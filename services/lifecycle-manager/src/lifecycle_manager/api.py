"""FastAPI surface for lifecycle-manager (v1.2 A1) + the sweep scheduler.

Three things live here, deliberately in one module so the guard rails are
greppable in one place:

1. **Client builders** used by the app (the CLI builds its own; they are
   deliberately not shared yet — see SPEC non-goals) (``delegation_client``,
   ``killswitch_client``, ``build_engine``). Outbound calls carry
   ``auth_headers()``.
2. **The app**: ``GET /health`` (open), ``POST /sweep`` and ``GET /findings``
   (behind ``x-field-auth`` when ``FIELD_SHARED_SECRET`` is set). The last
   report is persisted at ``$FIELD_DATA_DIR/lifecycle/last_sweep.json``;
   roster-less scheduler ticks go to ``last_tick.json`` so they never
   overwrite the ``swept_at`` that proves a sweep ran.
3. **The scheduler**: ``run_every`` drives ``scheduled_tick`` on a daemon
   thread when ``--every`` / ``FIELD_LIFECYCLE_EVERY`` is set.

Auto-kill discipline (mirrors ``cli.py``): the kill-switch client is
constructed ONLY inside the request handler, ONLY when the body flag
``auto_kill_orphans`` is literally ``True`` (``StrictBool`` — no ``"true"``,
no ``1``). The scheduler passes ``auto_kill_orphans=False`` hard-coded and no
environment variable is consulted for it — a grep-guard test pins both.

Roster discipline: a sweep with no roster would orphan every agent, so
"no roster" is a 503 (served) or a *recorded* skipped tick (scheduled) —
never a silent empty sweep.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from field_core.authn import auth_headers
from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager import __version__
from lifecycle_manager.engine import (
    LifecycleEngine,
    SweepConfig,
    SweepReport,
    parse_roster,
)

log = logging.getLogger("lifecycle_manager")

ROSTER_ENV = "FIELD_LIFECYCLE_ROSTER"
EVERY_ENV = "FIELD_LIFECYCLE_EVERY"
NO_ROSTER_DETAIL = "no roster configured — set FIELD_LIFECYCLE_ROSTER or send roster_csv"
SCHEDULED_OPERATOR = "lifecycle-manager (scheduled)"


# --------------------------------------------------------------------------
# Shared client builders (CLI + app)
# --------------------------------------------------------------------------

def delegation_client() -> httpx.Client:
    return httpx.Client(
        base_url=os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003"),
        timeout=10.0,
        headers=auth_headers(),
    )


def killswitch_client() -> httpx.Client:
    """The ONLY place a kill-switch client is built. Callers must guard it
    behind the explicit auto-kill flag (CLI ``--auto-kill-orphans`` or the
    literal ``True`` body flag) — never a default, never an env var."""
    return httpx.Client(
        base_url=os.environ.get("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005"),
        timeout=10.0,
        headers=auth_headers(),
    )


def build_engine(
    registry: RegistryClient | None = None,
    delegation: Any = None,
    ledger: LedgerClient | None = None,
    killswitch: Any = None,
    retention: Any = None,
    witness: Any = None,
) -> LifecycleEngine:
    """Wire a LifecycleEngine; missing clients come from the FIELD_*_URL env.
    ``killswitch`` is passed through as given — None means "cannot kill".
    ``retention`` likewise: None means the retention policy is not checked
    (``lifecycle serve`` passes a LedgerClient)."""
    return LifecycleEngine(
        registry=registry or RegistryClient(),
        delegation=delegation if delegation is not None else delegation_client(),
        ledger=ledger or LedgerClient(),
        killswitch=killswitch,
        retention=retention,
        witness=witness,
    )


# --------------------------------------------------------------------------
# Request model
# --------------------------------------------------------------------------

class SweepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roster_csv: str | None = Field(
        default=None,
        description="owners.csv text (header with an 'owner' column). "
                    "Omit to use the file at FIELD_LIFECYCLE_ROSTER.",
    )
    expiry_days: int = Field(default=30, ge=1)
    reattest_days: int = Field(default=90, ge=1)
    operator: str = Field(default="lifecycle-manager (served)", min_length=1)
    auto_kill_orphans: StrictBool = Field(
        default=False,
        description="Kill active orphans via kill-switch. Must be the JSON "
                    "literal true — never a default, never an env var.",
    )

    @field_validator("roster_csv")
    @classmethod
    def _roster_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("roster_csv must not be blank (omit it to use FIELD_LIFECYCLE_ROSTER)")
        return v


class RosterUnavailable(Exception):
    """No usable roster: nothing in the body and no readable file configured."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


# --------------------------------------------------------------------------
# Persistence helpers ($FIELD_DATA_DIR/lifecycle/last_sweep.json)
# --------------------------------------------------------------------------

def findings_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "lifecycle" / "last_sweep.json"


def tick_path() -> Path:
    """Scheduler ticks that swept nothing are recorded HERE, never over
    last_sweep.json: `swept_at` from a real sweep is the only evidence that a
    sweep ran, and a daily roster-less tick would otherwise erase it."""
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "lifecycle" / "last_tick.json"


def _persist(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The sweep (one function shared by the handler and the scheduler)
# --------------------------------------------------------------------------

def _configured_roster_path(app: FastAPI) -> Path | None:
    raw = app.state.roster_path or os.environ.get(ROSTER_ENV) or None
    return Path(raw) if raw else None


def _resolve_roster(app: FastAPI, req: SweepRequest) -> str:
    if req.roster_csv is not None:
        text, source = req.roster_csv, "request body"
    else:
        path = _configured_roster_path(app)
        if path is None:
            raise RosterUnavailable(NO_ROSTER_DETAIL)
        if not path.is_file():
            raise RosterUnavailable(f"roster file not found: {path} ({ROSTER_ENV})")
        text, source = path.read_text(encoding="utf-8"), str(path)
    if not parse_roster(text):
        # An owner-less roster would orphan every agent — refuse loudly.
        raise RosterUnavailable(f"roster from {source} contains no owners — refusing an empty sweep")
    return text


def run_sweep(app: FastAPI, req: SweepRequest) -> SweepReport:
    """Sweep with the app's clients and persist the report. Raises
    ``RosterUnavailable`` when there is nothing to sweep against."""
    roster_csv = _resolve_roster(app, req)

    killswitch = None
    if req.auto_kill_orphans is True:
        # The one and only arming point on the served path.
        killswitch = app.state.killswitch or killswitch_client()

    engine = build_engine(
        registry=app.state.registry,
        delegation=app.state.delegation,
        ledger=app.state.ledger,
        killswitch=killswitch,
        retention=app.state.retention,
        witness=app.state.witness,
    )
    report = engine.sweep(
        roster_csv=roster_csv,
        config=SweepConfig(
            expiry_horizon_days=req.expiry_days,
            reattestation_days=req.reattest_days,
            auto_kill_orphans=req.auto_kill_orphans,
            operator=req.operator,
        ),
        now=app.state.clock() if app.state.clock else None,
    )
    _persist(app.state.findings_path, report.model_dump(mode="json"))
    return report


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------

def scheduled_tick(app: FastAPI) -> dict[str, Any]:
    """One scheduler tick. Auto-kill is hard-coded OFF; nothing here can arm
    it. Logs and records outcomes; NEVER raises (Fly's ``wait -n`` would take
    the machine down on a child exit)."""
    try:
        req = SweepRequest(operator=SCHEDULED_OPERATOR, auto_kill_orphans=False)
        report = run_sweep(app, req)
        log.info(
            "lifecycle tick: swept %d agents / %d tokens — %d expiring, %d re-attest, %d orphans",
            report.agents_scanned, report.tokens_scanned,
            len(report.expiring), len(report.reattestation_due), len(report.orphans),
        )
        return {"ok": True, "swept_at": report.swept_at}
    except RosterUnavailable as exc:
        log.warning("lifecycle tick skipped: no roster (%s)", exc.detail)
        marker = {
            "skipped": True,
            "reason": "no roster",
            "detail": exc.detail,
            "at": datetime.now(timezone.utc).isoformat(),
            "operator": SCHEDULED_OPERATOR,
        }
        try:
            _persist(app.state.tick_path, marker)
        except Exception:
            log.exception("lifecycle tick: could not persist skipped marker")
        try:
            app.state.ledger.append(
                "lifecycle.tick_skipped",
                payload={"reason": "no roster", "detail": exc.detail,
                         "operator": SCHEDULED_OPERATOR},
                agent_id=None,
            )
        except Exception:
            log.warning("lifecycle tick: ledger unreachable for skipped marker")
        return marker
    except Exception as exc:  # noqa: BLE001 — the loop must survive anything
        log.exception("lifecycle tick failed")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def run_every(
    fn: Callable[[], Any],
    seconds: float,
    stop_event: threading.Event,
    sleep: Callable[[float], Any] | None = None,
) -> int:
    """Call ``fn`` every ``seconds`` until ``stop_event`` is set. First tick
    fires AFTER the first interval. A raising ``fn`` is logged and the loop
    continues. ``sleep`` is injectable for tests; the default waits on the
    stop event so shutdown is immediate. Returns the number of ticks fired."""
    wait = sleep if sleep is not None else stop_event.wait
    ticks = 0
    while not stop_event.is_set():
        wait(seconds)
        if stop_event.is_set():
            break
        ticks += 1
        try:
            fn()
        except Exception:  # noqa: BLE001 — never let a tick kill the thread
            log.exception("lifecycle scheduler: tick raised; continuing")
    return ticks


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

def create_app(
    registry: RegistryClient | None = None,
    delegation: Any = None,
    ledger: LedgerClient | None = None,
    killswitch: Any = None,
    roster_path: str | os.PathLike[str] | None = None,
    every: int | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    retention: Any = None,
    witness: Any = None,
) -> FastAPI:
    """``killswitch`` is an injection seam for tests: it is USED only when a
    request carries ``auto_kill_orphans: true``; it is never consulted by the
    scheduler. ``clock`` freezes ``now`` for deterministic tests.
    ``retention``: an object with ``retention_check()`` (``lifecycle serve``
    passes a LedgerClient); None (the default) = the retention policy is not
    checked. Deliberately not built here from the environment. ``witness``: a
    ``WitnessWatch`` (``lifecycle serve`` builds it from FIELD_WITNESS_EVERY);
    None (the default) = this estate runs no witness."""
    if every is None:
        raw = os.environ.get(EVERY_ENV, "").strip()
        every = int(raw) if raw.isdigit() else 0
    every = int(every or 0)
    if every < 0:
        every = 0

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if app.state.every > 0:
            app.state.scheduler_thread = threading.Thread(
                target=run_every,
                args=(app.state.tick, app.state.every, app.state.scheduler_stop),
                name="lifecycle-scheduler",
                daemon=True,
            )
            app.state.scheduler_thread.start()
            log.info(
                "lifecycle scheduler armed: every %d s (first tick after the interval; "
                "roster %s)", app.state.every,
                "configured" if _configured_roster_path(app) else "NOT configured — ticks will be recorded as skipped",
            )
        try:
            yield
        finally:
            app.state.scheduler_stop.set()

    app = FastAPI(
        title="lifecycle-manager",
        version=__version__,
        description="Authority hygiene sweeps, served (FIELD letters I + D).",
        lifespan=_lifespan,
    )
    install_authn(app)

    app.state.registry = registry or RegistryClient()
    app.state.delegation = delegation if delegation is not None else delegation_client()
    app.state.ledger = ledger or LedgerClient()
    app.state.killswitch = killswitch
    app.state.retention = retention
    app.state.witness = witness
    app.state.roster_path = str(roster_path) if roster_path else None
    app.state.every = every
    app.state.clock = clock
    app.state.findings_path = findings_path()
    app.state.tick_path = tick_path()
    app.state.scheduler_stop = threading.Event()
    app.state.scheduler_thread = None
    app.state.tick = lambda: scheduled_tick(app)

    @app.get("/health")
    def health() -> dict:
        path = _configured_roster_path(app)
        return {
            "ok": True,
            "service": "lifecycle-manager",
            "version": __version__,
            "roster_configured": bool(path and path.is_file()),
            "every": app.state.every,
            "build_sha": build_sha(),
        }

    @app.post("/sweep", response_model=SweepReport)
    def sweep(req: SweepRequest) -> SweepReport:
        try:
            return run_sweep(app, req)
        except RosterUnavailable as exc:
            raise HTTPException(503, exc.detail)

    @app.get("/findings")
    def findings() -> dict:
        try:
            data = _load(app.state.findings_path)
            tick = _load(app.state.tick_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(500, f"lifecycle state unreadable: {exc}")
        if data is None:
            # A skipped tick is not a sweep: say so, and hand back why.
            raise HTTPException(404, {
                "message": "no sweep recorded yet — POST /sweep or configure a roster",
                "last_tick": tick,
            })
        if tick is not None:
            data = {**data, "last_tick": tick}
        return data

    return app
