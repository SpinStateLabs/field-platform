"""FastAPI surface for kill-switch.

Ordering rule (ENFORCED, and deliberately the *opposite* of
delegation-authority): the kill happens first, the ledger is told after,
best-effort. A halt must never wait on — or be refused because of — an
audit outage. The asymmetry is the design: authority creation is
ledger-first fail-closed; authority destruction is act-first.

Propagation model: killing = flipping the agent's registry status. The
conformance-sentinel reads the registry on every /check, so a killed agent
fails its next check instantly. Agents also poll /heartbeat and must halt
on killed=true.

Agent-side halt signal (v1.2): after the registry flip the service
best-effort calls the agent's own ``enforcement.kill_switch.endpoint`` from
the manifest the registry record points at. This is a SIGNAL, not a process
stop — see README "Enforced vs. Declared". Two guards make it safe:

* **SSRF allowlist (mandatory).** ``FIELD_KILL_ENDPOINT_ALLOWLIST`` is read
  per call; unset or blank means NO call is ever made. The host compared is
  ``urlsplit(endpoint).hostname`` by EXACT string match — never a substring
  or suffix test, which ``http://allowed.host@169.254.169.254/`` (userinfo)
  and ``allowed.host.evil.com`` (suffix) both defeat. Non-http(s) schemes
  are skipped (this is what a FIELD 1.1.0 ``method: file`` kill switch
  becomes). The endpoint URL is NEVER echoed into the report or the ledger —
  host only, because a URL can carry credentials.
* **Self-call guard (mandatory, two independent mechanisms).** Every
  manifest this service can resolve today points back at its own
  ``/kill/{agent}``; without a guard a kill recurses. The outbound call
  carries ``x-field-kill-origin: kill-switch`` and an incoming request
  carrying that header never signals onward; independently, an endpoint
  whose path ends in ``/kill/{agent_id}`` or contains ``/kill/domain/`` is
  skipped. The path heuristic alone would false-skip a legitimate
  third-party hook that happens to use that path shape, which is why the
  header exists too.

Retired agents (v1.2 B4): ``retired`` is the end of an agent's life, written
by ``lifecycle decommission``. A retired agent is ALREADY non-active — the
heartbeat says ``killed=true`` and the sentinel blocks it — so ``/kill``
would gain nothing and ``/revive`` would silently undo a decommission with
one click. Both answer **409** instead; a domain kill skips retired agents
and records that it did.

Heartbeat check-ins (v1.2): ``POST /heartbeat/{agent}`` records ``last_seen``
in a small SQLite store and answers with the same semantics as the GET.
``GET /heartbeat`` never writes. ``GET /liveness`` reports which
registry-active agents have not checked in inside a window. Stale means "no
check-in in the window" — NOT evidence that the process is dead.
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
from pydantic import BaseModel, ConfigDict, Field

from field_core.clients import (
    AgentNotRegisteredError,
    LedgerClient,
    RegistryClient,
    RegistryUnreachableError,
    resolve_manifest_detail,
)
from kill_switch import __version__
from kill_switch.store import HeartbeatStore

#: Header the service sends on every outbound halt signal, and short-circuits
#: on when an incoming kill request carries it. Half of the self-call guard.
ORIGIN_HEADER = "x-field-kill-origin"
ORIGIN_VALUE = "kill-switch"

#: Outbound halt-signal timeout. Serial across a domain kill: N agents cost
#: at most N x this. The CLI's `killswitch domain` timeout is 30 s, so a
#: domain of more than ~14 agents with dead endpoints can outlive the client.
ENDPOINT_TIMEOUT_S = 2.0

_KNOWN_METHODS = {"POST", "GET", "PUT", "PATCH", "DELETE"}
_URLISH = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://\S+")


class KillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, description="Human operator issuing the halt")
    reason: str = Field(min_length=1)


class EndpointResult(BaseModel):
    """Outcome of the best-effort agent-side halt signal.

    ``endpoint_host`` is the parsed hostname and nothing else: the full URL
    never leaves this function, because manifests may carry credentials in
    it.
    """

    outcome: str = Field(description="called | failed | skipped")
    reason: str | None = None
    endpoint_host: str | None = None
    method: str | None = None
    http_status: int | None = None
    elapsed_ms: float | None = None
    error: str | None = None


class KillReport(BaseModel):
    agent_id: str
    previous_status: str
    status: str = "killed"
    elapsed_ms: float
    operator: str
    reason: str
    killed_at: str
    endpoint_result: EndpointResult | None = None


class DomainAgentResult(BaseModel):
    """Per-agent outcome inside a domain kill. A registry fault on one agent
    is RECORDED here, never raised mid-loop — one broken agent must not stop
    the halt of the rest."""

    agent_id: str
    outcome: str = Field(description="killed | already_killed | skipped_retired | error")
    previous_status: str | None = None
    error: str | None = None
    endpoint_result: EndpointResult | None = None


class DomainKillReport(BaseModel):
    domain: str
    killed: list[str]
    already_killed: list[str]
    skipped_retired: list[str] = Field(
        default_factory=list,
        description="Retired agents the domain kill left alone (a retire is "
                    "not undone, and not repeated, by a domain halt)",
    )
    elapsed_ms: float
    operator: str
    reason: str
    results: list[DomainAgentResult] = Field(default_factory=list)


class Heartbeat(BaseModel):
    agent_id: str
    status: str
    killed: bool
    checked_at: str
    last_seen: str | None = None


class AgentLiveness(BaseModel):
    agent_id: str
    last_seen: str | None = None
    age_seconds: float | None = None
    status: str


class LivenessReport(BaseModel):
    stale_after_seconds: float
    checked_at: str
    stale: list[AgentLiveness]
    live: list[AgentLiveness]
    note: str = (
        "Stale = no check-in inside the window. It is NOT evidence that the "
        "process is dead, and a live row is only evidence that the agent "
        "POSTed a check-in."
    )


class DrillReport(BaseModel):
    agent_id: str
    kill_confirmed_ms: float = Field(
        description="Command received -> registry confirms status=killed"
    )
    heartbeat_confirmed_ms: float = Field(
        description="Command received -> heartbeat reports killed=true"
    )
    endpoint_confirmed_ms: float | None = Field(
        default=None,
        description="Command received -> agent endpoint answered; None unless called",
    )
    restored: bool
    restored_status: str
    total_ms: float
    endpoint_result: EndpointResult | None = None
    note: str = (
        "Drill: real kill, real propagation, then status restored. "
        "The 2 a.m. answer: one command, measured below."
    )


def _default_store_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "killswitch" / "heartbeats.sqlite3"


def new_endpoint_client() -> Any:
    """The outbound halt-signal client.

    ``follow_redirects=False`` is load-bearing, not decoration. The allowlist
    is checked against the URL in the manifest; if redirects were followed, an
    allowlisted host answering ``302 Location: http://169.254.169.254/`` would
    walk the signal straight to the metadata service the allowlist exists to
    keep it away from. httpx's current default is already False — pinning it
    here means a library default change, or an edit, cannot silently void the
    guarantee. Module-level so a test can assert on the real client.
    """
    import httpx

    return httpx.Client(timeout=ENDPOINT_TIMEOUT_S, follow_redirects=False)


def _allowlist() -> set[str]:
    """Read per call — an operator can arm or disarm the signal without a
    restart, and no test can leave it armed for the next one."""
    raw = os.environ.get("FIELD_KILL_ENDPOINT_ALLOWLIST", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _parse_method(raw: str | None) -> str | None:
    """``'HTTP POST'`` -> ``'POST'``. Anything unrecognised -> None."""
    if not raw:
        return None
    tokens = [t for t in str(raw).upper().replace("/", " ").split() if t]
    tokens = [t for t in tokens if not t.startswith("HTTP")]
    if len(tokens) == 1 and tokens[0] in _KNOWN_METHODS:
        return tokens[0]
    return None


def _scrub(text: Any, limit: int = 200) -> str:
    """Never let a URL (which may carry credentials) into a report or the
    ledger. Any scheme://... run is replaced wholesale."""
    return _URLISH.sub("<endpoint>", str(text))[:limit]


#: Path shapes served by THIS service. The recursion guard matches the shape,
#: not the agent id: a manifest that points at ``/heartbeat/<other-agent>``
#: used to slip past a guard that only recognised ``/kill/<this-agent>``, and
#: the outbound "halt signal" then forged a check-in for a different agent
#: which ``GET /liveness`` reported as live. A halt signal must never re-enter
#: this service by ANY route, whichever agent the path names.
_SELF_PATH_SHAPES = (
    "/kill/",
    "/revive/",
    "/drill/",
    "/heartbeat/",
    "/liveness",
    "/health",
)


def _is_self_endpoint(path: str, agent_id: str) -> bool:
    clean = path.rstrip("/") or "/"
    if clean.endswith(f"/kill/{agent_id}") or "/kill/domain/" in path:
        return True
    # Any segment boundary, so /agent/kill/x counts and /killswitchy does not.
    return any(
        shape in clean + "/" if shape.endswith("/") else clean.endswith(shape)
        for shape in _SELF_PATH_SHAPES
    )


def create_app(
    registry: RegistryClient | None = None,
    ledger: LedgerClient | None = None,
    heartbeats: HeartbeatStore | None = None,
    clock: Callable[[], datetime] | None = None,
    endpoint_client: Any | None = None,
) -> FastAPI:
    app = FastAPI(
        title="kill-switch",
        version=__version__,
        description="Registry-integrated halt for agents and domains (FIELD letter E).",
    )
    install_authn(app)
    app.state.registry = registry or RegistryClient()
    app.state.ledger = ledger or LedgerClient()
    # Lazy: a kill-switch that is never checked in to never creates a file.
    app.state.heartbeats = heartbeats
    app.state.clock = clock or (lambda: datetime.now(timezone.utc))
    app.state.endpoint_client = endpoint_client

    def _now() -> datetime:
        return app.state.clock()

    # Guards the lazy build only. Without it, concurrent first check-ins each
    # saw ``None`` and built their own HeartbeatStore -- one connection and
    # one ``_lock`` apiece on the same file, so the store lock serialised
    # nothing across them (tests/test_heartbeat_store_lazy_init.py).
    _hb_build_lock = threading.Lock()

    def _hb_store() -> HeartbeatStore:
        store = app.state.heartbeats
        if store is None:
            with _hb_build_lock:
                if app.state.heartbeats is None:
                    app.state.heartbeats = HeartbeatStore(_default_store_path())
                store = app.state.heartbeats
        return store

    def _endpoint_http() -> Any:
        if app.state.endpoint_client is None:
            app.state.endpoint_client = new_endpoint_client()
        return app.state.endpoint_client

    def _ledger_note(event_type: str, payload: dict, agent_id: str | None) -> None:
        try:
            app.state.ledger.append(event_type, payload=payload, agent_id=agent_id)
        except Exception:
            pass  # act-first: the kill already happened; audit gap is visible

    # -- agent-side halt signal ---------------------------------------------

    def _signal_endpoint(
        agent_id: str, record: dict, origin: str | None
    ) -> EndpointResult:
        """Best-effort call to the agent's own kill endpoint. NEVER raises;
        every refusal is an explicit ``skipped`` reason, never a silent pass."""
        if origin:
            # Our own outbound signal came back to us: stop the recursion.
            return EndpointResult(outcome="skipped", reason="self_endpoint")

        manifest, why = resolve_manifest_detail(record.get("manifest_ref"))
        if manifest is None:
            return EndpointResult(
                outcome="skipped",
                reason="no_manifest_ref" if why == "no_ref" else "manifest_unresolved",
            )
        try:
            endpoint = manifest.enforcement.kill_switch.endpoint
            raw_method = manifest.enforcement.kill_switch.method
        except AttributeError:  # pragma: no cover - schema guarantees both
            return EndpointResult(outcome="skipped", reason="no_endpoint")
        if not endpoint:  # pragma: no cover - schema enforces min_length=1
            return EndpointResult(outcome="skipped", reason="no_endpoint")

        parts = urlsplit(endpoint)
        if parts.scheme not in ("http", "https"):
            # Covers FIELD 1.1.0's `method: file` sentinel kill switches.
            return EndpointResult(outcome="skipped", reason="non_http_endpoint")
        host = parts.hostname
        if _is_self_endpoint(parts.path, agent_id):
            return EndpointResult(
                outcome="skipped", reason="self_endpoint", endpoint_host=host
            )
        allow = _allowlist()
        if not allow:
            return EndpointResult(
                outcome="skipped", reason="allowlist_unset", endpoint_host=host
            )
        # EXACT hostname match, and every weakening of it has a test:
        #   substring  -> http://allowed.host@169.254.169.254/ (userinfo)
        #   prefix     -> allowed.host.evil.com
        #   SUFFIX     -> notallowed.host, a separate registrable domain that
        #                 `.endswith("allowed.host")` accepts
        if host not in allow:
            return EndpointResult(
                outcome="skipped", reason="host_not_allowlisted", endpoint_host=host
            )
        method = _parse_method(raw_method)
        if method is None:
            return EndpointResult(
                outcome="skipped", reason="unsupported_method", endpoint_host=host
            )

        t0 = time.perf_counter()
        try:
            resp = _endpoint_http().request(
                method,
                endpoint,
                headers={ORIGIN_HEADER: ORIGIN_VALUE},
                timeout=ENDPOINT_TIMEOUT_S,
            )
        except Exception as exc:
            return EndpointResult(
                outcome="failed",
                reason="transport_error",
                endpoint_host=host,
                method=method,
                elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
                error=_scrub(f"{type(exc).__name__}: {exc}"),
            )
        elapsed = round((time.perf_counter() - t0) * 1000, 2)
        status = getattr(resp, "status_code", None)
        if status is not None and status >= 400:
            return EndpointResult(
                outcome="failed",
                reason="http_error",
                endpoint_host=host,
                method=method,
                http_status=status,
                elapsed_ms=elapsed,
            )
        return EndpointResult(
            outcome="called",
            endpoint_host=host,
            method=method,
            http_status=status,
            elapsed_ms=elapsed,
        )

    def _signal_and_ledger(
        agent_id: str, record: dict, origin: str | None, base: dict
    ) -> EndpointResult:
        result = _signal_endpoint(agent_id, record, origin)
        _ledger_note(
            f"kill.endpoint_{result.outcome}",
            {**base, **result.model_dump(exclude_none=True)},
            agent_id,
        )
        return result

    def _kill_one(
        agent_id: str,
        operator: str,
        reason: str,
        origin: str | None = None,
        extra: dict | None = None,
    ) -> KillReport:
        t0 = time.perf_counter()
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot kill: {exc}")
        previous = record.get("status", "<unknown>")
        if previous == "retired":
            # A retire is terminal. Flipping retired -> killed would let a
            # later /revive put a decommissioned agent back to `active`.
            raise HTTPException(
                409,
                f"agent '{agent_id}' is retired — a retired agent is already "
                "non-active and must not be flipped to 'killed' (a later "
                "/revive would undo the decommission)",
            )
        if previous != "killed":
            try:
                app.state.registry.set_status(agent_id, "killed")
            except RegistryUnreachableError as exc:
                raise HTTPException(502, f"registry unreachable — cannot kill: {exc}")
        # The signal is sent even on an idempotent re-kill: the flip is what
        # is idempotent, the halt signal is the whole point of repeating it.
        endpoint_result = _signal_and_ledger(
            agent_id, record, origin, {"operator": operator, "reason": reason}
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        report = KillReport(
            agent_id=agent_id,
            previous_status=previous,
            elapsed_ms=round(elapsed_ms, 2),
            operator=operator,
            reason=reason,
            killed_at=_now().isoformat(),
            endpoint_result=endpoint_result,
        )
        _ledger_note(
            "kill.agent",
            {"operator": operator, "reason": reason,
             "previous_status": previous, "elapsed_ms": report.elapsed_ms,
             **(extra or {})},
            agent_id,
        )
        return report

    def _heartbeat_for(agent_id: str) -> tuple[Heartbeat, str]:
        """Read-only heartbeat + the registry status string it came from."""
        checked_at = _now().isoformat()
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            # Unknown agents are told to stop: fail closed.
            return (
                Heartbeat(
                    agent_id=agent_id, status="unregistered", killed=True,
                    checked_at=checked_at,
                ),
                "unregistered",
            )
        status = record.get("status", "<unknown>")
        return (
            Heartbeat(
                agent_id=agent_id, status=status, killed=status != "active",
                checked_at=checked_at,
            ),
            status,
        )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "kill-switch", "version": __version__,
                "build_sha": build_sha()}

    @app.post("/kill/{agent_id}", response_model=KillReport)
    def kill_agent(agent_id: str, req: KillRequest, request: Request) -> KillReport:
        return _kill_one(
            agent_id, req.operator, req.reason,
            origin=request.headers.get(ORIGIN_HEADER),
        )

    @app.post("/kill/domain/{domain}", response_model=DomainKillReport)
    def kill_domain(domain: str, req: KillRequest, request: Request) -> DomainKillReport:
        t0 = time.perf_counter()
        origin = request.headers.get(ORIGIN_HEADER)
        try:
            agents = app.state.registry.list_agents(domain=domain)
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot kill: {exc}")
        if not agents:
            raise HTTPException(404, f"no agents registered in domain '{domain}'")
        killed: list[str] = []
        already: list[str] = []
        retired: list[str] = []
        results: list[DomainAgentResult] = []
        for record in agents:
            agent_id = record["agent_id"]
            if record.get("status") == "retired":
                # Skipped, not errored: a domain halt has nothing to do to an
                # agent whose life already ended, and must not reopen it.
                retired.append(agent_id)
                results.append(
                    DomainAgentResult(
                        agent_id=agent_id, outcome="skipped_retired",
                        previous_status="retired",
                    )
                )
                continue
            was_killed = record.get("status") == "killed"
            try:
                report = _kill_one(
                    agent_id, req.operator, req.reason,
                    origin=origin, extra={"domain": domain},
                )
            except HTTPException as exc:
                # Recorded, not raised: one broken agent must not abort the
                # halt of the rest, and the route stays 200.
                results.append(
                    DomainAgentResult(
                        agent_id=agent_id, outcome="error",
                        previous_status=record.get("status"),
                        error=f"{exc.status_code}: {exc.detail}",
                    )
                )
                continue
            if was_killed:
                already.append(agent_id)
            else:
                killed.append(agent_id)
            results.append(
                DomainAgentResult(
                    agent_id=agent_id,
                    outcome="already_killed" if was_killed else "killed",
                    previous_status=report.previous_status,
                    endpoint_result=report.endpoint_result,
                )
            )
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        _ledger_note(
            "kill.domain",
            {"operator": req.operator, "reason": req.reason,
             "domain": domain, "killed": killed,
             "skipped_retired": retired, "elapsed_ms": elapsed_ms},
            None,
        )
        return DomainKillReport(
            domain=domain, killed=killed, already_killed=already,
            skipped_retired=retired,
            elapsed_ms=elapsed_ms, operator=req.operator, reason=req.reason,
            results=results,
        )

    @app.post("/revive/{agent_id}", response_model=Heartbeat)
    def revive(agent_id: str, req: KillRequest) -> Heartbeat:
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot revive: {exc}")
        if record.get("status") == "retired":
            # The one that matters: without this, one console click undoes a
            # decommission and the agent is `active` again.
            raise HTTPException(
                409,
                f"agent '{agent_id}' is retired — reviving a decommissioned "
                "agent is not a kill-switch operation; register a new agent or "
                "have the owner re-provision it",
            )
        try:
            app.state.registry.set_status(agent_id, "active")
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot revive: {exc}")
        _ledger_note(
            "kill.revive", {"operator": req.operator, "reason": req.reason}, agent_id
        )
        return Heartbeat(
            agent_id=agent_id, status="active", killed=False,
            checked_at=_now().isoformat(),
        )

    @app.get("/heartbeat/{agent_id}", response_model=Heartbeat)
    def heartbeat(agent_id: str) -> Heartbeat:
        """Read-only. A poll is not a check-in and must never write."""
        return _heartbeat_for(agent_id)[0]

    @app.post("/heartbeat/{agent_id}", response_model=Heartbeat)
    def checkin(agent_id: str) -> Heartbeat:
        """Record a check-in, then answer with the SAME semantics as the GET.

        An unregistered check-in is recorded with status ``unregistered`` so
        a shadow agent nobody registered still surfaces — and is still told
        to halt."""
        hb, status = _heartbeat_for(agent_id)
        seen = _now()
        _hb_store().record(agent_id, seen, status)
        hb.last_seen = seen.isoformat()
        return hb

    @app.get("/liveness", response_model=LivenessReport)
    def liveness(stale_after: float = 300.0) -> LivenessReport:
        if stale_after <= 0:
            raise HTTPException(422, "stale_after must be > 0 seconds")
        try:
            agents = app.state.registry.list_agents(status="active")
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot report liveness: {exc}")
        now = _now()
        cutoff = now - timedelta(seconds=stale_after)
        rows = _hb_store().all()
        stale: list[AgentLiveness] = []
        live: list[AgentLiveness] = []
        for record in agents:
            agent_id = record["agent_id"]
            row = rows.get(agent_id)
            if row is None:
                # Never checked in: stale. last_seen null counts as stale.
                stale.append(
                    AgentLiveness(agent_id=agent_id, status=record.get("status", "<unknown>"))
                )
                continue
            last_seen = row["last_seen"]
            entry = AgentLiveness(
                agent_id=agent_id,
                last_seen=last_seen.isoformat(),
                age_seconds=round((now - last_seen).total_seconds(), 3),
                status=record.get("status", "<unknown>"),
            )
            (live if last_seen >= cutoff else stale).append(entry)
        return LivenessReport(
            stale_after_seconds=stale_after,
            checked_at=now.isoformat(),
            stale=stale,
            live=live,
        )

    @app.post("/drill/{agent_id}", response_model=DrillReport)
    def drill(agent_id: str, req: KillRequest, request: Request) -> DrillReport:
        t0 = time.perf_counter()
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        previous = record.get("status", "active")
        if previous == "retired":
            # The fourth status-writing route, and the one that made the other
            # three guards bypassable: a drill flips retired -> killed, and if
            # the restore then fails the record is left `killed`, which /revive
            # accepts. Drill-then-revive laundered a decommissioned agent back
            # to active. A drill on a decommissioned agent proves nothing.
            raise HTTPException(
                409,
                f"agent '{agent_id}' is retired — a drill on a decommissioned "
                "agent proves nothing and a failed restore would leave the "
                "record 'killed', which /revive accepts",
            )
        _ledger_note(
            "kill.drill.start", {"operator": req.operator, "reason": req.reason}, agent_id
        )

        restored = False
        restored_status = "<not restored>"
        # try/finally: an exception anywhere between the flip and the restore
        # must never leave the agent killed. The restore is itself guarded so
        # a failing restore reports `restored: false` instead of masking the
        # original error.
        try:
            app.state.registry.set_status(agent_id, "killed")
            kill_confirmed = None
            for _ in range(100):
                if app.state.registry.get_agent(agent_id).get("status") == "killed":
                    kill_confirmed = (time.perf_counter() - t0) * 1000
                    break
            if kill_confirmed is None:
                raise HTTPException(500, "drill failed: kill did not propagate")

            hb = _heartbeat_for(agent_id)[0]
            if not hb.killed:
                raise HTTPException(500, "drill failed: heartbeat still live")
            heartbeat_confirmed = (time.perf_counter() - t0) * 1000

            endpoint_result = _signal_and_ledger(
                agent_id, record, request.headers.get(ORIGIN_HEADER),
                {"operator": req.operator, "reason": req.reason, "drill": True},
            )
            endpoint_confirmed_ms = (
                round((time.perf_counter() - t0) * 1000, 2)
                if endpoint_result.outcome == "called"
                else None
            )
        finally:
            try:
                app.state.registry.set_status(agent_id, previous)
                restored_status = app.state.registry.get_agent(agent_id).get("status") or "<unknown>"
                restored = restored_status == previous
            except Exception as exc:
                restored = False
                restored_status = "<restore failed>"
                _ledger_note(
                    "kill.drill.restore_failed",
                    {"operator": req.operator, "target_status": previous,
                     "error": _scrub(f"{type(exc).__name__}: {exc}")},
                    agent_id,
                )

        total = (time.perf_counter() - t0) * 1000
        report = DrillReport(
            agent_id=agent_id,
            kill_confirmed_ms=round(kill_confirmed, 2),
            heartbeat_confirmed_ms=round(heartbeat_confirmed, 2),
            endpoint_confirmed_ms=endpoint_confirmed_ms,
            restored=restored,
            restored_status=restored_status,
            total_ms=round(total, 2),
            endpoint_result=endpoint_result,
        )
        _ledger_note(
            "kill.drill.complete",
            {"operator": req.operator,
             **report.model_dump(exclude={"note"}, exclude_none=True)},
            agent_id,
        )
        return report

    return app
