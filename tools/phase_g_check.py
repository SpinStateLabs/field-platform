#!/usr/bin/env python3
"""phase_g_check - one-command live check of Phase G operator authentication.

    python tools/phase_g_check.py --base URL --secret-file PATH
        [--operator-id ID --key-file PATH] [--expect-mode off|log-only|enforce]
        [--agent canary-gb10] [--alias NAME ...] [--allow AGENT:EVENT,...] [--restore]

Replaces the hand-run curls of the Phase G canary gate. Same conventions as
tools/estate_probe.py (whose helpers it imports): standard library only,
[PASS]/[FAIL] lines, an 'N/M checks passed' summary, ASCII output, and exit
status 0 = every check passed, 1 = a check failed (or none ran, or an unexpected
error that did not leave the canary killed), 2 = refused (usage, rule 7, an unsafe
secret/key, the canary not active at the start or halted during the run),
3 = the canary may have been left KILLED (a kill whose outcome is unknown, a revive that failed,
an unexpected error with the revive failing): run this tool again with --restore;
4 = every check passed but the armed mode (log-only or enforce) was only inferred, never asserted
with --expect-mode (NOT VERIFIED; a failed check, 1, outranks it);
130 = interrupted with Ctrl-C (the canary is revived and verified first).
An unexpected error prints one redacted line (exception type and message), never a traceback.

WHAT IT DOES TO THE ESTATE. Every mutation targets the EXACT canary id
(canary-gb10 or canary-fly, confirmed in the registry as domain `canary`);
any other --agent is refused before anything is sent. The probe write is
POST /killswitch/revive/<canary> with the canary ACTIVE: when a guard lets it
through, it re-sets an already-active canary to active (a registry no-op) and
ledgers one kill.revive; when the guard refuses it, nothing changes. A kill is
never used as a probe. A canary that is not active is refused (exit 2), so the
tool never un-kills a canary that was halted before the run. The heartbeat is also
re-read immediately before every probe write and before the positive-path kill (the
revive of the canary this run killed has, by design, no re-read); a halt that lands between that read and
the write (one round trip) is still undone by the probe revive, because /revive
has no server-side precondition (kill_switch/api.py, the revive handler). That
residual window is server-side; this tool narrows it and cannot close it.

WITHOUT CREDENTIALS (--operator-id/--key-file omitted):
  1. Mode detection from behaviour alone: no headers => 401 means ENFORCE;
     200 plus an over-long key header => 400 means LOG-ONLY (a malformed
     credential is a 400 in any armed mode); 200 and 200 means OFF only when both
     answers are the kill-switch's heartbeat for the canary (agent_id, status=active,
     killed=false) AND the ledger shows exactly two new kill.revive events for it
     with no operator_* field (flags off write payloads unchanged): an edge that
     answers 200 to everything is mode UNVERIFIED, a FAIL. The 401 and 400 must
     carry the guard's own body. LOG-ONLY is cross-checked on the ledger: the
     no-credential write left one operator.unauthenticated event (OFF and ENFORCE
     leave none).
  2. Refusal paths for the detected mode (ENFORCE: 401 / 403 / 400; LOG-ONLY:
     allowed but never attributed, ledgered operator.unauthenticated, 400 for
     malformed headers): operator id without key, an unknown id with a made-up
     key, the same two with a different id, duplicate / non-ASCII / over-long
     / comma-joined header values, a display-name alias used as a login id.
     Every 403 body must be byte-identical (no oracle). Made-up keys are
     generated per run and never reuse a real key.
  4. No key, key hash, perimeter secret or made-up key in any response body or
     in any ledger payload field other than the 8-hex operator_key_fp.
  5. Collateral: every event in the ledger tail since the start names the
     probed canary (--agent) as its agent, or is an operator.unauthenticated row
     with no agent id. An operator.mode_changed / operator.registry_changed row
     with no agent id (the C-6 ledger observer) is printed as an [INFO] line and
     not counted. Anything else is a FAIL: another agent, the other canary,
     a retired canary, an event with no agent id. Use --allow AGENT:EVENT
     (<none> for no agent id) for events a busy estate legitimately appends.
  6. Pairing (C-12, LOG-ONLY and ENFORCE): every registry.status_changed of the
     canary since the start carries operator_id_authenticated and
     operator_on_behalf_of, and pairs one-to-one with a kill.* event of the canary
     since the start whose operator_id_authenticated is that operator (to killed:
     kill.agent or kill.drill.start; otherwise kill.revive or kill.drill.complete).
     A status PATCH sent straight to the registry, even with the kill-switch's own
     key, is a FAIL.

WITH --operator-id and --key-file the positive path (check 3) also runs, on the canary
only: the mismatch probe (your real key under another id => 403), then one
kill (heartbeat and registry say killed; the kill report names the
authenticated id; the kill.agent event carries operator_id_authenticated,
operator_claimed and operator_key_fp == first 8 hex of sha256(key)), then one
revive (back to active, kill.revive carries the same fields). A failure
between the kill and the revive triggers a best-effort revive.

HOW THE KEY TRAVELS. It is read from --key-file (never argv, never an
environment variable) into memory and sent ONLY as the x-field-operator-key
header of a request to --base, never in a URL, never written to a file by this
tool. The perimeter secret is sent as x-field-auth, as estate_probe does. The
tool prints neither, nor the key's hash; stdout and stderr are also redacted
for each of them as a last line of defence. Response bodies are never echoed.
FIELD_OPERATOR / FIELD_OPERATOR_KEY in the environment are NOT used for the
probes (the probes control their headers exactly); estate_probe-style reads
may still send them.

AFTER THE KILL. When the estate's kill-signal allowlist is armed (X3, GB10),
the kill makes `canary-agent` halt, and a halt is sticky until the container
restarts: /revive flips the registry, not the process. --restore revives the
canary if it is killed (with your credentials in ENFORCE) and prints the host
command that resumes the container, the documented restore (runbook X3 halt
endpoint): `docker compose ... restart canary-agent`. The tool never runs docker.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import secrets as _secrets
import sys
import time
import urllib.parse
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import estate_probe as ep  # noqa: E402

HDR_OP = "x-field-operator"
HDR_KEY = "x-field-operator-key"
OFF, LOG_ONLY, ENFORCE = "off", "log-only", "enforce"
#: An id that is in no operators file (the made-up identities are never real).
PROBE_OP = "phase-g-probe-nobody"
PROBE_OP_2 = "phase-g-probe-other"
#: The manifests list DISPLAY names; a display name is never a login id. Every name the shipped
#: canary manifests list: Don's two and the machine verifier's (P35, svc-verifier-<estate>).
DEFAULT_ALIASES = ("Don Hagell, Spin State Labs", "Don Hagell", "FIELD canary (gate verification)")
_KEY_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{1,256}$")
_OP_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
_FP = re.compile(r"^[0-9a-f]{8}$")
#: The guard's fixed refusal bodies ({"detail": ...}); a 400/401/403 from a proxy or edge
#: in front of the service does not carry them, so a bare status is not evidence.
UNAUTH_DETAIL = "operator credentials required"
FORBIDDEN_DETAIL = "operator not authorised"
MALFORMED_DETAIL = "malformed operator credential headers"
DETAILS = {401: UNAUTH_DETAIL, 403: FORBIDDEN_DETAIL, 400: MALFORMED_DETAIL}
#: Ledger payload keys only the guard's authenticated path sets (field_core/operator_auth.py
#: RESERVED_KEYS). Flags OFF: merge_payload leaves a payload unchanged, so none is present.
OPERATOR_FIELDS = frozenset({"operator_id_authenticated", "operator_claimed", "operator_key_fp",
                             "operator_body_claimed", "operator_on_behalf_of"})
#: Exit status: the canary may have been left killed (distinct from 1 = a plain failed check).
EXIT_STILL_KILLED = 3
#: Exit status: every check passed but the armed mode (log-only or enforce) was only INFERRED, because no
#: --expect-mode asserted it (C-122, C-287): a pass that did not verify the mode is not a 0. 3 is
#: EXIT_STILL_KILLED, 1 a failed check, 2 a refusal; a failed check (1) outranks 4.
EXIT_NOT_VERIFIED = 4
EXIT_INTERRUPTED = 130
BODY = {"operator": "phase-g-check (canary)", "reason": "phase-g live check - canary only"}
#: How long to wait for the (bounded, asynchronous) operator.unauthenticated append.
SETTLE_S = 6.0
RESTART_HINT = ("docker compose -p field-platform -f integration/demo/docker-compose.yml "
                "-f integration/demo/docker-compose.gb10.yml restart canary-agent")

LEAKS: list[str] = []


_internal_host = ep._internal_host      # one tested copy (C-489), not a third


def _hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# -- the sender: explicit headers, duplicates and raw bytes allowed ----------------


class Sender:
    """One HTTP request with EXACTLY the headers given (urllib cannot send a
    duplicate or a non-ASCII header). Never follows a redirect. Every response
    body is scanned for the needles registered in ``needles`` (kind -> value);
    a hit is recorded by kind and path only, never the value."""

    def __init__(self, base: str, secret: str | None, timeout: float = 20.0):
        parts = urllib.parse.urlsplit(base)
        self.scheme = parts.scheme
        self.host = parts.hostname or ""
        self.port = parts.port
        self.prefix = parts.path.rstrip("/")
        self.secret = secret
        self.timeout = timeout
        self.needles: dict[str, str] = {}

    def _conn(self):
        cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=self.timeout)

    def send(self, method: str, path: str, body: Any, headers: list[tuple[str, Any]]) -> tuple[int, Any, str]:
        data = json.dumps(body).encode() if body is not None else None
        conn = self._conn()
        try:
            conn.putrequest(method, f"{self.prefix}{path}", skip_accept_encoding=True)
            conn.putheader("Accept", "application/json")
            if data is not None:
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", str(len(data)))
            if self.secret:
                conn.putheader("x-field-auth", self.secret)
            for name, value in headers:
                conn.putheader(name, value)
            conn.endheaders(data)
            resp = conn.getresponse()
            raw, status = resp.read(), resp.status
        except Exception as exc:  # type name only: never a message
            return 0, {"transport_error": type(exc).__name__}, ""
        finally:
            conn.close()
        text = raw.decode("utf-8", "replace")
        for kind, needle in self.needles.items():
            if needle and needle in text:
                LEAKS.append(f"{kind} found in the response body of {method} {path}")
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = {"non_json_bytes": len(raw)}
        return status, parsed, text


class Ctx:
    def __init__(self, estate: "ep.Estate", sender: Sender, agent: str,
                 operator: str | None, key: str | None):
        self.estate, self.sender, self.agent = estate, sender, agent
        self.operator, self.key = operator, key
        self.fp = _hex(key)[:8] if key else None
        self.killed_by_us = False
        self.not_verified: str | None = None   # the armed mode that was inferred but never asserted
        self.bodies_403: list[str] = []
        self.fake_keys: list[str] = []

    # a made-up key, never anything real; registered so a reflected copy is a leak
    def fake_key(self) -> str:
        k = "fok_probe_" + _secrets.token_urlsafe(24)
        self.fake_keys.append(k)
        self.sender.needles[f"made-up key #{len(self.fake_keys)}"] = k
        return k

    def guard_active(self) -> None:
        """Re-read the canary state right before a probe write (it can change after the
        start-of-run check): a probe must never un-kill a canary halted on purpose."""
        hb = ep._heartbeat_killed(self.estate, self.agent)
        if hb is not False:
            ep._die(f"'{self.agent}' is no longer active (heartbeat killed={hb}): stopping before another write, "
                    "a revive probe could un-kill a canary halted on purpose")

    @property
    def revive_path(self) -> str:
        return f"/killswitch/revive/{ep._q(self.agent)}"

    def revive(self, headers: list[tuple[str, Any]]) -> tuple[int, Any, str]:
        return self.sender.send("POST", self.revive_path, BODY, headers)

    def kill(self, headers: list[tuple[str, Any]]) -> tuple[int, Any, str]:
        return self.sender.send("POST", f"/killswitch/kill/{ep._q(self.agent)}", BODY, headers)

    def creds(self) -> list[tuple[str, Any]]:
        return [(HDR_OP, self.operator), (HDR_KEY, self.key)]

    def events(self, event_type: str) -> list[dict] | None:
        return ep._events(self.estate, event_type=event_type, agent_id=self.agent)

    def unauth_events(self) -> list[dict] | None:
        """operator.unauthenticated rows for a revive of THIS canary (they carry no agent id)."""
        evs = ep._events(self.estate, event_type="operator.unauthenticated")
        if evs is None:
            return None
        suffix = f"/revive/{self.agent}"
        return [e for e in evs if isinstance(e.get("payload"), dict)
                and str(e["payload"].get("path", "")).endswith(suffix)]

    def wait_for(self, fetch, want_len: int) -> list[dict] | None:
        """The log-only append is asynchronous and bounded; poll for it."""
        deadline = time.time() + SETTLE_S
        while True:
            got = fetch()
            if got is None or len(got) >= want_len or time.time() >= deadline:
                return got
            time.sleep(0.25)


def _no_more(ctx: Ctx, fetch, want_len: int) -> list[dict] | None:
    """For 'this left NO event': wait the same settle window, return the final list."""
    deadline = time.time() + min(SETTLE_S, 3.0)
    got = fetch()
    while got is not None and len(got) <= want_len and time.time() < deadline:
        time.sleep(0.25)
        got = fetch()
    return got


def _guard_body(status: int, body: Any) -> bool:
    return isinstance(body, dict) and status in DETAILS and body.get("detail") == DETAILS[status]


def _heartbeat_of(body: Any, agent: str) -> bool:
    """The kill-switch's answer to a revive that went through: the canary's Heartbeat."""
    return (isinstance(body, dict) and body.get("agent_id") == agent and body.get("status") == "active"
            and body.get("killed") is False)


def _off_evidence(ctx: Ctx, r0: list[dict] | None, bodies: tuple[Any, Any]) -> bool:
    """200 and 200 alone would let an edge that answers 200 to everything read as OFF. The real
    kill-switch answers each revive that goes through with the canary's Heartbeat and ledgers one
    kill.revive whose payload is the request body, with no operator_* field (flags off)."""
    if not all(_heartbeat_of(b, ctx.agent) for b in bodies):
        ep.check(False, "HTTP 200 without the kill-switch's heartbeat body for the canary (a proxy or edge, "
                        "not the service?): mode UNVERIFIED")
        return False
    if r0 is None:       # the ledger read failed and is already a FAIL
        return False
    got = ctx.wait_for(lambda: ctx.events("kill.revive"), len(r0) + 2)
    new = got[len(r0):] if got is not None else None
    ok = new is not None and len(new) == 2 and all(
        isinstance(e.get("payload"), dict) and e["payload"].get("operator") == BODY["operator"]
        and not OPERATOR_FIELDS & set(e["payload"]) for e in new)
    ep.check(ok, "off: the two no-credential writes left exactly two kill.revive events for the canary, "
                 f"with no operator_* field ({len(new) if new is not None else '?'} new)"
                 + ("" if ok else ": mode UNVERIFIED"))
    return ok


# -- 1. mode detection ----------------------------------------------------------------


def detect_mode(ctx: Ctx, expect: str | None) -> str | None:
    print("1. mode detection (no credentials)")
    u0 = ctx.unauth_events()
    r0 = ctx.events("kill.revive")
    ctx.guard_active()
    s, b1, _ = ctx.revive([])
    detected: str | None = None
    if s == 401:
        if _guard_body(s, b1):
            detected = ENFORCE
        else:
            ep.check(False, "HTTP 401 without the guard's body shape (a proxy or edge, not the service?): "
                            "mode UNVERIFIED")
    elif s == 200:
        ctx.guard_active()
        s2, b2, _ = ctx.revive([(HDR_KEY, "k" * 257)])
        if s2 == 400 and not _guard_body(s2, b2):
            ep.check(False, "HTTP 400 without the guard's body shape (a proxy or edge, not the service?): "
                            "mode UNVERIFIED")
        elif s2 == 400:
            detected = LOG_ONLY
        elif s2 == 200:
            if _off_evidence(ctx, r0, (b1, b2)):
                detected = OFF
        else:
            ep.check(False, f"over-long key header answered HTTP {s2} (400 armed / 200 off): mode not inferable")
    else:
        ep.check(False, f"no-credential guarded write answered HTTP {s} (401 enforce / 200 log-only or off): "
                        "mode not inferable")
    if detected is None:
        return None
    ep.check(True, f"inferred mode: {detected} (no-credential write HTTP {s})")
    if u0 is not None:
        want = len(u0) + 1 if detected == LOG_ONLY else len(u0)
        if detected == LOG_ONLY:
            got = ctx.wait_for(ctx.unauth_events, want)
            ep.check(got is not None and len(got) == want,
                     f"log-only: the no-credential write left exactly one operator.unauthenticated "
                     f"event ({len(got) - len(u0) if got is not None else '?'} new)")
            if got and len(got) == want:
                p = got[-1].get("payload", {})
                ep.check(p.get("reason") == "no_credential" and p.get("action") == "revive",
                         f"that event says action=revive reason=no_credential (got action={p.get('action')} "
                         f"reason={p.get('reason')})")
        else:
            got = _no_more(ctx, ctx.unauth_events, want)
            ep.check(got is not None and len(got) == want,
                     f"{detected}: the no-credential write left NO operator.unauthenticated event")
    if expect is not None:
        ep.check(detected == expect, f"estate mode is {expect} as expected (inferred {detected})")
    elif detected == OFF:
        # C-122 (reviewer R-07): the mode is inferred from behaviour, and a guard that is OFF by mistake behaves
        # exactly like one that is OFF by design, so an unasserted OFF is not a pass
        ep.check(False, "no --expect-mode given and the guard looks OFF (mode only INFERRED, NOT VERIFIED): "
                        "OFF by mistake looks the same as OFF by design; give --expect-mode off to accept it")
    else:
        ctx.not_verified = detected
        print(f"  [NOT VERIFIED] mode {detected} was only inferred from behaviour; "
              f"give --expect-mode {detected} to assert it (the run will exit {EXIT_NOT_VERIFIED})")
    return detected


# -- 2. refusal paths ---------------------------------------------------------------------


def _probe(ctx: Ctx, mode: str, label: str, headers: list[tuple[str, Any]], *,
           enforce: tuple[int, ...], log_only: tuple[int, ...], want_event_reason: str | None = None,
           claimed: str | None = None) -> None:
    """One guarded write with the given headers; assert the status for the mode.
    In log-only a 200 must also be unattributed on the ledger (the revive event
    exists and carries no authenticated id)."""
    r0 = ctx.events("kill.revive")
    u0 = ctx.unauth_events() if want_event_reason else None
    ctx.guard_active()   # last read before the write: nothing between it and the revive
    s, body, text = ctx.revive(headers)
    shape = s not in DETAILS or _guard_body(s, body)
    note = "" if shape else " [body is not the guard's: UNVERIFIED]"
    if mode == ENFORCE:
        ep.check(s in enforce and shape, f"enforce: {label} => HTTP {s} (want {'/'.join(map(str, enforce))}){note}")
        if s == 403:
            ctx.bodies_403.append(text)
        if r0 is not None:
            r1 = ep._events(ctx.estate, event_type="kill.revive", agent_id=ctx.agent)
            ep.check(r1 is not None and len(r1) == len(r0), f"enforce: {label} wrote no kill.revive (refusal changed nothing)")
        return
    ep.check(s in log_only and shape, f"log-only: {label} => HTTP {s} (want {'/'.join(map(str, log_only))}){note}")
    if s != 200:
        return
    new = ctx.wait_for(lambda: ctx.events("kill.revive"), len(r0) + 1) if r0 is not None else None
    ok = new is not None and r0 is not None and len(new) == len(r0) + 1
    p = new[-1].get("payload", {}) if ok else {}
    ep.check(ok and p.get("operator_id_authenticated") is None and p.get("operator_key_fp") is None,
             f"log-only: {label} allowed but NOT attributed (operator_id_authenticated and operator_key_fp are null)")
    if claimed is not None and ok:
        ep.check(p.get("operator_claimed") == claimed, f"log-only: {label} ledgers operator_claimed as the header said")
    if want_event_reason and u0 is not None:
        got = ctx.wait_for(ctx.unauth_events, len(u0) + 1)
        reason = got[-1].get("payload", {}).get("reason") if got and len(got) == len(u0) + 1 else None
        ep.check(reason == want_event_reason,
                 f"log-only: {label} ledgered operator.unauthenticated reason={want_event_reason} (got {reason})")


def refusal_paths(ctx: Ctx, mode: str, aliases: list[str]) -> None:
    print(f"2. refusal paths ({mode})")
    if mode == OFF:
        ep.check(True, "mode off: the guard is not armed, so there is nothing to refuse (headers are ignored)")
        return
    other_id = ctx.operator or PROBE_OP_2
    _probe(ctx, mode, "operator id without a key", [(HDR_OP, PROBE_OP)],
           enforce=(401,), log_only=(200,), want_event_reason="incomplete_credential", claimed=PROBE_OP)
    _probe(ctx, mode, "unknown operator id with a made-up key", [(HDR_OP, PROBE_OP), (HDR_KEY, ctx.fake_key())],
           enforce=(403,), log_only=(200,), want_event_reason="bad_credential", claimed=PROBE_OP)
    wrong_for = "your operator id" if ctx.operator else "a second unknown id"
    _probe(ctx, mode, f"{wrong_for} with a made-up (wrong) key", [(HDR_OP, other_id), (HDR_KEY, ctx.fake_key())],
           enforce=(403,), log_only=(200,), want_event_reason="bad_credential", claimed=other_id)
    if ctx.key:
        _probe(ctx, mode, "your real key under a DIFFERENT operator id (id/key mismatch)",
               [(HDR_OP, PROBE_OP), (HDR_KEY, ctx.key)],
               enforce=(403,), log_only=(200,), want_event_reason="bad_credential", claimed=PROBE_OP)
    else:
        print("  (id/key mismatch with a real key: skipped, no --key-file)")

    # malformed credential headers are a request defect: 400 in ANY armed mode
    fake = ctx.fake_key()
    malformed: list[tuple[str, list[tuple[str, Any]]]] = [
        ("duplicate x-field-operator headers", [(HDR_OP, "a"), (HDR_OP, "b"), (HDR_KEY, fake)]),
        ("duplicate x-field-operator-key headers", [(HDR_OP, PROBE_OP), (HDR_KEY, fake), (HDR_KEY, fake)]),
        ("non-ASCII operator id", [(HDR_OP, "dón".encode("utf-8")), (HDR_KEY, fake)]),
        ("non-ASCII key", [(HDR_OP, PROBE_OP), (HDR_KEY, "kéy".encode("utf-8"))]),
        ("over-long operator id (65 chars)", [(HDR_OP, "a" * 65), (HDR_KEY, fake)]),
        ("over-long key (257 chars)", [(HDR_OP, PROBE_OP), (HDR_KEY, "k" * 257)]),
        ("comma-joined operator ids", [(HDR_OP, "a,b"), (HDR_KEY, fake)]),
    ]
    for label, headers in malformed:
        _probe(ctx, mode, f"malformed: {label}", headers, enforce=(400,), log_only=(400,))

    # an alias (display name) is never a login id
    for alias in aliases:
        if not alias:
            continue
        key = ctx.key or ctx.fake_key()
        hdr_alias: Any = alias.encode("utf-8") if not alias.isascii() else alias
        _probe(ctx, mode, "an alias / display name used as the login id" + (" (real key)" if ctx.key else ""),
               [(HDR_OP, hdr_alias), (HDR_KEY, key)],
               enforce=(400, 403), log_only=(200, 400))

    if mode == ENFORCE:
        distinct = set(ctx.bodies_403)
        ep.check(len(ctx.bodies_403) >= 2 and len(distinct) == 1,
                 f"all {len(ctx.bodies_403)} HTTP 403 bodies are byte-identical (no oracle): {len(distinct)} distinct")


# -- 3. positive path ------------------------------------------------------------------------


def _fields_ok(ev: dict, op: str, fp: str) -> tuple[bool, str]:
    p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    got_fp = p.get("operator_key_fp")
    ok = (p.get("operator_id_authenticated") == op and p.get("operator_claimed") == op
          and isinstance(got_fp, str) and _FP.fullmatch(got_fp) is not None and got_fp == fp)
    return ok, ("matches" if ok else "does NOT match")


def positive_path(ctx: Ctx, mode: str) -> None:
    op, fp = ctx.operator, ctx.fp
    assert op and fp
    print(f"3. positive path on {ctx.agent} (one kill, one revive, your credentials)")
    if mode == OFF:
        ep.check(True, "mode off: credentials are ignored, no attribution to verify - positive path not run")
        return
    k0, r0 = ep._count(ctx.estate, "kill.agent", ctx.agent), ep._count(ctx.estate, "kill.revive", ctx.agent)
    ctx.guard_active()
    # Set BEFORE sending: a kill the server applied but answered 503 / timed out / was interrupted
    # (Ctrl-C) is a canary that may be killed. The finally path in _run reads the state and revives.
    ctx.killed_by_us = True
    s, rep, _ = ctx.kill(ctx.creds())
    if not ep.check(s == 200 and isinstance(rep, dict) and rep.get("status") == "killed",
                    f"kill with your credentials => 200 status=killed (got HTTP {s})"):
        if ep._heartbeat_killed(ctx.estate, ctx.agent) is not False:
            print("  CANARY MAY STILL BE KILLED: the kill's outcome is unknown. Run --restore "
                  "(attempting an emergency revive now).")
        else:
            ctx.killed_by_us = False
        return
    er = rep.get("endpoint_result") if isinstance(rep, dict) else None
    outcome = er.get("outcome") if isinstance(er, dict) else None
    ep.check(rep.get("operator") == op, "the kill report names the authenticated operator id, not the body text")
    ep.check(ep._heartbeat_killed(ctx.estate, ctx.agent) is True, "heartbeat killed=true after the kill")
    st, rec = ctx.estate.call("GET", f"/registry/agents/{ep._q(ctx.agent)}")
    ep.check(st == 200 and isinstance(rec, dict) and rec.get("status") == "killed", "registry status is killed")
    evs = ctx.events("kill.agent")
    new = evs[k0:] if evs is not None and k0 is not None else None
    if ep.check(new is not None and len(new) == 1, "exactly +1 kill.agent for the canary"):
        ok, word = _fields_ok(new[0], op, fp)
        ep.check(ok, f"kill.agent carries operator_id_authenticated and operator_claimed == your id and "
                     f"operator_key_fp {word} the key fingerprint (8 hex, not shown)")
    s, hb, _ = ctx.revive(ctx.creds())
    ep.check(s == 200, f"revive with your credentials => 200 (got HTTP {s})")
    alive = ep.check(ep._heartbeat_killed(ctx.estate, ctx.agent) is False, "heartbeat killed=false after the revive")
    if alive:
        ctx.killed_by_us = False   # otherwise the finally path tries again and reports STILL KILLED
    evs = ctx.events("kill.revive")
    new = evs[r0:] if evs is not None and r0 is not None else None
    if ep.check(new is not None and len(new) == 1, "exactly +1 kill.revive for the canary"):
        ok, word = _fields_ok(new[0], op, fp)
        ep.check(ok, f"kill.revive carries the authenticated fields and operator_key_fp {word} the fingerprint")
    if outcome == "called":
        print("  NOTE: the kill signalled the agent (endpoint_result outcome=called). A halted canary-agent "
              "container STAYS halted until restarted: /revive flips the registry, not the process. Run --restore.")


# -- 4. no key / hash anywhere ---------------------------------------------------------------


def _strip_fp(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_fp(v) for k, v in obj.items() if k != "operator_key_fp"}
    if isinstance(obj, list):
        return [_strip_fp(v) for v in obj]
    return obj


def no_leak(ctx: Ctx, start: int, secret: str | None) -> None:
    print("4. nothing secret in any response or ledger payload")
    ep.check(not LEAKS, "no key, key hash, perimeter secret or made-up key in any response body"
             + ("" if not LEAKS else ": " + "; ".join(sorted(set(LEAKS)))))
    needles = {"made-up key": list(ctx.fake_keys)}
    if ctx.key:
        needles.update({"operator key": [ctx.key], "key sha256": [_hex(ctx.key)]})
    if secret:
        needles["perimeter secret"] = [secret]
    events = ep._events(ctx.estate)
    if events is None:
        return
    tail = events[start:]
    bad: list[str] = []
    fps: list[Any] = []
    for ev in tail:
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        if "operator_key_fp" in payload:
            fps.append(payload["operator_key_fp"])
        text = json.dumps(_strip_fp(payload), sort_keys=True)
        if ctx.fp and ctx.fp in text:
            bad.append("key fingerprint outside operator_key_fp")
        whole = json.dumps(ev, sort_keys=True)
        for kind, values in needles.items():
            if any(v and v in whole for v in values):
                bad.append(f"{kind} in {ev.get('event_type')}")
    ep.check(not bad, f"{len(tail)} ledger events since the start hold no key, hash, secret or made-up key, and the "
                      f"fingerprint only under operator_key_fp" + ("" if not bad else ": " + "; ".join(sorted(set(bad)))))
    ep.check(all(isinstance(f, str) and _FP.fullmatch(f) for f in fps if f is not None),
             f"every non-null operator_key_fp is exactly 8 lowercase hex ({len(fps)} seen)")


# -- 5. collateral ---------------------------------------------------------------------------


#: C-6: the ledger's own operator observer writes these, with no agent id, at its first
#: observation of each service and on every change of mode or operators file. One can land
#: inside the window (a flip, a recreate or a ledger restart just before the run); it is the
#: ledger's record of the estate, not a mutation by this tool, so check 5 lists it as
#: information. Only these two exact types with NO agent id are exempt.
OBSERVER_EVENT_TYPES = frozenset({"operator.mode_changed", "operator.registry_changed"})
_SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,47}$")   # a service name; never a key (no _ or upper case)


def _observer_row(ev: dict) -> bool:
    return ev.get("agent_id") is None and ev.get("event_type") in OBSERVER_EVENT_TYPES


def collateral(ctx: Ctx, start: int, allow: set[str]) -> None:
    print(f"5. collateral: every mutation was on {ctx.agent} (events of any other agent, the other canary "
          "included, are collateral)")
    events = ep._ledger(ctx.estate)
    if events is None:
        return
    if not ep.check(0 <= start <= len(events), f"start index {start} is inside the ledger (length {len(events)})"):
        return
    others: dict[tuple[str, str], int] = {}
    observed: dict[str, list[str]] = {}
    for ev in events[start:]:
        if _observer_row(ev):
            p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
            svc = p.get("service")
            observed.setdefault(ev["event_type"], []).append(
                svc if isinstance(svc, str) and _SERVICE_RE.fullmatch(svc) else "?")
            continue
        agent = ev.get("agent_id") or "<none>"
        etype = ev.get("event_type", "?")
        if agent == ctx.agent or (agent == "<none>" and etype == "operator.unauthenticated"):
            continue
        others[(agent, etype)] = others.get((agent, etype), 0) + 1
    for etype, services in sorted(observed.items()):
        print(f"  [INFO] {len(services)} x {etype} with no agent id (C-6 ledger observer: "
              f"{', '.join(sorted(set(services)))}) - the ledger's own record, not collateral")
    for (agent, etype), n in sorted(others.items()):
        ep.check(f"{agent}:{etype}" in allow, f"{n} x {etype} for {agent}"
                 + ("" if f"{agent}:{etype}" in allow else " - NOT intended by this tool (use --allow if expected)"))
    if not others:
        ep.check(True, "no ledger events about a non-canary agent since the start")


# -- 6. registry status changes pair with kill.* events (C-12) -----------------------------

#: A registry status change to "killed" is made by a kill (or the kill half of a drill); any
#: other target status by a revive (or the drill's restore).
_PAIRS_KILLED = frozenset({"kill.agent", "kill.drill.start"})
_PAIRS_OTHER = frozenset({"kill.revive", "kill.drill.complete"})


def _shown(value: Any) -> str:
    """An operator id from the ledger, fit to print: the id charset without the key prefix,
    else "(not shown)"; a missing value is "nobody"."""
    if value is None:
        return "nobody"
    if isinstance(value, str) and _OP_RE.fullmatch(value) and not value.startswith("fok_"):
        return value
    return "(not shown)"


def status_pairing(ctx: Ctx, start: int, mode: str) -> None:
    """C-12 / RT1-3: every registry.status_changed of the canary since the start must be
    written by an authenticated identity on behalf of an operator (operator_on_behalf_of),
    and pair one-to-one with a kill.* event of the canary since the start whose
    operator_id_authenticated is that operator (to killed: kill.agent / kill.drill.start;
    otherwise kill.revive / kill.drill.complete). A status PATCH sent straight to the
    registry, even with the kill-switch's own key, has no kill.* event of its own."""
    print("6. registry status changes pair with kill.* events by the operator they name (C-12)")
    if mode == OFF:
        ep.check(True, "mode off: status changes carry no attribution to pair - not run")
        return
    events = ep._events(ctx.estate)
    if events is None:
        return
    tail = [ev for ev in events[start:] if isinstance(ev, dict) and ev.get("agent_id") == ctx.agent]
    changes = [ev for ev in tail if ev.get("event_type") == "registry.status_changed"]
    kills = [ev for ev in tail if str(ev.get("event_type", "")).startswith("kill.")]
    if not changes:
        if ctx.key:
            ep.check(False, f"no registry status change of {ctx.agent} since the start, but the positive path "
                            "killed and revived it (want >= 2: none means the pairing below proved nothing)")
        else:
            ep.check(True, f"no registry status change of {ctx.agent} since the start (nothing to pair)")
        return
    used: set[int] = set()
    for ev in changes:
        p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        to, svc, who = p.get("to"), p.get("operator_id_authenticated"), p.get("operator_on_behalf_of")
        wanted = _PAIRS_KILLED if to == "killed" else _PAIRS_OTHER
        match = None
        if isinstance(svc, str) and svc and isinstance(who, str) and who:
            for i, k in enumerate(kills):
                kp = k.get("payload") if isinstance(k.get("payload"), dict) else {}
                if i not in used and k.get("event_type") in wanted and kp.get("operator_id_authenticated") == who:
                    match = i
                    break
        label = (f"registry.status_changed to {_shown(to) if to is not None else '?'} by {_shown(svc)} "
                 f"on behalf of {_shown(who)}")
        if match is not None:
            used.add(match)
            ep.check(True, f"{label} pairs with {kills[match].get('event_type')} by {_shown(who)}")
        else:
            ep.check(False, f"{label} - NOT paired with a kill.* event by that operator (a status write "
                            "outside the kill-switch, or a kill-switch that does not name its caller)")
    if ctx.key:
        ep.check(len(changes) >= 2, f"the positive path's kill and revive ledgered {len(changes)} registry status "
                                    f"change(s) of {ctx.agent} (want >= 2: fewer means part of the pairing proved nothing)")


# -- --restore -------------------------------------------------------------------------------


def restore(ctx: Ctx) -> int:
    print(f"restore - {ctx.agent}")
    killed = ep._heartbeat_killed(ctx.estate, ctx.agent)
    if killed is None:
        ep.check(False, "cannot read the canary's heartbeat")
        return ep.finish()
    if killed:
        s, _, _ = ctx.revive(ctx.creds() if ctx.key else [])
        ep.check(s == 200, f"revive => 200 (got HTTP {s})" + ("" if ctx.key else " [no credentials given]"))
        ep.check(ep._heartbeat_killed(ctx.estate, ctx.agent) is False, "heartbeat killed=false after the revive")
    else:
        ep.check(True, "the canary is already active in the registry; nothing to revive")
    print("  NEXT (host, GB10 only - this tool never runs docker): if the X3 halt fired, the canary-agent "
          "process is still halted. Resume it with:")
    print(f"    {RESTART_HINT}")
    print("  then GET /status on canary-agent shows halted=False, halts=0. Fly has no agent-side halt endpoint.")
    return ep.finish()


# -- main ----------------------------------------------------------------------------------------


def _read_key(path: str) -> str:
    try:
        with open(path, encoding="utf-8-sig") as fh:   # PowerShell 5.1 writes a BOM
            value = fh.read().strip()
    except (OSError, UnicodeDecodeError):
        ep._die("--key-file is not readable")
    if not value or not _KEY_RE.fullmatch(value):
        ep._die("--key-file does not hold a well-formed operator key (value not shown)")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="phase_g_check.py", description="Live check of Phase G operator authentication, canary only.",
        epilog="Exit 0: all checks passed. 1: a check failed (or an unexpected error that did not leave the canary killed). "
               "2: refused (usage, rule 7, unsafe secret/key, canary not active). "
               "3: the canary may have been left KILLED - run again with --restore. "
               "4: all checks passed but the armed mode was only inferred (no --expect-mode): NOT VERIFIED. "
               "130: interrupted (Ctrl-C), canary verified active. "
               "See the module docstring (tools/phase_g_check.py) for the full description.")
    p.add_argument("--base", required=True, help="estate base URL, e.g. http://127.0.0.1:18080 or an https Fly URL")
    p.add_argument("--secret-file", help="file holding the perimeter secret (x-field-auth); "
                   "else FIELD_SHARED_SECRET. Never printed")
    p.add_argument("--operator-id", help="your operator id (a person, or the machine verifier svc-verifier-<estate>); needs --key-file. Enables the positive path "
                   "(one kill + one revive of the canary) and the id/key mismatch probe")
    p.add_argument("--key-file", help="file holding your operator key; sent only as the x-field-operator-key "
                   "header, never printed or put in a URL or argv")
    p.add_argument("--expect-mode", choices=(OFF, LOG_ONLY, ENFORCE),
                   help="fail unless the inferred mode is this (the mode is always inferred from behaviour). "
                   "Without it a run that infers OFF FAILS (OFF by mistake looks like OFF by design) and one "
                   "that infers log-only or enforce prints NOT VERIFIED: give it on every gate run")
    p.add_argument("--agent", default="canary-gb10", help="canary-gb10 (default) or canary-fly; anything else is refused")
    p.add_argument("--alias", action="append", default=[], metavar="NAME",
                   help="a display name your key answers to in a manifest (repeatable); each must be rejected as a "
                   "login id. Defaults to the shipped canary manifest names")
    p.add_argument("--allow", help="comma list of AGENT:EVENT_TYPE ledger events expected from other agents "
                   "during the run (collateral check)")
    p.add_argument("--allow-plaintext", action="store_true",
                   help="permit http:// to a non-loopback, non-private host with the secret")
    p.add_argument("--restore", action="store_true",
                   help="revive the canary if killed, print the host command that resumes the canary-agent "
                   "container, and exit; probes nothing else")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ep.RESULTS.clear()
    LEAKS.clear()
    if bool(args.operator_id) != bool(args.key_file):
        ep._die("--operator-id and --key-file go together")
    if args.operator_id and not _OP_RE.fullmatch(args.operator_id):
        ep._die("--operator-id must match [A-Za-z0-9._@-]{1,64}")
    secret = ep._secret(args.secret_file)
    key = _read_key(args.key_file) if args.key_file else None
    if args.agent not in ep.CANARIES:
        ep._die(f"'{args.agent}' is not one of {sorted(ep.CANARIES)} - this tool mutates the canary only (rule 7)")

    # made-up keys are registered later, but the real ones are redacted from the first byte
    saved = sys.stdout, sys.stderr
    for s in _secret_values(secret, key):
        sys.stdout, sys.stderr = ep._Redact(sys.stdout, s), ep._Redact(sys.stderr, s)
    try:
        return _run(args, secret, key)
    finally:
        sys.stdout, sys.stderr = saved


def _secret_values(secret: str | None, key: str | None) -> list[str]:
    """What the stream redactor removes: the perimeter secret, the key, its sha256 and fingerprint,
    and an operator key in the environment."""
    return [s for s in (secret, key, _hex(key) if key else None, _hex(key)[:8] if key else None,
                        os.environ.get("FIELD_OPERATOR_KEY") or None) if s]


def _scrub(text: str, values: list[str]) -> str:
    """The stream redactor's replacement applied to a whole string, so that a later cut can never
    leave part of a secret behind (the stream redactor only matches a secret whole)."""
    for s in values:
        for needle in (s, repr(s)[1:-1]):
            text = text.replace(needle, "<redacted>")
    return text


def _run(args: argparse.Namespace, secret: str | None, key: str | None) -> int:
    # The env key counts: ep.Estate.call sends FIELD_OPERATOR_KEY on every read.
    if secret or key or os.environ.get("FIELD_OPERATOR_KEY"):
        parts = urllib.parse.urlsplit(args.base)
        host = parts.hostname or ""
        local = _internal_host(host)
        if parts.scheme != "https" and not local and not args.allow_plaintext:
            ep._die("the secret/key would travel in cleartext: use https:// or a loopback/private address")
    estate = ep.Estate(args.base, secret)
    sender = Sender(args.base, secret)
    ctx = Ctx(estate, sender, args.agent, args.operator_id, key)
    if secret:
        sender.needles["perimeter secret"] = secret
    if key:
        sender.needles["operator key"] = key
        sender.needles["key sha256"] = _hex(key)
        sender.needles["key fingerprint"] = ctx.fp or ""
    ep._require_canary(estate, args.agent)
    hb = ep._heartbeat_killed(estate, args.agent)
    if args.restore:
        return restore(ctx)
    if hb is not False:
        ep._die(f"'{args.agent}' is not active (heartbeat killed={hb}): refusing to probe, a revive probe could "
                "un-kill a canary halted on purpose. Use --restore, or revive it yourself")

    print(f"phase_g_check - {args.agent}")
    status, health = estate.call("GET", "/ledger/health", auth=False)
    start = health.get("event_count") if status == 200 and isinstance(health, dict) else None
    if not isinstance(start, int):
        ep.check(False, f"cannot read the ledger event count (HTTP {status}): collateral cannot be bounded")
        return ep.finish()
    interrupted = crashed = False
    try:
        mode = detect_mode(ctx, args.expect_mode)
        if mode is None:
            return ep.finish()
        refusal_paths(ctx, mode, list(DEFAULT_ALIASES) + args.alias)
        if key:
            positive_path(ctx, mode)
        else:
            print("3. positive path: skipped (give --operator-id and --key-file to run it)")
    except KeyboardInterrupt:
        interrupted = True
        print("\ninterrupted (Ctrl-C)")
    except Exception as exc:  # a bug must not escape as a traceback or skip the settle below
        crashed = True
        # one line, type and message only: redact the WHOLE message, then flatten and bound it (a cut
        # made before redaction could print the prefix of a key); stderr is also behind the redactor
        msg = " ".join(_scrub(str(exc), _secret_values(secret, key)).split())[:300]
        print(f"error: unexpected {type(exc).__name__}: {msg} (the run is incomplete)", file=sys.stderr)
    finally:
        still_killed = _settle_canary(ctx)
    if still_killed:
        ep.finish()
        return EXIT_STILL_KILLED
    if crashed:
        ep.finish()
        return 1
    if interrupted:
        print("the canary was verified active by a read; the run is incomplete")
        return EXIT_INTERRUPTED
    no_leak(ctx, start, secret)
    allow = set(filter(None, (args.allow or "").split(",")))
    collateral(ctx, start, allow)
    status_pairing(ctx, start, mode)
    print("NOTE: all mutations were on the canary. If the kill signalled canary-agent (X3), that container stays "
          "halted until restarted - see --restore and the runbook section 'X3 halt endpoint'.")
    rc = ep.finish()
    if rc == 0 and ctx.not_verified is not None:
        print(f"NOT VERIFIED: every check passed, but mode {ctx.not_verified} was only inferred from behaviour; "
              f"exit status {EXIT_NOT_VERIFIED}. Give --expect-mode {ctx.not_verified} to verify it.")
        return EXIT_NOT_VERIFIED
    return rc


def _settle_canary(ctx: Ctx) -> bool:
    """After any exit from the probes: if this run may have killed the canary, read its state
    and revive it if needed. Returns True only when the canary is (or may be) STILL killed."""
    if not ctx.killed_by_us:
        return False
    try:
        if ep._heartbeat_killed(ctx.estate, ctx.agent) is False:
            ctx.killed_by_us = False
            return False
        s, _, _ = ctx.revive(ctx.creds())
        alive = ep._heartbeat_killed(ctx.estate, ctx.agent) is False
        ep.check(s == 200 and alive, f"emergency revive after an interrupted positive path => 200 and "
                                     f"heartbeat killed=false (got HTTP {s}, active={alive})")
        if alive:
            ctx.killed_by_us = False
            return False
    except KeyboardInterrupt:
        pass
    print("")
    print("!!! CANARY STILL KILLED (or its state could not be confirmed): run this tool again with --restore "
          "and the same --operator-id/--key-file to revive it;")
    print(f"!!! if the X3 halt fired, the canary-agent container also stays halted - on the GB10 host: {RESTART_HINT}")
    print(f"!!! exit status {EXIT_STILL_KILLED} = canary left killed")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
