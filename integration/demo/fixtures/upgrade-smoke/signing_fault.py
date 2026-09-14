#!/usr/bin/env python3
"""F2 fault-path proof (arming step A9, CI-proven only — never on a live estate).

    FIELD_SHARED_SECRET=... python3 signing_fault.py <base-url> <fixture-agent-id>

Standard library only (it runs on the bare CI runner, through the proxy).
Run by compose-upgrade-smoke after the ledger alone was recreated with
FIELD_LEDGER_SIGN_KEY pointing at a file that does not exist and
FIELD_LEDGER_REQUIRE_SIGNING=1 (the sentinel is in enforce mode). The
perimeter secret comes from the environment, never from argv, and is never
printed. Checks, each a PASS/FAIL line:

1. GET /ledger/health: appendable false, require_signing true (and signing
   "error" with a key_error — the path is set, the key is not loadable);
2. POST /sentinel/check for the fixture agent => BLOCK L.unreachable (the
   step-1 gate refuses a ledger that would refuse the allow record);
3. a start-type append, POST /ledger/events event_type registry.updated =>
   503 whose detail names FIELD_LEDGER_REQUIRE_SIGNING;
4. a stop-type append, event_type kill.agent for the fixture agent with
   payload {"reason": "F2 fault-path proof"} => 201 with signing_failed true
   and NO signature key;
5. GET /ledger/events shows that event with signing_failed and without
   signature, and /verify is still ok.

Exit 0 all passed, 1 any FAIL, 2 refused (usage, no secret).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

RESULTS: list[bool] = []


def check(ok: bool, label: str) -> bool:
    RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return bool(ok)


class Estate:
    def __init__(self, base: str, secret: str):
        self.base, self._secret = base.rstrip("/"), secret

    def call(self, method: str, path: str, body=None, auth: bool = True):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth:
            headers["x-field-auth"] = self._secret
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except OSError as exc:
            return 0, {"transport_error": type(exc).__name__}
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, None


def run(base: str, agent: str, secret: str) -> int:
    RESULTS.clear()
    e = Estate(base, secret)
    print(f"F2 fault path (require signing, unreadable key) - {base}")

    status, h = e.call("GET", "/ledger/health", auth=False)
    got = ({k: h.get(k) for k in ("appendable", "require_signing", "signing", "ok")}
           if isinstance(h, dict) else None)
    check(status == 200 and got == {"appendable": False, "require_signing": True,
                                    "signing": "error", "ok": True}
          and isinstance(h.get("key_error"), str) and "FIELD_LEDGER_SIGN_KEY" in h["key_error"],
          f"/ledger/health: appendable false, require_signing true, signing error with key_error "
          f"(got HTTP {status} {got})")

    status, v = e.call("POST", "/sentinel/check", {"agent_id": agent, "action": "upgrade.probe"})
    decision = (v.get("decision"), v.get("clause_id")) if isinstance(v, dict) else (None, None)
    check(status == 200 and decision == ("BLOCK", "L.unreachable"),
          f"/sentinel/check {agent} => BLOCK L.unreachable (got HTTP {status} {decision})")

    status, refused = e.call("POST", "/ledger/events", {"event_type": "registry.updated",
                                                          "agent_id": agent,
                                                          "payload": {"probe": "F2 start-type"}})
    detail = refused.get("detail") if isinstance(refused, dict) else None
    check(status == 503 and isinstance(detail, str) and "FIELD_LEDGER_REQUIRE_SIGNING" in detail,
          f"start-type append registry.updated => 503 naming FIELD_LEDGER_REQUIRE_SIGNING (got HTTP {status})")

    status, ev = e.call("POST", "/ledger/events", {"event_type": "kill.agent", "agent_id": agent,
                                                     "payload": {"reason": "F2 fault-path proof"}})
    event_id = ev.get("event_id") if isinstance(ev, dict) else None
    check(status == 201 and isinstance(ev, dict) and ev.get("signing_failed") is True
          and "signature" not in ev and ev.get("event_type") == "kill.agent" and ev.get("agent_id") == agent,
          f"stop-type append kill.agent => 201 with signing_failed true and no signature (got HTTP {status})")

    status, events = e.call("GET", f"/ledger/events?agent_id={urllib.parse.quote(agent)}&event_type=kill.agent")
    mine = [x for x in events if x.get("event_id") == event_id] if isinstance(events, list) else []
    s2, verify = e.call("GET", "/ledger/verify")
    check(status == 200 and len(mine) == 1 and mine[0].get("signing_failed") is True
          and "signature" not in mine[0] and mine[0].get("payload", {}).get("reason") == "F2 fault-path proof"
          and s2 == 200 and isinstance(verify, dict) and verify.get("ok") is True,
          f"GET /ledger/events shows the kill.agent event with signing_failed and no signature; "
          f"/verify ok (got HTTP {status}, {len(mine)} match, verify HTTP {s2})")

    passed = sum(RESULTS)
    print(f"{passed}/{len(RESULTS)} checks passed")
    return 0 if RESULTS and passed == len(RESULTS) else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: signing_fault.py <base-url> <fixture-agent-id>   (FIELD_SHARED_SECRET from env)",
              file=sys.stderr)
        return 2
    secret = os.environ.get("FIELD_SHARED_SECRET", "")
    if not secret or not secret.isascii() or not secret.isprintable() or any(c.isspace() for c in secret):
        print("refusing: FIELD_SHARED_SECRET must be set (printable ASCII, no whitespace); value not shown",
              file=sys.stderr)
        return 2
    return run(argv[0], argv[1], secret)


if __name__ == "__main__":
    raise SystemExit(main())
