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

RULE 7 - CANARY-ONLY MUTATION. Every subcommand that changes estate state acts
only on the EXACT canary ids (canary-gb10, canary-fly), confirmed in the
registry as domain `canary`, with a token confirmed to belong to that canary.
`refused-kill` fires only at a decommissioned canary (canary-<estate>-retired),
so even a broken retired-guard can never halt a real agent.

READS NEVER PASS ON NOTHING. A failed ledger read is a FAIL, never an empty
list; the ledger's /health, /events and /verify must describe the same chain;
kill, revive and drill must each leave exactly one ledger event.

Exit status: 0 every check passed, 1 at least one check failed (or none ran),
2 refused (usage, rule 7, or an unsafe secret).

Subcommands (all take --base):
  health       every prefix /health names the right service, and one data route
               per service is serving; --expect-perimeter also requires 401
               without the header
  pin          ledger event count and head hash, only from a consistent ledger
  continuity   history up to a pinned (count, hash) is unchanged
  canary       C0 verdict checks on the canary
  catalogue    the Phase A + B live catalogue on the canary
  refused-kill a kill of a retired canary is refused 409 and ledgers nothing
  revoke       revoke the canary's token (end of every gate's live checks)
  collateral   every ledger event after --since that is not a canary's
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
GENESIS = "0" * 64
_HASH = re.compile(r"^[0-9a-f]{16,64}$")
RESULTS: list[tuple[bool, str]] = []


def _q(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def _die(msg: str) -> "None":
    print(f"refusing: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _shape(body: Any) -> str:
    """Never print a response body: it can reflect request headers."""
    if isinstance(body, dict):
        return "dict keys=" + ",".join(sorted(str(k) for k in body)[:12])
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


class _Redact:
    """Last line of defence: nothing written to stdout/stderr (tracebacks
    included) can carry the secret verbatim."""

    def __init__(self, stream, secret: str):
        self._s, self._needles = stream, {secret, repr(secret)[1:-1]}

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
    def __init__(self, base: str, secret: str | None, timeout: float = 20.0):
        self.base = base.rstrip("/")
        self._secret = secret
        self.timeout = timeout

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


def cmd_health(estate: Estate, args: argparse.Namespace) -> int:
    prefixes = args.only.split(",") if args.only else list(SERVICES)
    for p in prefixes:
        if p not in SERVICES:
            _die(f"unknown prefix '{p}'")
    print(f"health - {len(prefixes)} prefixes")
    for prefix in prefixes:
        status, body = estate.call("GET", f"/{prefix}/health", auth=False)
        service = body.get("service") if isinstance(body, dict) else None
        check(status == 200 and service == SERVICES[prefix],
              f"/{prefix}/health 200 service={service!r} (want {SERVICES[prefix]!r}, got HTTP {status})")
    status, _ = estate.call("GET", "/", auth=False)
    check(status == 200, f"console shell / answers 200 (got {status})")
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


def cmd_catalogue(estate: Estate, args: argparse.Namespace) -> int:
    agent, token = args.agent, args.token
    _require_canary(estate, agent)
    _require_token_of(estate, token, agent)
    op = {"operator": "FIELD gate verification (canary)", "reason": "live catalogue check - canary only"}
    print(f"Phase A + B live catalogue - {agent}")

    status, _ = estate.call("GET", "/attest/pack?since=2026-01-01")
    check(status == 422, f"A2 windowed pack request refused 422 until C4 (got {status})")
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

    # A2 AFTER the drill, so the compared number is never a vacuous 0 == 0.
    status, pack = estate.call("GET", "/attest/pack")
    metrics: dict[str, Any] = {}
    if isinstance(pack, dict):
        for section in pack.get("sections", []) or []:
            for m in (section.get("metrics", []) or []) if isinstance(section, dict) else []:
                if isinstance(m, dict) and m.get("name"):
                    metrics[m["name"]] = m.get("value")
    drills = metrics.get("Kill drills completed")
    recomputed = _events(estate, event_type="kill.drill.complete")
    n = len(recomputed) if recomputed is not None else None
    check(status == 200 and isinstance(drills, int) and n is not None and n >= 1 and drills == n,
          f"A2 'Kill drills completed' {drills} == recomputed from the ledger {n} (>= 1)")

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live verification of a FIELD estate.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--secret-file")
    parser.add_argument("--allow-plaintext", action="store_true",
                        help="permit http:// to a non-loopback, non-private host with the secret")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("health")
    p.add_argument("--only")
    p.add_argument("--expect-perimeter", action="store_true")
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

    args = parser.parse_args(argv)
    secret = _secret(args.secret_file)
    if secret:
        sys.stdout, sys.stderr = _Redact(sys.stdout, secret), _Redact(sys.stderr, secret)
        parts = urllib.parse.urlsplit(args.base)
        host = parts.hostname or ""
        try:
            local = ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_private
        except ValueError:
            local = host == "localhost"
        if parts.scheme != "https" and not local and not args.allow_plaintext:
            _die("the secret would travel in cleartext: use https:// or a loopback/private address")
    estate = Estate(args.base, secret)
    handler = {
        "health": cmd_health, "pin": cmd_pin, "continuity": cmd_continuity,
        "canary": cmd_canary, "catalogue": cmd_catalogue, "refused-kill": cmd_refused_kill,
        "revoke": cmd_revoke, "collateral": cmd_collateral,
    }[args.cmd]
    return handler(estate, args)


if __name__ == "__main__":
    raise SystemExit(main())
