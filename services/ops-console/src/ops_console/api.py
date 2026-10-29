"""FastAPI surface for ops-console.

Design rule: the console is a CLIENT, not an authority. Every mutation
proxies through the service that owns it (kill-switch, delegation-authority,
spend-governor), so every action lands on the sealed ledger exactly as if a
CLI operator had done it. The console adds zero new power — it only makes
existing power visible and reachable.

Aggregation follows the attestation-reporter rule: an unreachable service
renders as unavailable, never as a fabricated empty state.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from field_core import operator_auth, operator_health
from field_core.authn import HEADER as AUTH_HEADER, install as install_authn, shared_secret
from field_core.buildinfo import build_sha
from field_core.clients import (
    CallerSigner,
    LedgerUnreachableError,
    ManifestResolver,
    signed_append_body,
)
from ops_console import __version__

#: Phase G C-14: the console never holds an operator identity of its own. Any
#: of these set (non-blank) in its environment and it refuses to start; its
#: upstream clients carry ``x-field-auth`` only, and a human action carries the
#: signed-in human's pair, forwarded per request (``_operator_kw``).
OWN_IDENTITY_ENV = (operator_auth.ENV_OPERATOR, operator_auth.ENV_OPERATOR_KEY,
                    "FIELD_OPERATOR_KEY_FILE")


class ConsoleIdentityRefused(RuntimeError):
    """The console was started with an operator identity of its own."""


def own_identity_vars(env=None) -> list[str]:
    """Names (never values) of the OWN_IDENTITY_ENV variables set non-blank."""
    env = os.environ if env is None else env
    return [n for n in OWN_IDENTITY_ENV if (env.get(n) or "").strip()]


def refuse_own_identity(env=None) -> None:
    """Raise ConsoleIdentityRefused when the console has an identity of its own.
    The message names the variables only, never their values."""
    names = own_identity_vars(env)
    if names:
        raise ConsoleIdentityRefused(
            f"ops-console refuses to start: {', '.join(names)} set in its environment. "
            "The console never acts under an operator identity of its own; a human "
            "action carries the signed-in human's headers. Unset them.")


def _console_headers() -> dict[str, str]:
    """``x-field-auth`` only (when FIELD_SHARED_SECRET is set): never an
    operator pair, whatever the environment holds (C-14)."""
    secret = shared_secret()
    return {AUTH_HEADER: secret} if secret else {}


class ServiceClient:
    """Thin httpx-compatible wrapper with graceful failure. A client built
    here carries ``x-field-auth`` only, never an operator identity (C-14)."""

    def __init__(self, client=None, base_url: str | None = None,
                 env: str = "", default: str = ""):
        self._client = client
        self.base = (base_url or os.environ.get(env, default)).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                base_url=self.base, timeout=10.0, headers=_console_headers()
            )

    def get(self, path: str, **kw) -> tuple[int, Any]:
        try:
            resp = self._client.get(path, **kw)
            return resp.status_code, resp.json()
        except Exception as exc:
            return 0, str(exc)

    def post(self, path: str, **kw) -> tuple[int, Any]:
        try:
            resp = self._client.post(path, **kw)
            return resp.status_code, resp.json()
        except Exception as exc:
            return 0, str(exc)


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    source: str
    data: Any = None
    error: str | None = None


class Overview(BaseModel):
    generated_at: str
    agents: Section
    tokens: Section
    escalations: Section
    ledger_verify: Section
    recent_events: Section
    token_usage: Section


class OperatorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, description="Human operator — recorded")
    reason: str = Field(default="via ops-console", min_length=1)


class ResolveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(min_length=1)


class BulkAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["kill", "drill", "revive"]
    agent_ids: list[str] = Field(min_length=1, max_length=100)
    operator: str = Field(min_length=1, description="Human operator — recorded")
    reason: str = Field(default="via ops-console (bulk)", min_length=1)


class FleetHalt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, description="Human operator — recorded")
    reason: str = Field(min_length=1)
    confirm: Literal["HALT"] = Field(
        description="Must be the literal word HALT — a typed confirmation")
    domains: list[str] | None = Field(
        default=None, description="Default: every domain with a non-retired agent")


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    token_id: str | None = None
    irreversible: bool = False


#: Manifest viewer guard. The console reads a file named by a registrant-set
#: ``manifest_ref`` from a volume it shares with signing keys, so it serves
#: ONLY manifest-shaped files that really live under FIELD_MANIFEST_DIR.
MANIFEST_SUFFIXES = (".yaml", ".yml", ".json")
MANIFEST_MAX_BYTES = 256 * 1024

#: The twelve governance services, in Caddy prefix order (status strip).
PLATFORM_SERVICES = ("registry", "ledger", "delegation", "sentinel",
                     "killswitch", "governor", "replay", "crosswalk",
                     "gateway", "federation", "lifecycle", "attest")


class ManifestRefused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def guarded_manifest_path(manifest_dir: str | Path | None,
                          manifest_ref: str) -> Path:
    """Resolve ``manifest_ref`` to a readable manifest file or refuse.

    Refuses (403) when the manifest dir is not configured, when the real path
    (symlinks followed) escapes it, when the suffix is not a manifest suffix,
    or when the file is over MANIFEST_MAX_BYTES; 404 when nothing is there.
    """
    if not manifest_dir:
        raise ManifestRefused(403, "FIELD_MANIFEST_DIR is not configured")
    try:
        base = Path(manifest_dir).resolve(strict=True)
    except (OSError, ValueError):
        raise ManifestRefused(404, "manifest directory does not exist")
    path = Path(manifest_ref)
    if not path.is_absolute():
        path = base / path
    outside = ManifestRefused(403, "manifest_ref resolves outside FIELD_MANIFEST_DIR")
    # Containment BEFORE existence: answering 404 for an absent outside path
    # but 403 for a present one would be a file-existence oracle.
    try:
        if not path.resolve(strict=False).is_relative_to(base):
            raise outside
        real = path.resolve(strict=True)
    except (OSError, ValueError):
        raise ManifestRefused(404, "no manifest file at that ref")
    if not real.is_relative_to(base):  # a symlink inside pointing out
        raise outside
    if real.suffix.lower() not in MANIFEST_SUFFIXES or not real.is_file():
        raise ManifestRefused(403, "not a manifest file (.yaml/.yml/.json)")
    if real.stat().st_size > MANIFEST_MAX_BYTES:
        raise ManifestRefused(403, f"manifest larger than {MANIFEST_MAX_BYTES} bytes")
    return real


# A spreadsheet evaluates a cell that starts with one of these (C-200 F-C200-1,
# OWASP "CSV injection"): the CSV export prefixes a single quote.
CSV_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_LEADS):
        return "'" + value
    return value


#: Per-agent outcomes of a kill-switch domain kill (its DomainAgentResult.outcome).
DOMAIN_OUTCOMES = ("killed", "already_killed", "skipped_retired", "error")
#: Errored agents listed per domain in a fleet-halt answer (the count is exact).
MAX_LISTED_ERRORS = 50


def _domain_outcomes(data: Any) -> tuple[dict[str, int] | None, list[dict]]:
    """C-19: (counts per outcome, errored agents) from a kill-switch domain-kill
    answer. The per-agent ``results`` are read from the body, or from its
    ``detail`` when a non-2xx answer carries the report there. (None, []) when
    no per-agent results are present. An outcome this console does not know
    counts as an error, never as a success."""
    report = None
    for cand in (data, data.get("detail") if isinstance(data, dict) else None):
        if isinstance(cand, dict) and isinstance(cand.get("results"), list):
            report = cand
            break
    if report is None:
        return None, []
    counts = dict.fromkeys(DOMAIN_OUTCOMES, 0)
    errors: list[dict] = []
    for r in report["results"]:
        outcome = r.get("outcome") if isinstance(r, dict) else None
        if outcome in counts and outcome != "error":
            counts[outcome] += 1
            continue
        counts["error"] += 1
        if len(errors) < MAX_LISTED_ERRORS:
            r = r if isinstance(r, dict) else {}
            errors.append({"agent_id": r.get("agent_id"),
                           "error": r.get("error") or f"outcome {outcome!r}"})
    return counts, errors


def _drill_not_restored(data: Any) -> str | None:
    """C-19: why a drill answer is a failure although it came back 2xx (the
    agent was not restored), or None when ``restored`` is true."""
    if isinstance(data, dict) and data.get("restored") is True:
        return None
    d = data if isinstance(data, dict) else {}
    return (f"drill did not restore the agent (restored={d.get('restored')}, "
            f"restored_status={d.get('restored_status')})")


def _overview_digest(overview: dict) -> str:
    """Change detector for the stream: everything except the timestamp."""
    body = {k: v for k, v in overview.items() if k != "generated_at"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _page() -> str:
    root = resources.files("ops_console") / "static"
    return Path(str(root / "console.html")).read_text(encoding="utf-8")


def create_app(
    registry: ServiceClient | None = None,
    ledger: ServiceClient | None = None,
    delegation: ServiceClient | None = None,
    governor: ServiceClient | None = None,
    killswitch: ServiceClient | None = None,
    sentinel: ServiceClient | None = None,
    lifecycle: ServiceClient | None = None,
    attest: ServiceClient | None = None,
    crosswalk: ServiceClient | None = None,
    federation: ServiceClient | None = None,
    replay: ServiceClient | None = None,
    gateway: ServiceClient | None = None,
    manifest_dir: str | Path | None = None,
    stream_interval: float = 2.0,
    stream_keepalive: float = 15.0,
    max_streams: int | None = None,
) -> FastAPI:
    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI):
        # C-14: an ASGI server serving this app (``console serve``, or uvicorn
        # directly) fails startup when the console has an identity of its own.
        refuse_own_identity()
        yield

    app = FastAPI(
        title="ops-console",
        version=__version__,
        description="Dashboard over every governed agent (client, not authority).",
        lifespan=_lifespan,
    )
    # The HTML shell holds no data; /api/* requires the secret when set.
    install_authn(app, open_paths={"/"})
    if operator_auth.operator_headers() and operator_auth.mode() != operator_auth.ENFORCE:
        # The console forwards the HUMAN's headers; its own FIELD_OPERATOR is
        # never used for a human action. Setting it without REQUIRE is a
        # config that suggests otherwise.
        logging.getLogger("ops_console").warning(
            "FIELD_OPERATOR is set on the ops-console but FIELD_OPERATOR_REQUIRE is not: "
            "the console never acts under its own identity for a human action; unset it")

    app.state.registry = registry or ServiceClient(
        env="FIELD_REGISTRY_URL", default="http://127.0.0.1:8001")
    app.state.ledger = ledger or ServiceClient(
        env="FIELD_LEDGER_URL", default="http://127.0.0.1:8002")
    app.state.delegation = delegation or ServiceClient(
        env="FIELD_DELEGATION_URL", default="http://127.0.0.1:8003")
    app.state.governor = governor or ServiceClient(
        env="FIELD_GOVERNOR_URL", default="http://127.0.0.1:8006")
    app.state.killswitch = killswitch or ServiceClient(
        env="FIELD_KILLSWITCH_URL", default="http://127.0.0.1:8005")
    app.state.sentinel = sentinel or ServiceClient(
        env="FIELD_SENTINEL_URL", default="http://127.0.0.1:8004")
    app.state.replay = replay or ServiceClient(
        env="FIELD_REPLAY_URL", default="http://127.0.0.1:8007")
    app.state.crosswalk = crosswalk or ServiceClient(
        env="FIELD_CROSSWALK_URL", default="http://127.0.0.1:8008")
    app.state.gateway = gateway or ServiceClient(
        env="FIELD_GATEWAY_URL", default="http://127.0.0.1:8009")
    app.state.federation = federation or ServiceClient(
        env="FIELD_FEDERATION_URL", default="http://127.0.0.1:8010")
    app.state.lifecycle = lifecycle or ServiceClient(
        env="FIELD_LIFECYCLE_URL", default="http://127.0.0.1:8012")
    app.state.attest = attest or ServiceClient(
        env="FIELD_ATTEST_URL", default="http://127.0.0.1:8013")
    # No "." default: an unset dir means the viewer refuses, never that it
    # reads relative to wherever the console happened to start.
    app.state.manifest_dir = (manifest_dir if manifest_dir is not None
                              else os.environ.get("FIELD_MANIFEST_DIR") or None)
    app.state.max_streams = (max_streams if max_streams is not None
                             else int(os.environ.get("FIELD_CONSOLE_MAX_STREAMS", "8")))
    app.state.open_streams = 0

    def _section(client: ServiceClient, path: str, label: str,
                 **kw) -> Section:
        status, data = client.get(path, **kw)
        if status == 200:
            return Section(available=True, source=f"GET {client.base}{path}",
                           data=data)
        return Section(available=False, source=f"GET {client.base}{path}",
                       error=f"status {status}: {data}" if status else str(data))

    # F2b: the console's caller key (FIELD_LEDGER_CALLER_ID / _KEY, GB10:
    # ``console``), loaded once here. Its operator.refused records are signed
    # exactly like every other service's appends (signed_append_body): a
    # ledger with FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1 refuses an unsigned
    # operator.* record (it is not a stop type).
    refusal_signer = CallerSigner.from_env()

    class _RefusalLedger:
        """C-16: operator.refused over the console's own ledger client, which
        carries x-field-auth only (C-14); the ledger stores it self_reported."""

        def __init__(self, client: ServiceClient):
            self.client = client

        def append(self, event_type: str, payload: dict, agent_id: str | None = None) -> None:
            body = {"event_type": event_type, "payload": payload, "agent_id": agent_id}
            if refusal_signer is not None:
                raw = getattr(self.client, "_client", None)
                sent = dict(getattr(raw, "headers", None) or {})
                body = signed_append_body(refusal_signer, event_type, payload, agent_id, sent)
            status, _ = self.client.post("/events", json=body)
            if status != 201:
                raise LedgerUnreachableError(f"ledger append returned {status}",
                                             status_code=status or None)

    op_health = operator_health.install(
        app, ledger_getter=lambda a: _RefusalLedger(a.state.ledger))

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "ops-console", "version": __version__,
                "build_sha": build_sha(), **op_health.health_fields()}

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return _page()

    def _token_usage_section(agents_section: Section) -> Section:
        """Per-agent token usage + cost + rogue flags, from the governor."""
        gov = app.state.governor
        source = f"GET {gov.base}/usage/{{agent_id}} (per registered agent)"
        if not agents_section.available:
            return Section(available=False, source=source,
                           error="agents unavailable")
        rows = []
        for agent in agents_section.data:
            status, data = gov.get(f"/usage/{agent['agent_id']}")
            if status == 200 and (
                data.get("total_input_tokens") or data.get("total_output_tokens")
                or data.get("open_rogue_flags")
            ):
                rows.append(data)
        return Section(available=True, source=source, data=rows)

    def _build_overview() -> Overview:
        agents = _section(app.state.registry, "/agents", "agents")
        return Overview(
            generated_at=datetime.now(timezone.utc).isoformat(),
            agents=agents,
            tokens=_section(app.state.delegation, "/tokens", "tokens"),
            escalations=_section(app.state.governor, "/escalations", "escalations"),
            ledger_verify=_section(app.state.ledger, "/verify", "verify"),
            recent_events=_section(
                app.state.ledger, "/events", "events", params={"limit": 25}
            ),
            token_usage=_token_usage_section(agents),
        )

    @app.get("/api/overview", response_model=Overview)
    def overview() -> Overview:
        return _build_overview()

    @app.get("/api/stream")
    async def stream(request: Request,
                     frames: int | None = Query(default=None, ge=1)) -> Any:
        """Server-sent events: an ``overview`` frame on every change.

        The upstreams have no push, so this polls them every
        ``stream_interval`` seconds server-side and pushes only changes (plus
        a keep-alive comment). Behind the shared secret like every /api/*
        route: browsers read it with fetch(), which can send x-field-auth.
        ``frames`` bounds the stream (tests, diagnostics).
        """
        if app.state.open_streams >= app.state.max_streams:
            raise HTTPException(503, detail="stream limit reached — poll /api/overview")

        async def events():
            # Counted inside the generator: an unstarted generator never runs
            # its finally, so counting earlier would leak a slot per drop.
            app.state.open_streams += 1
            sent, last_digest, last_send = 0, None, time.monotonic()
            try:
                while frames is None or sent < frames:
                    if await request.is_disconnected():
                        break
                    o = (await asyncio.to_thread(_build_overview)).model_dump()
                    digest = _overview_digest(o)
                    now = time.monotonic()
                    if digest != last_digest:
                        last_digest, last_send = digest, now
                        sent += 1
                        yield f"event: overview\ndata: {json.dumps(o, default=str)}\n\n"
                    elif now - last_send >= stream_keepalive:
                        last_send = now
                        sent += 1
                        yield ": keep-alive\n\n"
                    if frames is None or sent < frames:
                        await asyncio.sleep(stream_interval)
            finally:
                app.state.open_streams -= 1

        return StreamingResponse(
            events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---- drill to details -------------------------------------------------

    @app.get("/api/agents/{agent_id}")
    def agent_detail(agent_id: str) -> dict:
        q = quote(agent_id, safe="")
        record = _section(app.state.registry, f"/agents/{q}", "agent")
        if not record.available and record.error and record.error.startswith("status 404"):
            raise HTTPException(404, detail=f"agent '{agent_id}' not registered")
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": record,
            "heartbeat": _section(app.state.killswitch, f"/heartbeat/{q}", "hb"),
            "tokens": _section(app.state.delegation, "/tokens", "tokens",
                               params={"agent_id": agent_id}),
            "usage": _section(app.state.governor, f"/usage/{q}", "usage"),
            "events": _section(app.state.ledger, "/events", "events",
                               params={"agent_id": agent_id, "limit": 50}),
        }

    @app.get("/api/agents/{agent_id}/manifest")
    def agent_manifest(agent_id: str) -> dict:
        """Read-only view of the agent's FIELD manifest, behind the path guard."""
        status, record = app.state.registry.get(f"/agents/{quote(agent_id, safe='')}")
        if status != 200:
            raise HTTPException(status or 502, detail=record)
        ref = record.get("manifest_ref")
        if not ref:
            return {"agent_id": agent_id, "ref": None, "validation": "no_ref",
                    "raw": None}
        try:
            path = guarded_manifest_path(app.state.manifest_dir, ref)
        except ManifestRefused as exc:
            raise HTTPException(exc.status, detail={
                "agent_id": agent_id, "ref": ref, "validation": "refused"
                if exc.status == 403 else "missing", "reason": exc.reason})
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise HTTPException(403, detail={
                "agent_id": agent_id, "ref": ref, "validation": "refused",
                "reason": f"unreadable: {type(exc).__name__}"})
        _, validation = ManifestResolver(path.parent).resolve_detail(str(path))
        return {"agent_id": agent_id, "ref": ref, "validation": validation,
                "raw": raw}

    # ---- newer-service panels ---------------------------------------------

    @app.get("/api/platform")
    def platform() -> dict:
        """Health of all twelve services plus the read panels of the newer
        ones. Fetched in parallel; each unreachable piece is marked, alone."""
        jobs = {f"health:{name}": (getattr(app.state, name), "/health")
                for name in PLATFORM_SERVICES}
        jobs.update({
            "lifecycle": (app.state.lifecycle, "/findings"),
            "federation": (app.state.federation, "/contracts"),
            "crosswalk": (app.state.crosswalk, "/staleness"),
        })
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {k: pool.submit(c.get, p) for k, (c, p) in jobs.items()}
            raw = {k: f.result() for k, f in futures.items()}

        def sec(key: str) -> Section:
            client, path = jobs[key]
            status, data = raw[key]
            src = f"GET {client.base}{path}"
            if status == 200:
                return Section(available=True, source=src, data=data)
            if key == "lifecycle" and status == 404:
                # Reachable, but no sweep has run yet: a fact, not an outage.
                return Section(available=True, source=src,
                               data={"no_sweep_yet": True, "detail": data})
            return Section(available=False, source=src,
                           error=f"status {status}: {data}" if status else str(data))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health": {n: sec(f"health:{n}") for n in PLATFORM_SERVICES},
            "lifecycle": sec("lifecycle"),
            "federation": sec("federation"),
            "crosswalk": sec("crosswalk"),
            "attest": sec("health:attest"),
        }

    # ---- ledger filter + export -------------------------------------------

    def _ledger_events(agent_id, event_type, since, until, limit) -> list:
        params = {k: v for k, v in {
            "agent_id": agent_id, "event_type": event_type,
            "since": since, "until": until, "limit": limit}.items() if v}
        status, data = app.state.ledger.get("/events", params=params)
        if status != 200:
            raise HTTPException(status or 502, detail=data)
        return data

    @app.get("/api/events")
    def events(agent_id: str | None = None, event_type: str | None = None,
               since: str | None = None, until: str | None = None,
               limit: int = Query(default=100, ge=1, le=10000)) -> list:
        return _ledger_events(agent_id, event_type, since, until, limit)

    @app.get("/api/events/export")
    def export_events(format: Literal["csv", "json"] = "csv",
                      agent_id: str | None = None, event_type: str | None = None,
                      since: str | None = None, until: str | None = None,
                      limit: int = Query(default=1000, ge=1, le=10000)) -> Response:
        """Unsigned convenience copy of matching events. The evidence bundle
        is the ledger's own POST /export; this only saves what the screen shows."""
        rows = _ledger_events(agent_id, event_type, since, until, limit)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"field-ledger-{stamp}.{format}"
        disposition = {"Content-Disposition": f'attachment; filename="{name}"'}
        if format == "json":
            body = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": f"GET {app.state.ledger.base}/events",
                "filters": {"agent_id": agent_id, "event_type": event_type,
                            "since": since, "until": until, "limit": limit},
                "count": len(rows),
                "note": "unsigned convenience export from ops-console; a "
                        "filtered subset does not verify as a chain on its own. "
                        "Evidence bundles come from the ledger's POST /export.",
                "events": rows,
            }
            return Response(json.dumps(body, indent=2), media_type="application/json",
                            headers=disposition)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts", "event_id", "event_type", "agent_id", "clause_id",
                    "hash", "prev_hash", "payload_json"])
        for e in rows:
            payload = e.get("payload") or {}
            w.writerow([_csv_cell(c) for c in (
                e.get("ts"), e.get("event_id"), e.get("event_type"),
                e.get("agent_id") or "", payload.get("clause_id") or "",
                e.get("hash"), e.get("prev_hash"),
                json.dumps(payload, sort_keys=True))])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers=disposition)

    def _operator_kw(request: Request) -> dict:
        """Phase G: the HUMAN's operator headers are forwarded so the
        downstream service authenticates the human, not this console's
        service identity. Under REQUIRE a missing pair is a 401 here - the
        console never falls back to its own identity for a human action."""
        # C-16: a refusal here is counted and, under ENFORCE, ledgered as
        # operator.refused; the action is the route's last path segment.
        action = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        try:
            op, key = operator_auth.parse_headers(request.headers)
        except operator_auth.OperatorRefused as exc:
            raise op_health.http_refusal(exc, action=action, path=request.url.path,
                                         headers=request.headers,
                                         agent_id=request.path_params.get("agent_id")) from None
        if op and key:
            return {"headers": {operator_auth.HEADER_OPERATOR: op,
                                operator_auth.HEADER_KEY: key}}
        if operator_auth.mode() == operator_auth.ENFORCE:
            raise op_health.http_refusal(
                operator_auth.OperatorRefused(401, operator_auth.UNAUTH_DETAIL),
                action=action, path=request.url.path, headers=request.headers,
                agent_id=request.path_params.get("agent_id"))
        return {}

    def _proxy(client: ServiceClient, path: str, body: dict | None,
               ok_codes=(200, 201), **kw) -> Any:
        status, data = client.post(path, json=body, **kw)
        if status in ok_codes:
            return data
        raise HTTPException(status or 502, detail=data)

    @app.post("/api/agents/{agent_id}/kill")
    def kill(agent_id: str, action: OperatorAction, request: Request) -> Any:
        return _proxy(app.state.killswitch, f"/kill/{agent_id}",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/agents/{agent_id}/revive")
    def revive(agent_id: str, action: OperatorAction, request: Request) -> Any:
        return _proxy(app.state.killswitch, f"/revive/{agent_id}",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/agents/{agent_id}/drill")
    def drill(agent_id: str, action: OperatorAction, request: Request) -> Any:
        return _proxy(app.state.killswitch, f"/drill/{agent_id}",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/agents/bulk")
    def bulk(req: BulkAction, request: Request) -> dict:
        """Sequential per-agent calls to the kill-switch — one ledgered action
        each, exactly as if clicked one by one. A refusal is recorded for that
        agent and the rest continue."""
        results = []
        okw = _operator_kw(request)
        for agent_id in dict.fromkeys(req.agent_ids):  # de-dupe, keep order
            status, data = app.state.killswitch.post(
                f"/{req.action}/{quote(agent_id, safe='')}",
                json={"operator": req.operator, "reason": req.reason}, **okw)
            http_ok = status in (200, 201)
            row = {"agent_id": agent_id, "ok": http_ok, "status": status,
                   "result" if http_ok else "error": data}
            if http_ok and req.action == "drill":
                failed = _drill_not_restored(data)
                if failed:
                    # C-19: a drill that did not restore left the agent stopped;
                    # it is an error here, whatever the HTTP status said.
                    row["ok"], row["error"] = False, failed
            results.append(row)
        return {"action": req.action, "operator": req.operator,
                "all_ok": all(r["ok"] for r in results),
                "error_count": sum(1 for r in results if not r["ok"]),
                "results": results}

    @app.post("/api/fleet/halt")
    def fleet_halt(req: FleetHalt, request: Request) -> dict:
        """Kill every non-retired agent, domain by domain, through the
        kill-switch's own domain halt (POST /kill/domain/{d})."""
        okw = _operator_kw(request)
        domains = req.domains
        if not domains:
            status, agents = app.state.registry.get("/agents")
            if status != 200:
                raise HTTPException(502, detail=f"registry unavailable — cannot "
                                    f"enumerate domains: {agents}")
            domains = sorted({a.get("domain") or "general" for a in agents
                              if a.get("status") != "retired"})
        results = []
        for domain in dict.fromkeys(domains):
            status, data = app.state.killswitch.post(
                f"/kill/domain/{quote(domain, safe='')}",
                json={"operator": req.operator, "reason": req.reason}, **okw)
            http_ok = status in (200, 201)
            counts, errors = _domain_outcomes(data)
            # C-19: a domain is halted only when the HTTP answer was 2xx AND no
            # per-agent result is an error (a 200 with every agent errored is
            # not a halt).
            ok = http_ok and (counts is None or counts["error"] == 0)
            results.append({"domain": domain, "ok": ok, "status": status,
                            "counts": counts, "errors": errors,
                            "result" if http_ok else "error": data})
        return {"operator": req.operator, "domains": list(dict.fromkeys(domains)),
                "all_ok": all(r["ok"] for r in results),
                "agent_errors": sum(r["counts"]["error"] for r in results if r["counts"]),
                "domains_failed": sum(1 for r in results if not r["ok"]),
                "results": results}

    @app.post("/api/tokens/{token_id}/revoke")
    def revoke(token_id: str, request: Request) -> Any:
        return _proxy(app.state.delegation, f"/tokens/{token_id}/revoke", None,
                      **_operator_kw(request))

    @app.post("/api/escalations/{escalation_id}/resolve")
    def resolve(escalation_id: str, action: ResolveAction, request: Request) -> Any:
        return _proxy(app.state.governor,
                      f"/escalations/{escalation_id}/resolve",
                      action.model_dump(), **_operator_kw(request))

    @app.post("/api/check")
    def check(req: CheckRequest) -> Any:
        """Dry-run harness: ask the sentinel what WOULD happen. The verdict
        is real and lands on the ledger like any other check."""
        return _proxy(app.state.sentinel, "/check", req.model_dump())

    return app
