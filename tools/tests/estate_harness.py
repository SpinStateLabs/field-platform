"""A local stand-in for a FIELD estate, for tools/tests/test_estate_probe.py.

Every service's REAL create_app() is mounted under the same prefixes Caddy
routes on the estates, with Caddy's handle_path semantics (the service sees
the path without its prefix). Faults can be switched on at runtime with
POST /__fault {"on": [...]}, so each estate_probe check is run against the
exact broken estate it exists to catch. Faults are off by default.

    python estate_harness.py PORT DATA_DIR [--secret]

With --secret, FIELD_SHARED_SECRET must be set in the environment. Test-only:
never point it at, or run it on, a real estate.
"""
from __future__ import annotations

import json
import os
import sys

port = int(sys.argv[1])
data_dir = sys.argv[2]
secret = "--secret" in sys.argv
SECRET = os.environ.get("FIELD_SHARED_SECRET", "") if secret else ""
if secret and not SECRET:
    raise SystemExit("--secret needs FIELD_SHARED_SECRET in the environment")

base = f"http://127.0.0.1:{port}"
os.environ.update({
    "FIELD_DATA_DIR": data_dir,
    "FIELD_REGISTRY_URL": f"{base}/registry",
    "FIELD_LEDGER_URL": f"{base}/ledger",
    "FIELD_DELEGATION_URL": f"{base}/delegation",
    "FIELD_SENTINEL_URL": f"{base}/sentinel",
    "FIELD_KILLSWITCH_URL": f"{base}/killswitch",
    "FIELD_GOVERNOR_URL": f"{base}/governor",
    "FIELD_REPLAY_URL": f"{base}/replay",
    "FIELD_CROSSWALK_URL": f"{base}/crosswalk",
    "FIELD_GATEWAY_URL": f"{base}/gateway",
    "FIELD_FEDERATION_URL": f"{base}/federation",
    "FIELD_LIFECYCLE_URL": f"{base}/lifecycle",
    "FIELD_ATTEST_URL": f"{base}/attest",
    "FIELD_MANIFEST_DIR": os.path.join(data_dir, "manifests"),
    "FIELD_SENTINEL_MODE": "enforce",
    "FIELD_LIFECYCLE_EVERY": "0",
})
if secret:
    os.environ["FIELD_SHARED_SECRET"] = SECRET
else:
    os.environ.pop("FIELD_SHARED_SECRET", None)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

from agent_registry.api import create_app as registry  # noqa: E402
from attestation_reporter.api import create_app as attest  # noqa: E402
from compliance_crosswalk.api import create_app as crosswalk  # noqa: E402
from conformance_sentinel.api import create_app as sentinel  # noqa: E402
from delegation_authority.api import create_app as delegation  # noqa: E402
from federation_broker.api import create_app as federation  # noqa: E402
from force_gateway.api import create_app as gateway  # noqa: E402
from incident_replay.api import create_app as replay  # noqa: E402
from kill_switch.api import create_app as killswitch  # noqa: E402
from lifecycle_manager.api import create_app as lifecycle  # noqa: E402
from ops_console.api import create_app as ops_console  # noqa: E402
from sealed_ledger.api import create_app as ledger  # noqa: E402
from spend_governor.api import create_app as governor  # noqa: E402
from field_core.clients import LedgerClient, RegistryClient, LedgerUnreachableError  # noqa: E402

FAULTS: set[str] = set()


class ToggleLedger(LedgerClient):
    """kill-switch's ledger client: appends silently fail when
    'ks_ledger_dead' is on (e.g. kill-switch process missing the secret)."""

    def append(self, event_type, payload, agent_id=None):
        if "ks_ledger_dead" in FAULTS:
            raise LedgerUnreachableError("simulated: 401 from ledger")
        return super().append(event_type, payload, agent_id)


class StaleRegistry(RegistryClient):
    """kill-switch's registry client: with 'ks_sees_retired_as_active' on, a
    retired agent reads as active to the kill-switch only (pre-B4 kill-switch,
    or a kill-switch pointed at a stale registry replica)."""

    def get_agent(self, agent_id):
        rec = super().get_agent(agent_id)
        if "ks_sees_retired_as_active" in FAULTS and rec.get("status") == "retired":
            rec = dict(rec, status="active")
        return rec


def _auth():
    return {"x-field-auth": SECRET} if secret else {}


async def _json(send, status, body):
    raw = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})


async def _answer(app, scope, receive):
    """Run the real app and return (status, parsed JSON body) instead of sending."""
    chunks, start = [], {}

    async def keep(msg):
        if msg["type"] == "http.response.start":
            start.update(msg)
        else:
            chunks.append(msg.get("body", b""))
    await app(scope, receive, keep)
    return start.get("status", 200), json.loads(b"".join(chunks) or b"null")


async def _read_body(receive) -> bytes:
    """The whole request body (for faults that rewrite or answer from it)."""
    chunks = []
    while True:
        msg = await receive()
        if msg["type"] != "http.request":
            break
        chunks.append(msg.get("body", b""))
        if not msg.get("more_body"):
            break
    return b"".join(chunks)


def _with_raw(scope, raw: bytes):
    """(scope, receive) that present `raw` as the whole request body."""
    done = False

    async def rewritten():
        nonlocal done
        if done:
            return {"type": "http.disconnect"}
        done = True
        return {"type": "http.request", "body": raw, "more_body": False}
    hdrs = [(k, v) for k, v in scope["headers"] if k != b"content-length"]
    hdrs.append((b"content-length", str(len(raw)).encode()))
    return dict(scope, headers=hdrs), rewritten


async def _replayable(receive):
    """Read the whole request body once; return a receive() that replays it."""
    messages = []
    while True:
        msg = await receive()
        messages.append(msg)
        if msg["type"] != "http.request" or not msg.get("more_body"):
            break

    def fresh():
        pending = list(messages)

        async def replay():
            return pending.pop(0) if pending else {"type": "http.disconnect"}
        return replay
    return fresh


class Fault:
    def __init__(self, name, app):
        self.name, self.app = name, app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        qs = scope.get("query_string", b"")
        n = self.name

        if path == "/health" and f"stale_build_sha_{n}" in FAULTS:
            # this one container was not recreated: still the previous image
            chunks, start = [], {}

            async def keep(msg):
                if msg["type"] == "http.response.start":
                    start.update(msg)
                else:
                    chunks.append(msg.get("body", b""))
            await self.app(scope, receive, keep)
            body = json.loads(b"".join(chunks))
            body["build_sha"] = "0" * 40
            return await _json(send, start.get("status", 200), body)

        if n == "ledger" and method == "GET" and path == "/events":
            if "ledger_events_500" in FAULTS:
                return await _json(send, 500, {"detail": "simulated"})
            if "ledger_events_500_unfiltered" in FAULTS and not qs:
                return await _json(send, 500, {"detail": "simulated"})
            if "ledger_events_truncated" in FAULTS and not qs:
                # e.g. a restored-from-snapshot volume / stale replica serving
                # /events while /verify and /health come from the live file
                chunks, start = [], {}

                async def cap(msg):
                    if msg["type"] == "http.response.start":
                        start.update(msg)
                    else:
                        chunks.append(msg.get("body", b""))
                await self.app(scope, receive, cap)
                evs = json.loads(b"".join(chunks))
                # Drop the newest event: truncation must bite at ANY ledger size,
                # or a small test estate passes the check it exists to fail.
                return await _json(send, 200, evs[:-1])
        if n == "killswitch" and method == "POST" and path.startswith("/heartbeat/") and "checkin_not_recorded" in FAULTS:
            agent = path.rsplit("/", 1)[-1]
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{base}/killswitch/heartbeat/{agent}", headers=_auth())
            hb = r.json()
            hb["last_seen"] = hb["checked_at"]  # claims a check-in, stores nothing
            return await _json(send, 200, hb)
        if n in ("killswitch", "ledger", "delegation") and "no_authn_except_registry" in FAULTS:
            # that service's process started WITHOUT FIELD_SHARED_SECRET: open to anyone
            hdrs = [(k, v) for k, v in scope["headers"] if k != b"x-field-auth"]
            hdrs.append((b"x-field-auth", SECRET.encode()))
            scope = dict(scope, headers=hdrs)
            return await self.app(scope, receive, send)
        if n == "registry" and path.startswith("/agents") and "registry_data_500" in FAULTS:
            return await _json(send, 500, {"detail": "simulated"})

        # --- compose-upgrade-smoke flow faults (tools/tests/test_upgrade_smoke_fixture.py):
        # each turns exactly one upgrade_flow.py check into a FAIL.
        if n == "registry" and "no_authn_registry" in FAULTS:
            # the registry process started WITHOUT FIELD_SHARED_SECRET: open to anyone
            hdrs = [(k, v) for k, v in scope["headers"] if k != b"x-field-auth"]
            hdrs.append((b"x-field-auth", SECRET.encode()))
            return await self.app(dict(scope, headers=hdrs), receive, send)
        if (n == "registry" and method == "GET" and path.startswith("/agents/")
                and "registry_unmigrated_rows" in FAULTS):
            # a registry that never ran the v1.2 migration: rows without attested_at/by
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict):
                body.pop("attested_at", None)
                body.pop("attested_by", None)
            return await _json(send, status, body)
        if n == "ledger" and method == "GET" and path == "/verify" and "ledger_verify_segmented" in FAULTS:
            # a ledger that rotated during the upgrade (the C2 verification keys appear)
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict):
                body.update(segments=2, archived_segments=0, verified_events=body.get("length"))
            return await _json(send, status, body)
        if n == "sentinel" and method == "POST" and path == "/check" and "sentinel_check_ledgered_twice" in FAULTS:
            # the check runs twice for one request (a retrying hop): two verdicts ledgered
            fresh = await _replayable(receive)
            await _answer(self.app, scope, fresh())
            return await self.app(scope, fresh(), send)
        if (n == "governor" and method == "GET" and path == "/status/legacy-fixture-agent"
                and "governor_spend_unmigrated" in FAULTS):
            # a governor whose store never ran the D1 migration: its action query fails on the 7-column spend table
            return await _json(send, 500, {"detail": "simulated: sqlite3.OperationalError: no such column: action"})
        if n == "governor" and method == "POST" and path == "/spend" and "sentinel_metering_as_self" in FAULTS:
            # the sentinel's metered rows land as self-reports (A+B attribution lost); the window still fills
            raw = await _read_body(receive)
            body = json.loads(raw or b"null")
            if isinstance(body, dict) and body.get("source") == "sentinel":
                body["source"] = "self"
                raw = json.dumps(body).encode()
            done = False

            async def rewritten():
                nonlocal done
                if done:
                    return {"type": "http.disconnect"}
                done = True
                return {"type": "http.request", "body": raw, "more_body": False}
            hdrs = [(k, v) for k, v in scope["headers"] if k != b"content-length"]
            hdrs.append((b"content-length", str(len(raw)).encode()))
            return await self.app(dict(scope, headers=hdrs), rewritten, send)
        if (n == "governor" and method == "PUT" and path.startswith("/rate-limits/")
                and "governor_rate_limits_ignored" in FAULTS):
            # a governor that acknowledges a rate-limit set as enforced and stores nothing
            body = json.loads(await _read_body(receive) or b"null") or {}
            rows = [{"action": r.get("action"), "max": r.get("max"), "period": r.get("period"),
                     "period_seconds": 3600, "status": "enforced"} for r in body.get("rate_limits", [])]
            return await _json(send, 200, {"agent_id": body.get("agent_id"), "rate_limits": rows})
        if n == "sentinel" and method == "POST" and path == "/check" and "sentinel_allow_as_block" in FAULTS:
            # a sentinel that answers BLOCK for what it ledgered as ALLOW
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict) and body.get("decision") == "ALLOW":
                body.update(decision="BLOCK", clause_id="E.kill_switch")
            return await _json(send, status, body)

        # --- phase_g_check faults (tools/tests/test_phase_g_check.py): each turns exactly
        # one phase_g_check check into a FAIL.
        if n == "killswitch" and method == "POST" and path.startswith(("/revive/", "/kill/")):
            hdrs = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
            if "edge_200_everything" in FAULTS:
                # an edge / proxy that answers 200 to every write and forwards nothing
                return await _json(send, 200, {"ok": True})
            if "strip_operator_headers" in FAULTS:
                # a proxy that drops the credential: every request looks anonymous
                scope = dict(scope, headers=[(k, v) for k, v in scope["headers"]
                                             if not k.startswith(b"x-field-operator")])
            if FAULTS & {"revive_echo_headers", "forbidden_oracle", "fail_open_403", "fail_open_400",
                         "key_into_ledger", "collateral_event", "revive_leaves_killed", "refusal_still_writes",
                         "kill_503_after_apply", "revive_503", "bare_400_body", "bare_401_body",
                         "kill_after_first_revive", "collateral_other_canary", "collateral_retired_canary",
                         "kill_report_wrong_operator", "logonly_refuses", "nocred_503", "longkey_503", "enforce_ledgers_unauth", "full_hash_fp_event"}:
                anon = "x-field-operator" not in hdrs and "x-field-operator-key" not in hdrs
                if "nocred_503" in FAULTS and anon and path.startswith("/revive/"):
                    return await _json(send, 503, {"detail": "simulated"})
                if ("longkey_503" in FAULTS and path.startswith("/revive/")
                        and len(hdrs.get("x-field-operator-key", "")) > 256):
                    return await _json(send, 503, {"detail": "simulated"})
                if "revive_503" in FAULTS and path.startswith("/revive/") and hdrs.get("x-field-operator") == "don":
                    return await _json(send, 503, {"detail": "simulated: upstream unavailable"})
                status, body = await _answer(self.app, scope, receive)
                if "revive_echo_headers" in FAULTS and isinstance(body, dict):
                    body["echo"] = hdrs  # an upstream that reflects request headers
                if "forbidden_oracle" in FAULTS and status == 403 and isinstance(body, dict):
                    body["detail"] = f"{body.get('detail')} ({hdrs.get('x-field-operator')})"
                if "kill_503_after_apply" in FAULTS and path.startswith("/kill/") and hdrs.get("x-field-operator") == "don":
                    status, body = 503, {"detail": "simulated: applied, then the answer was lost"}
                if ("kill_report_wrong_operator" in FAULTS and path.startswith("/kill/") and status == 200
                        and isinstance(body, dict)):
                    body["operator"] = "someone-else"
                if ("logonly_refuses" in FAULTS and status == 200 and path.startswith("/revive/")
                        and 0 < len(hdrs.get("x-field-operator-key", "")) <= 256):
                    status, body = 403, {"detail": "operator not authorised"}
                if "bare_400_body" in FAULTS and status == 400:
                    body = {"message": "bad request"}  # an edge / proxy refusal, not the guard's body
                if "bare_401_body" in FAULTS and status == 401:
                    body = {"message": "unauthorized"}
                if "kill_after_first_revive" in FAULTS and path.startswith("/revive/"):
                    # somebody halts the canary on purpose while the probe is running (one shot)
                    from field_core.authn import auth_headers
                    FAULTS.discard("kill_after_first_revive")
                    agent = path.rsplit("/", 1)[-1]
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.patch(f"{base}/registry/agents/{agent}", json={"status": "killed"},
                                          headers=auth_headers())
                    assert r.status_code == 200, r.text
                if "fail_open_403" in FAULTS and status == 403:
                    status, body = 200, {"agent_id": "x", "status": "active", "killed": False, "checked_at": "x"}
                if "fail_open_400" in FAULTS and status == 400:
                    status, body = 200, {"agent_id": "x", "status": "active", "killed": False, "checked_at": "x"}
                if ("revive_leaves_killed" in FAULTS and status == 200 and path.startswith("/revive/")
                        and "x-field-operator-key" in hdrs):
                    # an authenticated revive that answers 200 and then loses the flip
                    from field_core.authn import auth_headers
                    agent = path.rsplit("/", 1)[-1]
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.patch(f"{base}/registry/agents/{agent}", json={"status": "killed"},
                                          headers=auth_headers())
                    assert r.status_code == 200, r.text
                extra = []
                if "key_into_ledger" in FAULTS and "x-field-operator-key" in hdrs:
                    extra.append({"event_type": "debug.note", "payload": {"note": hdrs["x-field-operator-key"]},
                                  "agent_id": "canary-gb10"})
                if "collateral_event" in FAULTS and status == 200:
                    extra.append({"event_type": "bystander.touched", "payload": {}, "agent_id": "agent-bystander"})
                if "enforce_ledgers_unauth" in FAULTS and status == 401 and anon:
                    from field_core.authn import auth_headers as _svc
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.post(f"{base}/ledger/events", headers=_svc(), json={
                            "event_type": "operator.unauthenticated", "agent_id": None,
                            "payload": {"action": "revive", "path": path, "reason": "no_credential"}})
                    assert r.status_code == 201, r.text
                if "full_hash_fp_event" in FAULTS and anon and path.startswith("/revive/"):
                    from field_core.authn import auth_headers as _svc
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.post(f"{base}/ledger/events", headers=_svc(), json={
                            "event_type": "debug.note", "agent_id": "canary-gb10",
                            "payload": {"operator_key_fp": "0123456789abcdef" * 4}})
                    assert r.status_code == 201, r.text
                if "collateral_other_canary" in FAULTS and status == 200:
                    extra.append({"event_type": "bystander.touched", "payload": {}, "agent_id": "canary-fly"})
                if "collateral_retired_canary" in FAULTS and status == 200:
                    # a decommissioned canary authors an event during the run
                    extra.append({"event_type": "bystander.touched", "payload": {}, "agent_id": "canary-gb10-retired"})
                if "refusal_still_writes" in FAULTS and status in (401, 403):
                    # a guard that refuses and acts anyway
                    extra.append({"event_type": "kill.revive", "payload": {"operator": "x", "reason": "x"},
                                  "agent_id": "canary-gb10"})
                for ev in extra:
                    async with httpx.AsyncClient(timeout=10) as c:
                        r = await c.post(f"{base}/ledger/events", headers=_auth(), json=ev)
                    assert r.status_code == 201, r.text
                return await _json(send, status, body)
        if (n == "ledger" and method == "POST" and path == "/events"
                and FAULTS & {"ledger_drops_unauth", "ledger_drops_nocred_unauth", "ledger_drops_fp",
                                       "ledger_wrong_fp", "ledger_forges_attribution", "ledger_drops_claimed",
                                       "ledger_reason_nocred_wrong", "ledger_reason_badcred_wrong",
                                       "ledger_drops_kill_agent", "ledger_drops_kill_revive",
                                       "ledger_revive_foreign_operator", "ledger_revive_operator_field"}):
            raw = await _read_body(receive)
            ev = json.loads(raw or b"null")
            if ("ledger_drops_unauth" in FAULTS and isinstance(ev, dict)
                    and ev.get("event_type") == "operator.unauthenticated"):
                return await _json(send, 500, {"detail": "simulated"})
            pl = ev.get("payload") if isinstance(ev, dict) else None
            if ("ledger_drops_nocred_unauth" in FAULTS and isinstance(ev, dict)
                    and ev.get("event_type") == "operator.unauthenticated"
                    and isinstance(pl, dict) and pl.get("reason") == "no_credential"):
                return await _json(send, 500, {"detail": "simulated"})  # only the anonymous write goes unrecorded
            et = ev.get("event_type") if isinstance(ev, dict) else None
            if ("ledger_drops_kill_agent" in FAULTS and et == "kill.agent") or \
                    ("ledger_drops_kill_revive" in FAULTS and et == "kill.revive"):
                return await _json(send, 500, {"detail": "simulated"})
            if isinstance(pl, dict) and et == "kill.revive":
                if "ledger_forges_attribution" in FAULTS and pl.get("operator_id_authenticated") is None \
                        and "operator_id_authenticated" in pl:
                    pl["operator_id_authenticated"] = "don"
                if "ledger_drops_claimed" in FAULTS:
                    pl.pop("operator_claimed", None)
                if "ledger_revive_foreign_operator" in FAULTS:
                    pl["operator"] = "someone-else"   # the revives on the ledger are not this tool's writes
                if "ledger_revive_operator_field" in FAULTS:
                    pl["operator_claimed"] = None     # a payload a flags-off kill-switch never writes
            if isinstance(pl, dict) and et == "operator.unauthenticated":
                if "ledger_reason_nocred_wrong" in FAULTS and pl.get("reason") == "no_credential":
                    pl["reason"] = "bad_credential"
                if "ledger_reason_badcred_wrong" in FAULTS and pl.get("reason") == "bad_credential":
                    pl["reason"] = "no_credential"
            if isinstance(pl, dict) and pl.get("operator_key_fp"):
                if "ledger_drops_fp" in FAULTS:
                    del pl["operator_key_fp"]
                elif "ledger_wrong_fp" in FAULTS:
                    pl["operator_key_fp"] = "deadbeef"
            scope, receive = _with_raw(scope, json.dumps(ev).encode())
            return await self.app(scope, receive, send)

        if (n == "registry" and method == "GET" and path == "/agents/canary-gb10"
                and "registry_status_hides_kill" in FAULTS
                and not any(k.startswith(b"x-field-operator") for k, _ in scope["headers"])):
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict):
                body["status"] = "active"
            return await _json(send, status, body)
        if n == "ledger" and method == "GET" and path == "/health" and "ledger_health_500" in FAULTS:
            return await _json(send, 500, {"detail": "simulated"})
        if (n == "killswitch" and method == "GET" and path.startswith("/heartbeat/")
                and "heartbeat_500" in FAULTS):
            return await _json(send, 500, {"detail": "simulated"})

        if n == "delegation" and path == "/oauth/introspect" and "introspect_echo_headers" in FAULTS:
            hdrs = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
            return await _json(send, 200, {"active": False, "echo": hdrs})

        if n == "killswitch" and method == "POST" and path.startswith("/kill/") and "kill_200_noflip" in FAULTS:
            agent = path.rsplit("/", 1)[-1]
            return await _json(send, 200, {"agent_id": agent, "previous_status": "active",
                                           "status": "killed", "elapsed_ms": 1.0, "operator": "x",
                                           "reason": "x", "killed_at": "2026-09-12T00:00:00+00:00",
                                           "endpoint_result": {"outcome": "skipped", "reason": "allowlist_unset"}})
        if n == "killswitch" and method == "POST" and path.startswith("/revive/") and "revive_200_noflip" in FAULTS:
            agent = path.rsplit("/", 1)[-1]
            return await _json(send, 200, {"agent_id": agent, "status": "active", "killed": False,
                                           "checked_at": "2026-09-12T00:00:00+00:00"})

        if n == "killswitch" and method == "POST" and path.startswith("/drill/") and "drill_leaves_killed" in FAULTS:
            agent = path.rsplit("/", 1)[-1]
            await self.app(scope, receive, send)  # real drill, real restored=true
            async with httpx.AsyncClient(timeout=10) as c:  # ...then the restore is lost
                await c.patch(f"{base}/registry/agents/{agent}", json={"status": "killed"}, headers=_auth())
            return

        if (n == "ledger" and method == "GET" and path == "/events" and "canary_events_vanish" in FAULTS
                and b"agent_id=" in qs and b"event_type=" not in qs):
            # a ledger that lost every canary event: the per-agent reads come back empty
            return await _json(send, 200, [])

        if n == "attest" and path == "/health" and "attest_signing_on" in FAULTS:
            # an estate whose signing is armed (A8): health says on, and windowed packs come back signed
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict):
                body["signing"] = "on"
            return await _json(send, status, body)

        if n == "attest" and path == "/pack" and qs and "attest_signing_on" in FAULTS:
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict):
                body["signed"] = True
            return await _json(send, status, body)

        if n == "attest" and path == "/pack" and qs and "attest_window_signed" in FAULTS:
            # a windowed pack passed off as signed
            status, body = await _answer(self.app, scope, receive)
            if isinstance(body, dict):
                body["signed"] = True
            return await _json(send, status, body)

        if n == "attest" and path == "/pack" and not qs and "canary_event_after_pack" in FAULTS:
            # a live estate: a canary event lands after the pack was generated
            # and before the probe re-reads the ledger (a sweep, a second probe)
            status, body = await _answer(self.app, scope, receive)
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(f"{base}/ledger/events", headers=_auth(),
                                 json={"event_type": "canary.interleaved", "payload": {},
                                       "agent_id": "canary-gb10"})
            assert r.status_code == 201, r.text
            return await _json(send, status, body)

        if n == "attest" and path == "/pack" and "attest_ignores_window" in FAULTS:
            # a pack that drops ?since/?until/?period: all-time counts under the
            # window the caller asked for, and a bad window is never refused
            return await self.app(dict(scope, query_string=b""), receive, send)

        if n == "attest" and path == "/pack" and FAULTS & {"attest_drills_zero", "attest_drills_off_by_one",
                                                           "attest_gate_overcount"}:
            chunks, start = [], {}

            async def capture(msg):
                if msg["type"] == "http.response.start":
                    start.update(msg)
                else:
                    chunks.append(msg.get("body", b""))
            await self.app(scope, receive, capture)
            body = json.loads(b"".join(chunks) or b"null")
            if isinstance(body, dict):
                for s in body.get("sections", []):
                    for m in s.get("metrics", []):
                        # C4 (plan-named): the canary's drill is excluded from
                        # 'Kill drills completed' and counted in the gate-
                        # verification row, so THAT row is the count that must
                        # never pass as a hard-coded 0.
                        if ("attest_drills_zero" in FAULTS and m.get("name")
                                == "Gate-verification events (canary agents, excluded from every other figure)"):
                            m.update(value=0, status="ok", note="hard-coded (simulated bug)")
                        if ("attest_gate_overcount" in FAULTS and m.get("name")
                                == "Gate-verification events (canary agents, excluded from every other figure)"):
                            m.update(value=(m.get("value") or 0) + 1000, status="ok", note="overcounted (simulated bug)")
                        if "attest_drills_off_by_one" in FAULTS and m.get("name") == "Kill drills completed":
                            m.update(value=(m.get("value") or 0) + 1, status="ok", note="miscounted (simulated bug)")
            return await _json(send, start.get("status", 200), body)

        return await self.app(scope, receive, send)


class HandlePath:
    def __init__(self, prefix: str, app):
        self.prefix, self.app = prefix, app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            if path.startswith(self.prefix):
                scope = dict(scope, path=path[len(self.prefix):] or "/", root_path="")
                scope["raw_path"] = scope["path"].encode()
        await self.app(scope, receive, send)


# The console owns the proxy root on the estates: its shell at / and its own
# /health (which estate_probe --expect-build-sha reads) are the REAL app.
console = Fault("console", ops_console())


async def fault(request: Request):
    if request.method == "POST":
        body = await request.json()
        FAULTS.clear()
        FAULTS.update(body.get("on", []))
    return JSONResponse({"on": sorted(FAULTS)})


async def operator_env(request: Request):
    """Test-only: flip the Phase G flags and this process's service identity at
    runtime (every service shares this process's environment and reads the mode
    per call). Only FIELD_OPERATOR* names are accepted."""
    body = await request.json()
    for k, v in (body.get("env") or {}).items():
        if not k.startswith("FIELD_OPERATOR"):
            return JSONResponse({"detail": "only FIELD_OPERATOR* may be set"}, status_code=422)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return JSONResponse({"mode": sorted(k for k in os.environ if k.startswith("FIELD_OPERATOR"))})


# Sentinel B: identical service, but its registry URL is wrong (dead port), so
# every /check BLOCKs R.unregistered regardless of kill state.
_saved = os.environ["FIELD_REGISTRY_URL"]
os.environ["FIELD_REGISTRY_URL"] = "http://127.0.0.1:9/registry"
sentinel_b = sentinel()
os.environ["FIELD_REGISTRY_URL"] = _saved
sentinel_a = sentinel()


async def sentinel_switch(scope, receive, send):
    app = sentinel_b if "sentinel_wrong_registry" in FAULTS else sentinel_a
    await app(scope, receive, send)


def M(prefix, name, app):
    return Mount(prefix, app=HandlePath(prefix, Fault(name, app)))


routes = [
    Route("/__fault", fault, methods=["GET", "POST"]),
    Route("/__operator", operator_env, methods=["POST"]),
    M("/registry", "registry", registry()),
    M("/ledger", "ledger", ledger()),
    M("/delegation", "delegation", delegation()),
    M("/sentinel", "sentinel", sentinel_switch),
    M("/killswitch", "killswitch", killswitch(registry=StaleRegistry(), ledger=ToggleLedger())),
    M("/governor", "governor", governor()),
    M("/replay", "replay", replay()),
    M("/gateway", "gateway", gateway(mock=True) if "mock" in gateway.__code__.co_varnames else gateway()),
    M("/federation", "federation", federation()),
    M("/lifecycle", "lifecycle", lifecycle()),
    M("/attest", "attest", attest()),
    M("/crosswalk", "crosswalk", crosswalk()),
    Route("/", console),
    Route("/health", console),
]
uvicorn.run(Starlette(routes=routes), host="127.0.0.1", port=port, log_level="warning")
