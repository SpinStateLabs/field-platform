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


class Fault:
    def __init__(self, name, app):
        self.name, self.app = name, app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        qs = scope.get("query_string", b"")
        n = self.name

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

        if n == "attest" and path == "/pack" and "attest_drills_zero" in FAULTS:
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
                        if m.get("name") == "Kill drills completed":
                            m.update(value=0, status="ok", note="hard-coded (simulated bug)")
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


async def console(request):
    return JSONResponse({"ok": True, "service": "ops-console"})


async def fault(request: Request):
    if request.method == "POST":
        body = await request.json()
        FAULTS.clear()
        FAULTS.update(body.get("on", []))
    return JSONResponse({"on": sorted(FAULTS)})


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
