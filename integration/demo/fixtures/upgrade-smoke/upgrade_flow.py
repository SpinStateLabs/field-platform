#!/usr/bin/env python3
"""The positive flow CI's compose-upgrade-smoke runs on the upgraded stack.

    FIELD_SHARED_SECRET=... python3 upgrade_flow.py --base URL --pin PIN.json

Standard library only (it runs on the bare CI runner). Every call goes through
the proxy at --base with `x-field-auth`; the secret is read from the
environment and never printed, and no response body is echoed. Run after
make_fixture.py wrote the old-schema /data and the current images started on
it with both rosters armed. Checks, each a FAIL line if it does not hold:

1. the perimeter is on: an unauthenticated write is 401;
2. the pre-v1.2 registry row still serves, now with the migrated attested_at;
3. the lifecycle roster is armed (FIELD_LIFECYCLE_ROSTER reached the service);
4. register -> cap -> mint -> /sentinel/check is ALLOW for the fixture agent,
   with the DOA roster armed: an off-roster grantor is refused 403 D.grantor
   first, the rostered mint is ledgered with doa_checked=true, and an action
   outside the scope BLOCKs D.scope (so ALLOW is not a blanket answer);
5. the ledger verifies, is still ONE file (no segments keys: nothing rotated),
   and still holds the fixture's head hash at the fixture's head index.

Exit 0 all passed, 1 a check failed, 2 refused (usage, no secret, bad pin).
The same script runs locally against the real services in
tools/tests/test_upgrade_smoke_fixture.py, which also runs it on estates with
one fault injected per check (each must turn exactly that check into a FAIL)
and uses --agent to run it more than once on one estate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

AGENT = "upgrade-smoke-agent"
LEGACY = "legacy-fixture-agent"
GRANTOR = "FIELD CI (compose-upgrade-smoke)"
ACTION = "upgrade.probe"
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


def _clause(body) -> str | None:
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail.get("clause_id") if isinstance(detail, dict) else None


def run(base: str, pin: dict, manifest_ref: str, secret: str, agent: str = AGENT) -> int:
    RESULTS.clear()  # one run, one verdict: never a previous run's FAIL
    e = Estate(base, secret)
    print(f"compose-upgrade-smoke flow - {base}")

    status, _ = e.call("POST", "/registry/agents", {"agent_id": "perimeter-probe", "name": "x",
                                                     "owner": "x", "domain": "ci"}, auth=False)
    check(status == 401, f"perimeter on: unauthenticated POST /registry/agents is 401 (got {status})")

    status, legacy = e.call("GET", f"/registry/agents/{LEGACY}")
    check(status == 200 and isinstance(legacy, dict) and "attested_at" in legacy
          and legacy["attested_at"] is None and legacy.get("status") == "active",
          f"pre-v1.2 registry row {LEGACY} served with migrated attested_at=None (got HTTP {status})")

    status, lh = e.call("GET", "/lifecycle/health", auth=False)
    check(status == 200 and isinstance(lh, dict) and lh.get("roster_configured") is True,
          f"lifecycle roster armed: roster_configured=true (got HTTP {status})")

    status, _ = e.call("POST", "/registry/agents", {"agent_id": agent, "name": "Upgrade smoke",
                                                     "owner": GRANTOR, "domain": "ci",
                                                     "manifest_ref": manifest_ref})
    check(status == 201, f"register {agent} 201 (got {status})")
    status, _ = e.call("PUT", f"/governor/caps/{agent}", {"agent_id": agent, "currency": "USD",
                                                          "limit_cents": 100, "period": "daily",
                                                          "on_breach": "halt"})
    check(status == 200, f"cap {agent} 200 (got {status})")

    status, refused = e.call("POST", "/delegation/tokens", {"agent_id": agent,
                                                            "granted_by": "Off Roster (upgrade smoke)",
                                                            "scope": [ACTION], "ttl_seconds": 600})
    check(status == 403 and _clause(refused) == "D.grantor",
          f"DOA roster armed: off-roster mint 403 D.grantor (got {status} {_clause(refused)})")
    status, token = e.call("POST", "/delegation/tokens", {"agent_id": agent, "granted_by": GRANTOR,
                                                          "scope": [ACTION], "ttl_seconds": 600})
    token_id = token.get("token_id") if isinstance(token, dict) else None
    check(status == 201 and bool(token_id), f"rostered mint 201 with a token (got {status})")

    status, v = e.call("POST", "/sentinel/check", {"agent_id": agent, "action": ACTION,
                                                   "token_id": token_id})
    decision = (v.get("decision"), v.get("clause_id")) if isinstance(v, dict) else (None, None)
    check(status == 200 and decision == ("ALLOW", None), f"/sentinel/check {ACTION} ALLOW (got {status} {decision})")
    status, v = e.call("POST", "/sentinel/check", {"agent_id": agent, "action": "upgrade.forbidden",
                                                   "token_id": token_id})
    decision = (v.get("decision"), v.get("clause_id")) if isinstance(v, dict) else (None, None)
    check(status == 200 and decision == ("BLOCK", "D.scope"),
          f"/sentinel/check upgrade.forbidden BLOCK D.scope (got {status} {decision})")

    s1, verify = e.call("GET", "/ledger/verify")
    s2, events = e.call("GET", "/ledger/events")
    if not (s1 == 200 and isinstance(verify, dict) and s2 == 200 and isinstance(events, list)):
        check(False, f"ledger readable (verify HTTP {s1}, events HTTP {s2})")
        return _finish()
    check(verify.get("ok") is True, "ledger verify ok")
    check("segments" not in verify, "ledger still one file: /verify carries no segments keys")
    check(verify.get("length") == len(events), f"/verify length {verify.get('length')} == /events {len(events)}")
    head_index = pin["head_index"]
    at = events[head_index].get("hash") if len(events) > head_index else None
    check(len(events) > pin["event_count"] and at == pin["head_hash"],
          f"fixture head {pin['head_hash'][:16]} still at index {head_index}; "
          f"{len(events)} events > fixture {pin['event_count']}")
    mints = [ev for ev in events if ev.get("event_type") == "delegation.mint" and ev.get("agent_id") == agent]
    check(len(mints) == 1 and mints[0].get("payload", {}).get("doa_checked") is True,
          f"exactly one delegation.mint for {agent}, doa_checked=true (got {len(mints)})")
    allows = [ev for ev in events if ev.get("event_type") == "conformance.allow" and ev.get("agent_id") == agent]
    check(len(allows) == 1, f"exactly one conformance.allow for {agent} (got {len(allows)})")
    return _finish()


def _finish() -> int:
    passed = sum(RESULTS)
    print(f"{passed}/{len(RESULTS)} checks passed")
    return 0 if RESULTS and passed == len(RESULTS) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", required=True)
    p.add_argument("--pin", required=True, help="JSON pin: the last line make_fixture.py printed")
    p.add_argument("--manifest-ref", default=f"/data/manifests/{AGENT}.yaml")
    p.add_argument("--agent", default=AGENT,
                   help="agent id to register (default %(default)s; the manifest stays --manifest-ref)")
    args = p.parse_args(argv)
    secret = os.environ.get("FIELD_SHARED_SECRET", "")
    if not secret or not secret.isascii() or not secret.isprintable() or any(c.isspace() for c in secret):
        print("refusing: FIELD_SHARED_SECRET must be set (printable ASCII, no whitespace); value not shown",
              file=sys.stderr)
        return 2
    try:
        with open(args.pin, encoding="utf-8") as fh:
            pin = json.loads(fh.read().strip().splitlines()[-1])
        assert isinstance(pin["event_count"], int) and isinstance(pin["head_index"], int)
        assert isinstance(pin["head_hash"], str) and len(pin["head_hash"]) == 64
    except (OSError, ValueError, KeyError, IndexError, AssertionError):
        print("refusing: --pin is not the JSON pin make_fixture.py printed", file=sys.stderr)
        return 2
    return run(args.base, pin, args.manifest_ref, secret, args.agent)


if __name__ == "__main__":
    raise SystemExit(main())
