#!/usr/bin/env python3
"""estate_probe - live verification of a FIELD estate, standard library only.

The evidence engine for every production deploy gate (v1.2 plan revision 2.1).
If it can report PASS on a broken estate, a broken deploy is declared green, so
every check is written to FAIL on the breakage it exists to catch. An
adversarial review (2026-09-12) broke the first version nine ways on a
fault-injected estate running the real services; each fix below is pinned by a
test in tools/tests/test_estate_probe.py.

Runs anywhere Python 3.7+ runs: on the GB10 host against the Caddy proxy
(http://127.0.0.1:18080), or inside a Fly machine against http://127.0.0.1:8080.
No third-party package, so it can be copied onto an estate as-is. Output is
ASCII only.

SECRETS. FIELD_SHARED_SECRET from the environment, or --secret-file, is sent as
`x-field-auth`. It is never printed: a value with whitespace, control or
non-ASCII characters is refused before use (a CRLF .env once put it in a
ValueError); response bodies are never echoed (an upstream can reflect
headers); redirects are never followed (a 3xx would carry the header to another
host); a cleartext non-loopback, non-private base is refused; and stdout and
stderr are redacted as a last line of defence.

OPERATOR IDENTITY (Phase G C-2). --operator-id and --operator-key-file (before
the subcommand), else FIELD_OPERATOR with FIELD_OPERATOR_KEY_FILE or
FIELD_OPERATOR_KEY. The key file is read here and stripped; the key is never
an argument and never printed (stdout and stderr are redacted for it as for the
secret), and a broken key file named on the command line refuses (exit 2)
before anything is sent. The pair travels ONLY on the guarded routes in
GUARDED_ROUTES (kill, revive, drill, attest, token revoke: RT1-10), never on a
read, a check-in, a sentinel check or an introspection. With a key present, a
cleartext non-loopback, non-private base is refused as for the secret.

RULE 7 - CANARY-ONLY MUTATION. Every subcommand that changes estate state acts
only on the EXACT canary ids (canary-gb10, canary-fly), confirmed in the
registry as domain `canary`, with a token confirmed to belong to that canary.
`refused-kill` fires only at a decommissioned canary (canary-<estate>-retired),
so even a broken retired-guard can never halt a real agent.

READS NEVER PASS ON NOTHING. A failed ledger read is a FAIL, never an empty
list; the ledger's /health, /events and /verify must describe the same chain;
kill, revive and drill must each leave exactly one ledger event.

Exit status: 0 every check passed, 1 at least one check failed (or none ran),
2 refused (usage, rule 7, or an unsafe secret). `registry --agent` is the one
subcommand that answers a question with its exit code, so it keeps the codes
apart: 0 present, 1 absent (the read succeeded and the id is not in it), 2 usage
(an unsafe or empty id), 3 unreadable or unexpected (HTTP error, transport error,
non-list body, a row that is not an object, a duplicated id, a non-text status).
A script must treat 3 as "unknown", never as "absent".

Subcommands (all take --base):
  health       every prefix /health names the right service, and one data route
               per service is serving; --expect-perimeter also requires 401
               without the header; --expect-build-sha SHA requires every
               service /health, the console's included, to report that
               build_sha (one container left on an old image fails)
  pin          ledger event count and head hash, only from a consistent ledger
  continuity   history up to a pinned (count, hash) is unchanged
  canary       C0 verdict checks on the canary
  catalogue    the Phase A + B live catalogue on the canary
  refused-kill a kill of a retired canary is refused 409 and ledgers nothing
  revoke       revoke the canary's token (end of every gate's live checks)
  collateral   every ledger event after --since that is not a canary's
  registry     READ-ONLY: one authenticated GET /registry/agents; prints agent
               id, domain and status only (never a token or any other field);
               --agent ID reports whether that exact id is present and its
               status, exit 0 present / 1 absent / 3 unreadable or unexpected
               (2 usage). Never mutates, so it does not call _require_canary
               (it is in READ_ONLY_SUBCOMMANDS, pinned by
               tools/tests/test_estate_probe.py)
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SERVICES: dict[str, str] = {
    "registry": "agent-registry",
    "ledger": "sealed-ledger",
    "delegation": "delegation-authority",
    "sentinel": "conformance-sentinel",
    "killswitch": "kill-switch",
    "governor": "spend-governor",
    "replay": "incident-replay",
    "gateway": "force-gateway",
    "federation": "federation-broker",
    "lifecycle": "lifecycle-manager",
    "attest": "attestation-reporter",
    "crosswalk": "compliance-crosswalk",
}
#: prefix -> (method, protected read-only data route, statuses that mean "serving")
DATA_ROUTES: dict[str, tuple[str, str, tuple[int, ...]]] = {
    "registry": ("GET", "/registry/agents", (200,)),
    "ledger": ("GET", "/ledger/events?limit=1", (200,)),
    "delegation": ("GET", "/delegation/tokens?agent_id=__probe_none__", (200,)),
    "sentinel": ("GET", "/sentinel/clauses", (200,)),
    "killswitch": ("GET", "/killswitch/liveness", (200,)),
    "governor": ("GET", "/governor/escalations", (200,)),
    "replay": ("POST", "/replay/replay", (422,)),
    "gateway": ("GET", "/gateway/presets", (200,)),
    "federation": ("GET", "/federation/contracts", (200,)),
    "lifecycle": ("GET", "/lifecycle/findings", (200, 404)),
    "attest": ("GET", "/attest/pack", (200,)),
    "crosswalk": ("GET", "/crosswalk/frameworks", (200,)),
}

#: Rule 7: EXACT ids, never a prefix. A real agent may be called canary-anything.
CANARIES = frozenset({"canary-gb10", "canary-fly"})
#: refused-kill targets a decommissioned CANARY, so rule 7 has no exception.
RETIRED_CANARIES = frozenset({"canary-gb10-retired", "canary-fly-retired"})
CANARY_DOMAIN = "canary"
#: C4: the board pack counts canary activity in this ONE row and excludes it
#: from every governance metric (attestation_reporter/engine.py CANARY_AGENTS).
ATTEST_GATE_ROW = "Gate-verification events (canary agents, excluded from every other figure)"
#: Subcommands that never mutate. Every other subcommand MUST call _require_canary
#: first (rule 7); tools/tests/test_estate_probe.py pins this exact set and checks
#: it against the handlers, so widening it needs an edit here AND in the test.
READ_ONLY_SUBCOMMANDS = frozenset({"health", "pin", "continuity", "collateral", "registry"})
#: Phase G C-2 (RT1-10): the ONLY (method, path) pairs that carry the operator
#: pair. Each is a guarded route of a service; tools/tests/test_operator_cli_c2.py
#: checks every entry against the services' api.py and every write this tool sends.
GUARDED_ROUTES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("POST", re.compile(r"/killswitch/kill/[^/]+")),
    ("POST", re.compile(r"/killswitch/revive/[^/]+")),
    ("POST", re.compile(r"/killswitch/drill/[^/]+")),
    ("POST", re.compile(r"/registry/agents/[^/]+/attest")),
    ("POST", re.compile(r"/delegation/tokens/[^/]+/revoke")),
)
_OPERATOR_ID = re.compile(r"[A-Za-z0-9._@-]{1,64}")
_OPERATOR_KEY = re.compile(r"[A-Za-z0-9._~+/=-]{1,256}")
_MAX_KEY_FILE_BYTES = 4096
#: `registry --agent` exit codes (see the module docstring).
EXIT_PRESENT, EXIT_ABSENT, EXIT_USAGE, EXIT_UNREADABLE = 0, 1, 2, 3
_MAX_TEXT = 128
GENESIS = "0" * 64
_HASH = re.compile(r"^[0-9a-f]{16,64}$")
#: A full git commit SHA (sha-1 or sha-256 object format) - never "unknown".
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
RESULTS: list[tuple[bool, str]] = []


def _q(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def _die(msg: str) -> "None":
    print(f"refusing: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _clean(value: Any) -> str | None:
    """The value itself if it is 1-128 printable ASCII characters with no whitespace,
    else None. The one filter for anything from a response that may be printed."""
    if (isinstance(value, str) and 0 < len(value) <= _MAX_TEXT and value.isascii()
            and value.isprintable() and not any(c.isspace() for c in value)):
        return value
    return None


def _shape(body: Any) -> str:
    """Never print a response body: it can reflect request headers. Key names are
    response data too, so each passes the same filter as _plain or is masked."""
    if isinstance(body, dict):
        keys = sorted(_clean(k) or "<unsafe-key>" for k in body)
        return "dict keys=" + ",".join(keys[:12])
    return type(body).__name__


# -- plumbing -------------------------------------------------------------------


def _secret(secret_file: str | None) -> str | None:
    if secret_file:
        try:
            with open(secret_file, encoding="utf-8") as fh:
                value = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            _die("--secret-file is not readable")
        if not value:
            _die("--secret-file is empty")
    else:
        value = os.environ.get("FIELD_SHARED_SECRET", "")
    if value and (not value.isascii() or not value.isprintable() or any(c.isspace() for c in value)):
        _die("shared secret contains whitespace, control or non-ASCII characters (value not shown)")
    return value or None


def _read_key_file(path: str, strict: bool) -> str:
    """The stripped key in ``path``. ``strict`` (named by --operator-key-file):
    any problem refuses (exit 2) before anything is sent. Otherwise (named by
    FIELD_OPERATOR_KEY_FILE): a warning and no identity, as field-core's
    operator_headers does. The content is never printed."""
    problem, key = None, ""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_MAX_KEY_FILE_BYTES + 1)
    except OSError as exc:
        problem = f"unreadable ({type(exc).__name__})"
    else:
        if len(raw) > _MAX_KEY_FILE_BYTES:
            problem = "larger than a key"
        else:
            try:
                key = raw.decode("utf-8-sig").strip()
            except UnicodeDecodeError:
                problem = "not UTF-8"
            else:
                if not key:
                    problem = "empty"
                elif not _OPERATOR_KEY.fullmatch(key):
                    problem = "not a single key token"
    if problem:
        if strict:
            _die(f"--operator-key-file is {problem}; nothing sent")
        print(f"warning: FIELD_OPERATOR_KEY_FILE is {problem}; no operator identity is sent", file=sys.stderr)
        return ""
    return key


def operator_pair(operator_id: str | None, key_file: str | None) -> tuple[str, str] | None:
    """(id, key) for the guarded routes, or None. The flags win over the
    environment; FIELD_OPERATOR_KEY_FILE wins over FIELD_OPERATOR_KEY (an
    unusable file never falls back to the variable)."""
    explicit = operator_id is not None or key_file is not None
    op = (operator_id if operator_id is not None else os.environ.get("FIELD_OPERATOR", "")).strip()
    env_file = os.environ.get("FIELD_OPERATOR_KEY_FILE", "").strip()
    if key_file is not None:
        key = _read_key_file(key_file, strict=True)
    elif env_file:
        key = _read_key_file(env_file, strict=explicit) if (op or explicit) else ""
    else:
        key = os.environ.get("FIELD_OPERATOR_KEY", "")
    if explicit and not (op and key):
        _die("--operator-id and an operator key (--operator-key-file, FIELD_OPERATOR_KEY_FILE or "
             "FIELD_OPERATOR_KEY) go together; nothing sent")
    if not (op and key):
        return None
    if not _OPERATOR_ID.fullmatch(op):
        _die("the operator id is not a valid operator id; nothing sent")
    if not _OPERATOR_KEY.fullmatch(key):
        _die("the operator key is not a single key token (value not shown); nothing sent")
    return op, key


def is_guarded(method: str, path: str) -> bool:
    """True only for an allowlisted guarded (method, path); the query is ignored."""
    path = urllib.parse.urlsplit(path).path
    return any(m == method.upper() and rx.fullmatch(path) for m, rx in GUARDED_ROUTES)


class _Redact:
    """Last line of defence: nothing written to stdout/stderr (tracebacks
    included) can carry the secret (or the operator key) verbatim."""

    def __init__(self, stream, secret: str, *more: str):
        self._s = stream
        self._needles = {form for value in (secret, *more) if value for form in (value, repr(value)[1:-1])}

    def write(self, text):
        for n in self._needles:
            text = text.replace(n, "<redacted>")
        return self._s.write(text)

    def __getattr__(self, name):
        return getattr(self._s, name)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx is an answer, never a hop: the header must not travel


_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))


class Estate:
    def __init__(self, base: str, secret: str | None, timeout: float = 20.0, *,
                 operator: tuple[str, str] | None = None):
        self.base = base.rstrip("/")
        self._secret = secret
        self.timeout = timeout
        self._operator = operator  # sent only on GUARDED_ROUTES, never printed

    @property
    def authenticated(self) -> bool:
        return self._secret is not None

    def call(self, method: str, path: str, body: Any | None = None, *, auth: bool = True,
             form: dict[str, str] | None = None) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth and self._secret:
            headers["x-field-auth"] = self._secret
        # Phase G C-2: this tool's own operator identity, on guarded routes only (never printed).
        if self._operator and is_guarded(method, path):
            headers["x-field-operator"], headers["x-field-operator-key"] = self._operator
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method, headers=headers)
        try:
            with _OPENER.open(req, timeout=self.timeout) as resp:
                raw, status = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            status = exc.code
        except Exception as exc:  # type name only: never a message
            return 0, {"transport_error": type(exc).__name__}
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, {"non_json_bytes": len(raw)}


def check(ok: bool, label: str) -> bool:
    RESULTS.append((bool(ok), label))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return bool(ok)


def finish() -> int:
    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for label in failed:
        print(f"  FAILED: {label}")
    return 1 if failed or not RESULTS else 0


def _events(estate: Estate, **params: str) -> list[dict] | None:
    """None (and a recorded FAIL) when the ledger cannot be read - never []."""
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    status, body = estate.call("GET", f"/ledger/events{query}")
    if status == 200 and isinstance(body, list):
        return body
    check(False, f"ledger read GET /ledger/events{query} failed (HTTP {status})")
    return None


def _count(estate: Estate, event_type: str, agent_id: str) -> int | None:
    events = _events(estate, event_type=event_type, agent_id=agent_id)
    return None if events is None else len(events)


def _canary_event_count(estate: Estate, canaries: frozenset) -> int | None:
    """Every live event of every canary agent, one read per agent; None if any read fails."""
    per_canary = [_events(estate, agent_id=a) for a in sorted(canaries)]
    return sum(len(evs) for evs in per_canary) if all(evs is not None for evs in per_canary) else None


def _gate_row_bracketed(gate: object, before: int | None, after: int | None) -> bool:
    """The pack's gate-verification row against canary counts read before and
    after the pack: non-vacuous (before >= 1) and before <= gate <= after, so
    an event appended between the reads is not a false red while a stale,
    zeroed or inflated row still fails."""
    return (isinstance(gate, int) and not isinstance(gate, bool)
            and before is not None and after is not None
            and before >= 1 and before <= gate <= after)


def _plus_one(before: int | None, after: int | None) -> bool:
    return before is not None and after is not None and after == before + 1


def _ledger(estate: Estate) -> list[dict] | None:
    """The whole ledger, accepted only when the three ledger routes describe
    the same chain. Race-tolerant on a busy estate: read /health FIRST (count
    c, head h), then /events, then /verify - appends can only lengthen, so
    require c <= len(events) <= verify.length and events[c-1].hash == h."""
    s1, health = estate.call("GET", "/ledger/health", auth=False)
    status, events = estate.call("GET", "/ledger/events")
    _, verify = estate.call("GET", "/ledger/verify")
    if status != 200 or not isinstance(events, list) or s1 != 200 or not isinstance(health, dict):
        check(False, f"GET /ledger/events failed (HTTP {status}; /ledger/health HTTP {s1})")
        return None
    n, c, head = len(events), health.get("event_count"), health.get("head_hash")
    v_ok = isinstance(verify, dict) and verify.get("ok") is True
    v_len = verify.get("length") if isinstance(verify, dict) else None
    at = (GENESIS if c == 0 else events[c - 1].get("hash")) if isinstance(c, int) and 0 <= c <= n else None
    ok = v_ok and at is not None and at == head and isinstance(v_len, int) and v_len >= n
    check(ok, f"ledger consistent: verify ok={v_ok}; /health {c} <= /events {n} <= /verify {v_len}; "
              f"/events[{c}-1].hash {str(at)[:16]} == /health head {str(head)[:16]}")
    return events if ok else None


def _require_canary(estate: Estate, agent: str, allowed: frozenset = CANARIES) -> dict:
    if agent not in allowed:
        _die(f"'{agent}' is not one of {sorted(allowed)} - mutating checks run on the canary only (rule 7)")
    status, rec = estate.call("GET", f"/registry/agents/{_q(agent)}")
    if status != 200 or not isinstance(rec, dict) or rec.get("agent_id") != agent \
            or rec.get("domain") != CANARY_DOMAIN:
        _die(f"registry record for '{agent}' is not a '{CANARY_DOMAIN}'-domain canary (HTTP {status})")
    return rec


def _require_token_of(estate: Estate, token: str, agent: str) -> None:
    status, tok = estate.call("GET", f"/delegation/tokens/{_q(token)}")
    if status != 200 or not isinstance(tok, dict) or tok.get("agent_id") != agent:
        _die(f"token is not a token of '{agent}' (HTTP {status}) - nothing was changed")


# -- subcommands ------------------------------------------------------------------


def _check_build_sha(path: str, body: Any, want: str) -> None:
    """One container on an old image is a failed deploy, not a detail."""
    got = body.get("build_sha") if isinstance(body, dict) else None
    shown = got if isinstance(got, str) and _SHA.match(got) else f"<{_shape(got)}, not shown>"
    if got == "unknown":
        shown = "'unknown'"
    check(got == want, f"{path} build_sha {shown} == deploy SHA {want[:12]}")


def cmd_health(estate: Estate, args: argparse.Namespace) -> int:
    prefixes = args.only.split(",") if args.only else list(SERVICES)
    for p in prefixes:
        if p not in SERVICES:
            _die(f"unknown prefix '{p}'")
    want_sha = args.expect_build_sha
    if want_sha is not None and not _SHA.match(want_sha):
        _die("--expect-build-sha must be the full 40- or 64-hex commit SHA the images were labelled with at build")
    print(f"health - {len(prefixes)} prefixes")
    for prefix in prefixes:
        status, body = estate.call("GET", f"/{prefix}/health", auth=False)
        service = body.get("service") if isinstance(body, dict) else None
        check(status == 200 and service == SERVICES[prefix],
              f"/{prefix}/health 200 service={service!r} (want {SERVICES[prefix]!r}, got HTTP {status})")
        if want_sha is not None:
            _check_build_sha(f"/{prefix}/health", body, want_sha)
    status, _ = estate.call("GET", "/", auth=False)
    check(status == 200, f"console shell / answers 200 (got {status})")
    if want_sha is not None:
        # The console owns the proxy root, so its /health is the bare /health.
        status, body = estate.call("GET", "/health", auth=False)
        service = body.get("service") if isinstance(body, dict) else None
        check(status == 200 and service == "ops-console",
              f"/health 200 service={service!r} (want 'ops-console', got HTTP {status})")
        _check_build_sha("/health", body, want_sha)
    if args.expect_perimeter and not estate.authenticated:
        check(False, "--expect-perimeter needs the secret: data routes cannot be verified without it")
    for prefix in prefixes:
        method, path, ok = DATA_ROUTES[prefix]
        body = {} if method == "POST" else None
        # Always checked: on a secretless estate the header is simply absent,
        # and a dead data route behind a healthy /health must still FAIL.
        label = "authenticated" if estate.authenticated else "open"
        status, _ = estate.call(method, path, body)
        check(status in ok, f"{label} {method} {path} serving {ok} (got {status})")
        if args.expect_perimeter:
            status, _ = estate.call(method, path, body, auth=False)
            check(status == 401, f"unauthenticated {method} {path} is 401 (got {status})")
    return finish()


def cmd_pin(estate: Estate, args: argparse.Namespace) -> int:
    events = _ledger(estate)
    if events is None or not events:
        print(json.dumps({"pin": None, "reason": "ledger unreadable, inconsistent or empty"}))
        return 1
    print(json.dumps({"event_count": len(events), "head_index": len(events) - 1,
                      "head_hash_prefix": events[-1].get("hash", "")[:16]}))
    return 0


def cmd_continuity(estate: Estate, args: argparse.Namespace) -> int:
    if args.count < 1 or not _HASH.match(args.hash):
        _die("--count must be >= 1 and --hash 16-64 lowercase hex chars (use the output of `pin`)")
    print(f"continuity - pin count={args.count} hash={args.hash[:16]}")
    events = _ledger(estate)
    if events is None:
        return finish()
    check(len(events) >= args.count, f"event_count {len(events)} >= pinned {args.count}")
    if len(events) >= args.count:
        at = events[args.count - 1].get("hash", "")
        check(at.startswith(args.hash), f"event[{args.count - 1}].hash {at[:16]} == pinned {args.hash[:16]}")
    return finish()


def _verdict(estate: Estate, agent: str, token: str, action: str) -> tuple[int, dict]:
    status, body = estate.call("POST", "/sentinel/check", {"agent_id": agent, "action": action, "token_id": token})
    return status, body if isinstance(body, dict) else {}


def _clause(verdict: dict) -> str | None:
    return verdict.get("clause_id") or None


def _heartbeat_killed(estate: Estate, agent: str) -> bool | None:
    status, hb = estate.call("GET", f"/killswitch/heartbeat/{_q(agent)}")
    return hb.get("killed") if status == 200 and isinstance(hb, dict) else None


def cmd_canary(estate: Estate, args: argparse.Namespace) -> int:
    agent, token = args.agent, args.token
    _require_canary(estate, agent)
    _require_token_of(estate, token, agent)
    print(f"canary C0 - {agent}")
    check(_heartbeat_killed(estate, agent) is False, "heartbeat 200 killed=false")
    before = _count(estate, "conformance.allow", agent)
    status, v = _verdict(estate, agent, token, "canary.probe")
    check(status == 200 and v.get("decision") == "ALLOW", f"/check canary.probe ALLOW (got {v.get('decision')} {_clause(v)})")
    check(_plus_one(before, _count(estate, "conformance.allow", agent)), "exactly +1 conformance.allow for the canary")
    before = _count(estate, "conformance.block", agent)
    status, v = _verdict(estate, agent, token, "canary.forbidden")
    check(status == 200 and v.get("decision") == "BLOCK" and _clause(v) == "D.scope",
          f"/check canary.forbidden BLOCK D.scope (got {v.get('decision')} {_clause(v)})")
    check(_plus_one(before, _count(estate, "conformance.block", agent)), "exactly +1 conformance.block for the canary")
    return finish()


def expected_window_signed(att_health) -> bool:
    """Whether a served windowed pack must be signed: only while /attest/health reports signing "on".
    "off" and "error" both serve unsigned drafts; an unreadable health answer is treated as off."""
    return isinstance(att_health, dict) and att_health.get("signing") == "on"


def cmd_catalogue(estate: Estate, args: argparse.Namespace) -> int:
    agent, token = args.agent, args.token
    _require_canary(estate, agent)
    _require_token_of(estate, token, agent)
    op = {"operator": "FIELD gate verification (canary)", "reason": "live catalogue check - canary only"}
    print(f"Phase A + B live catalogue - {agent}")

    # C4 serves the window: ?since= is a windowed range (never all-time relabelled as a window), and
    # only a window that is not one is refused 422. Since F4 the app signs every served pack with the
    # estate key while /attest/health says signing is "on" (A8 armed), so the window is expected signed
    # then and an unsigned draft only while signing is off. A pack that claims the opposite still fails.
    _, att_health = estate.call("GET", "/attest/health")
    want_signed = expected_window_signed(att_health)
    kind = "a signed" if want_signed else "an unsigned"
    status, windowed = estate.call("GET", "/attest/pack?since=2026-01-01")
    w = windowed.get("window") if isinstance(windowed, dict) else None
    check(status == 200 and isinstance(w, dict) and w.get("kind") == "range"
          and w.get("since") == "2026-01-01T00:00:00+00:00" and windowed.get("signed") is want_signed,
          f"A2 windowed pack ?since=2026-01-01 served 200 as {kind} range from 2026-01-01T00:00Z "
          f"(got HTTP {status}, kind={w.get('kind') if isinstance(w, dict) else None}, "
          f"signed={windowed.get('signed') if isinstance(windowed, dict) else None})")
    status, _ = estate.call("GET", "/attest/pack?period=2026-Q5")
    check(status == 422, f"A2 a bad window (?period=2026-Q5) refused 422 (got {status})")
    status, _ = estate.call("GET", "/crosswalk/frameworks")
    check(status == 200, f"A3 GET /crosswalk/frameworks 200 (got {status})")

    status, intro = estate.call("POST", "/delegation/oauth/introspect", form={"token": token})
    check(status == 200 and isinstance(intro, dict) and intro.get("active") is True
          and intro.get("sub") == agent and "canary.probe" in (intro.get("scope_list") or []),
          f"B2 introspect canary token active=true sub=canary scope has canary.probe (got {_shape(intro)})")
    status, junk = estate.call("POST", "/delegation/oauth/introspect",
                               form={"token": "00000000-0000-0000-0000-000000000000"})
    check(status == 200 and junk == {"active": False},
          f"B2 unknown token answers exactly {{\"active\": false}} (got {_shape(junk)})")

    status, hb = estate.call("POST", f"/killswitch/heartbeat/{_q(agent)}")
    seen = hb.get("last_seen") if status == 200 and isinstance(hb, dict) else None
    check(bool(seen), f"B3 POST check-in records last_seen (got HTTP {status})")
    status, live = estate.call("GET", "/killswitch/liveness?stale_after=3600")
    rows = [r for r in (live.get("live", []) if isinstance(live, dict) else []) if isinstance(r, dict)]
    check(status == 200 and any(r.get("agent_id") == agent and r.get("last_seen") == seen for r in rows),
          f"B3 /liveness lists {agent} with THIS check-in's last_seen")

    k0 = _count(estate, "kill.agent", agent)
    status, killed = estate.call("POST", f"/killswitch/kill/{_q(agent)}", op)
    er = killed.get("endpoint_result") if isinstance(killed, dict) else None
    outcome = er.get("outcome") if isinstance(er, dict) else None
    check(status == 200 and outcome == args.expect_endpoint,
          f"B3 kill 200 with endpoint_result outcome={outcome} (want {args.expect_endpoint}, "
          f"reason={er.get('reason') if isinstance(er, dict) else None})")
    check(_plus_one(k0, _count(estate, "kill.agent", agent)), "B3 exactly +1 kill.agent (the kill is audited)")
    check(_heartbeat_killed(estate, agent) is True, "B3 heartbeat 200 killed=true after the kill")
    status, v = _verdict(estate, agent, token, "canary.probe")
    check(status == 200 and v.get("decision") == "BLOCK" and _clause(v) == "E.kill_switch",
          f"B3 a killed canary's /check is BLOCK E.kill_switch (got {v.get('decision')} {_clause(v)})")

    r0 = _count(estate, "kill.revive", agent)
    status, _ = estate.call("POST", f"/killswitch/revive/{_q(agent)}", op)
    check(status == 200, f"B3 revive 200 (got {status})")
    check(_plus_one(r0, _count(estate, "kill.revive", agent)), "B3 exactly +1 kill.revive")
    check(_heartbeat_killed(estate, agent) is False, "B3 heartbeat 200 killed=false after revive")
    status, v = _verdict(estate, agent, token, "canary.probe")
    check(status == 200 and v.get("decision") == "ALLOW", f"B3 revived canary's /check is ALLOW (got {v.get('decision')} {_clause(v)})")

    d0 = _count(estate, "kill.drill.complete", agent)
    status, drill = estate.call("POST", f"/killswitch/drill/{_q(agent)}", op)
    check(status == 200 and isinstance(drill, dict) and drill.get("restored") is True
          and drill.get("restored_status") == "active",
          f"B3 drill restored=true restored_status=active (got HTTP {status})")
    check(_plus_one(d0, _count(estate, "kill.drill.complete", agent)), "B3 exactly +1 kill.drill.complete")
    check(_heartbeat_killed(estate, agent) is False, "B3 heartbeat 200 killed=false after the drill")

    # A2 AFTER the drill, so the canary row compared is never a vacuous 0 == 0.
    # C4 excludes the canaries from every governance metric: 'Kill drills
    # completed' must equal the recomputed NON-canary drills (on a test estate
    # that is 0 == 0, a consistency check only), and the non-vacuous check is
    # the gate-verification row against every canary event (>= 1: this drill).
    # A live estate can append a canary event while these reads run (a
    # scheduled sweep, a concurrent probe), so the pack is BRACKETED: canary
    # counts read before and after it, and the row must fall between them.
    canaries = CANARIES | RETIRED_CANARIES
    c_before = _canary_event_count(estate, canaries)
    status, pack = estate.call("GET", "/attest/pack")
    metrics: dict[str, Any] = {}
    if isinstance(pack, dict):
        for section in pack.get("sections", []) or []:
            for m in (section.get("metrics", []) or []) if isinstance(section, dict) else []:
                if isinstance(m, dict) and m.get("name"):
                    metrics[m["name"]] = m.get("value")
    drills = metrics.get("Kill drills completed")
    recomputed = _events(estate, event_type="kill.drill.complete")
    n = (sum(1 for e in recomputed if not (isinstance(e, dict) and e.get("agent_id") in canaries))
         if recomputed is not None else None)
    check(status == 200 and isinstance(drills, int) and n is not None and drills == n,
          f"A2 'Kill drills completed' {drills} == recomputed non-canary drills from the ledger {n}")
    gate = metrics.get(ATTEST_GATE_ROW)
    c_after = _canary_event_count(estate, canaries)
    check(status == 200 and _gate_row_bracketed(gate, c_before, c_after),
          f"A2 gate-verification row {gate} == recomputed canary events from the ledger "
          f"(between {c_before} read before and {c_after} after the pack; >= 1)")

    before = _count(estate, "registry.attested", agent)
    status, rec = estate.call("POST", f"/registry/agents/{_q(agent)}/attest",
                              {"attested_by": "FIELD gate verification (canary)"})
    check(status == 200 and isinstance(rec, dict) and rec.get("attested_at"), f"B4 attest canary 200 with attested_at set (got {status})")
    check(_plus_one(before, _count(estate, "registry.attested", agent)), "B4 exactly +1 registry.attested")
    status, _ = estate.call("POST", f"/registry/agents/{_q(agent)}/attest", {"attested_by": "   "})
    check(status == 422, f"B4 blank attester refused 422 (got {status})")
    return finish()


def cmd_refused_kill(estate: Estate, args: argparse.Namespace) -> int:
    agent = args.agent
    rec = _require_canary(estate, agent, RETIRED_CANARIES)
    print(f"refused kill - {agent} must be retired and the kill must be refused")
    if not check(rec.get("status") == "retired", f"{agent} is retired before the attempt (status={rec.get('status')})"):
        return finish()
    before = _count(estate, "kill.agent", agent)
    status, _ = estate.call("POST", f"/killswitch/kill/{_q(agent)}",
                            {"operator": "FIELD gate verification", "reason": "expect 409 for a retired agent"})
    check(status == 409, f"POST /killswitch/kill/{agent} refused 409 (got {status})")
    after = _count(estate, "kill.agent", agent)
    check(before is not None and after == before, "the refusal wrote no kill.agent event")
    status, rec = estate.call("GET", f"/registry/agents/{_q(agent)}")
    check(isinstance(rec, dict) and rec.get("status") == "retired", f"{agent} is still retired")
    return finish()


def cmd_revoke(estate: Estate, args: argparse.Namespace) -> int:
    _require_canary(estate, args.agent)
    _require_token_of(estate, args.token, args.agent)
    print(f"revoke canary token for {args.agent}")
    status, _ = estate.call("POST", f"/delegation/tokens/{_q(args.token)}/revoke")
    check(status == 200, f"revoke 200 (got {status})")
    status, intro = estate.call("POST", "/delegation/oauth/introspect", form={"token": args.token})
    check(status == 200 and intro == {"active": False},
          f"revoked token introspects as exactly {{\"active\": false}} (got {_shape(intro)})")
    return finish()


def _plain(value: Any) -> str:
    """A registry field safe to print: 1-128 printable ASCII characters with no
    whitespace (an id like 'x canary active' must not read as extra columns), or a
    placeholder. Nothing from a response is echoed unless it passes this."""
    clean = _clean(value)
    if clean is not None:
        return clean
    if isinstance(value, str):
        return f"<str-unsafe:len={len(value)}>"
    return f"<{_shape(value)}>"


def _registry_unreadable(why: str) -> int:
    print(f"UNREADABLE {why}")
    return EXIT_UNREADABLE


def cmd_registry(estate: Estate, args: argparse.Namespace) -> int:
    """READ-ONLY. One authenticated GET of the route `health` checks. Prints id, domain
    and status only. No _require_canary: nothing is changed. Exit 0 present, 1 absent
    (only after a read that succeeded and was well formed), 2 usage, 3 unreadable."""
    if args.agent is not None and _clean(args.agent) is None:
        _die(f"--agent must be 1-{_MAX_TEXT} printable ASCII characters with no whitespace")
    status, body = estate.call("GET", DATA_ROUTES["registry"][1])
    if status != 200 or not isinstance(body, list):
        return _registry_unreadable(f"GET /registry/agents (HTTP {status}, {_shape(body)}); "
                                    "the agent's presence is UNKNOWN")
    bad = [i for i, r in enumerate(body) if not isinstance(r, dict)]
    if bad:
        return _registry_unreadable(f"{len(bad)} of {len(body)} registry rows are not objects "
                                    f"(first at index {bad[0]}); the agent's presence is UNKNOWN")
    rows = body
    if args.agent is not None:
        match = [r for r in rows if r.get("agent_id") == args.agent]
        if not match:
            print(f"ABSENT {_plain(args.agent)}")
            return EXIT_ABSENT
        if len(match) > 1:
            return _registry_unreadable(f"the registry lists {_plain(args.agent)} {len(match)} times "
                                        "(ambiguous)")
        if _clean(match[0].get("status")) is None:
            return _registry_unreadable(f"{_plain(args.agent)} is listed with a status that is not "
                                        f"plain text ({_plain(match[0].get('status'))})")
        print(f"PRESENT {_plain(args.agent)} status={_plain(match[0].get('status'))}")
        return EXIT_PRESENT
    print(f"registry - {len(rows)} agents (id domain status)")
    for r in rows:
        print(f"  {_plain(r.get('agent_id'))} {_plain(r.get('domain'))} {_plain(r.get('status'))}")
    return 0


def cmd_collateral(estate: Estate, args: argparse.Namespace) -> int:
    events = _ledger(estate)
    if events is None:
        return finish()
    if not check(0 <= args.since <= len(events),
                 f"--since {args.since} is inside the ledger (length {len(events)})"):
        return finish()
    tail = events[args.since:]
    others: dict[tuple[str, str], int] = {}
    for ev in tail:
        agent = ev.get("agent_id") or "<none>"
        if agent not in CANARIES | RETIRED_CANARIES:
            key = (agent, ev.get("event_type", "?"))
            others[key] = others.get(key, 0) + 1
    print(f"collateral - {len(tail)} events since index {args.since}; {sum(others.values())} not about a canary")
    allowed = set(filter(None, (args.allow or "").split(",")))
    for (agent, etype), n in sorted(others.items()):
        intended = f"{agent}:{etype}" in allowed
        check(intended, f"{n} x {etype} for {agent}" + ("" if intended else " - NOT intended by this step"))
    if not others:
        check(True, "no events about a non-canary agent")
    return finish()


#: subcommand -> handler. tools/tests/test_estate_probe.py finds this by name.
HANDLERS = {
    "health": cmd_health, "pin": cmd_pin, "continuity": cmd_continuity,
    "canary": cmd_canary, "catalogue": cmd_catalogue, "refused-kill": cmd_refused_kill,
    "revoke": cmd_revoke, "collateral": cmd_collateral, "registry": cmd_registry,
}


def main(argv: list[str] | None = None) -> int:
    # allow_abbrev=False: "--operator-key VALUE" must never be taken for --operator-key-file
    parser = argparse.ArgumentParser(description="Live verification of a FIELD estate.", allow_abbrev=False)
    parser.add_argument("--base", required=True)
    parser.add_argument("--secret-file")
    parser.add_argument("--allow-plaintext", action="store_true",
                        help="permit http:// to a non-loopback, non-private host with the secret")
    parser.add_argument("--operator-id", metavar="ID",
                        help="operator id, sent only on guarded routes (default: $FIELD_OPERATOR)")
    parser.add_argument("--operator-key-file", metavar="PATH",
                        help="file holding that operator's key; read and stripped here, never printed, "
                             "sent only on guarded routes (default: $FIELD_OPERATOR_KEY_FILE, else "
                             "$FIELD_OPERATOR_KEY)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("health")
    p.add_argument("--only")
    p.add_argument("--expect-perimeter", action="store_true")
    p.add_argument("--expect-build-sha", metavar="SHA",
                   help="every /health (and the console's) must report this build_sha")
    sub.add_parser("pin")
    p = sub.add_parser("continuity")
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--hash", required=True)
    for name in ("canary", "catalogue", "revoke"):
        p = sub.add_parser(name)
        p.add_argument("--agent", required=True)
        p.add_argument("--token", required=True)
        if name == "catalogue":
            p.add_argument("--expect-endpoint", required=True, choices=("called", "skipped", "failed"))
    p = sub.add_parser("refused-kill")
    p.add_argument("--agent", required=True)
    p = sub.add_parser("collateral")
    p.add_argument("--since", type=int, required=True)
    p.add_argument("--allow")
    p = sub.add_parser("registry", help="READ-ONLY: list agent id, domain, status (no tokens)")
    p.add_argument("--agent", metavar="ID",
                   help="exit 0 if this exact id is present, 1 if absent (read succeeded, id not "
                        "found), 3 if the registry could not be read or the answer is unexpected "
                        "(never treat 3 as absent), 2 on a bad id")

    args = parser.parse_args(argv)
    secret = _secret(args.secret_file)
    operator = operator_pair(args.operator_id, args.operator_key_file)
    key = operator[1] if operator else None
    if secret or key:
        sys.stdout, sys.stderr = _Redact(sys.stdout, secret, key), _Redact(sys.stderr, secret, key)
        parts = urllib.parse.urlsplit(args.base)
        host = parts.hostname or ""
        try:
            local = ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
        except ValueError:
            local = host == "localhost"
        if parts.scheme != "https" and not local and not args.allow_plaintext:
            _die("the secret or operator key would travel in cleartext: use https:// or a loopback/private "
                 "address")
    estate = Estate(args.base, secret, operator=operator)
    return HANDLERS[args.cmd](estate, args)


if __name__ == "__main__":
    raise SystemExit(main())
