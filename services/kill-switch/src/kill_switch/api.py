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
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from field_core.clients import (
    AgentNotRegisteredError,
    LedgerClient,
    RegistryClient,
    RegistryUnreachableError,
)
from kill_switch import __version__


class KillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, description="Human operator issuing the halt")
    reason: str = Field(min_length=1)


class KillReport(BaseModel):
    agent_id: str
    previous_status: str
    status: str = "killed"
    elapsed_ms: float
    operator: str
    reason: str
    killed_at: str


class DomainKillReport(BaseModel):
    domain: str
    killed: list[str]
    already_killed: list[str]
    elapsed_ms: float
    operator: str
    reason: str


class Heartbeat(BaseModel):
    agent_id: str
    status: str
    killed: bool
    checked_at: str


class DrillReport(BaseModel):
    agent_id: str
    kill_confirmed_ms: float = Field(
        description="Command received -> registry confirms status=killed"
    )
    heartbeat_confirmed_ms: float = Field(
        description="Command received -> heartbeat reports killed=true"
    )
    restored: bool
    restored_status: str
    total_ms: float
    note: str = (
        "Drill: real kill, real propagation, then status restored. "
        "The 2 a.m. answer: one command, measured below."
    )


def create_app(
    registry: RegistryClient | None = None,
    ledger: LedgerClient | None = None,
) -> FastAPI:
    app = FastAPI(
        title="kill-switch",
        version=__version__,
        description="Registry-integrated halt for agents and domains (FIELD letter E).",
    )
    app.state.registry = registry or RegistryClient()
    app.state.ledger = ledger or LedgerClient()

    def _ledger_note(event_type: str, payload: dict, agent_id: str | None) -> None:
        try:
            app.state.ledger.append(event_type, payload=payload, agent_id=agent_id)
        except Exception:
            pass  # act-first: the kill already happened; audit gap is visible

    def _kill_one(agent_id: str, operator: str, reason: str) -> KillReport:
        t0 = time.perf_counter()
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot kill: {exc}")
        previous = record.get("status", "<unknown>")
        if previous != "killed":
            try:
                app.state.registry.set_status(agent_id, "killed")
            except RegistryUnreachableError as exc:
                raise HTTPException(502, f"registry unreachable — cannot kill: {exc}")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        report = KillReport(
            agent_id=agent_id,
            previous_status=previous,
            elapsed_ms=round(elapsed_ms, 2),
            operator=operator,
            reason=reason,
            killed_at=datetime.now(timezone.utc).isoformat(),
        )
        _ledger_note(
            "kill.agent",
            {"operator": operator, "reason": reason,
             "previous_status": previous, "elapsed_ms": report.elapsed_ms},
            agent_id,
        )
        return report

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "kill-switch", "version": __version__}

    @app.post("/kill/{agent_id}", response_model=KillReport)
    def kill_agent(agent_id: str, req: KillRequest) -> KillReport:
        return _kill_one(agent_id, req.operator, req.reason)

    @app.post("/kill/domain/{domain}", response_model=DomainKillReport)
    def kill_domain(domain: str, req: KillRequest) -> DomainKillReport:
        t0 = time.perf_counter()
        try:
            agents = app.state.registry.list_agents(domain=domain)
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — cannot kill: {exc}")
        if not agents:
            raise HTTPException(404, f"no agents registered in domain '{domain}'")
        killed, already = [], []
        for record in agents:
            if record.get("status") == "killed":
                already.append(record["agent_id"])
                continue
            app.state.registry.set_status(record["agent_id"], "killed")
            killed.append(record["agent_id"])
            _ledger_note(
                "kill.agent",
                {"operator": req.operator, "reason": req.reason,
                 "previous_status": record.get("status"), "domain": domain},
                record["agent_id"],
            )
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        _ledger_note(
            "kill.domain",
            {"operator": req.operator, "reason": req.reason,
             "domain": domain, "killed": killed, "elapsed_ms": elapsed_ms},
            None,
        )
        return DomainKillReport(
            domain=domain, killed=killed, already_killed=already,
            elapsed_ms=elapsed_ms, operator=req.operator, reason=req.reason,
        )

    @app.post("/revive/{agent_id}", response_model=Heartbeat)
    def revive(agent_id: str, req: KillRequest) -> Heartbeat:
        try:
            app.state.registry.set_status(agent_id, "active")
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        _ledger_note(
            "kill.revive", {"operator": req.operator, "reason": req.reason}, agent_id
        )
        return Heartbeat(
            agent_id=agent_id, status="active", killed=False,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    @app.get("/heartbeat/{agent_id}", response_model=Heartbeat)
    def heartbeat(agent_id: str) -> Heartbeat:
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            # Unknown agents are told to stop: fail closed.
            return Heartbeat(
                agent_id=agent_id, status="unregistered", killed=True,
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        status = record.get("status", "<unknown>")
        return Heartbeat(
            agent_id=agent_id, status=status, killed=status != "active",
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    @app.post("/drill/{agent_id}", response_model=DrillReport)
    def drill(agent_id: str, req: KillRequest) -> DrillReport:
        t0 = time.perf_counter()
        try:
            record = app.state.registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        previous = record.get("status", "active")
        _ledger_note(
            "kill.drill.start", {"operator": req.operator, "reason": req.reason}, agent_id
        )

        app.state.registry.set_status(agent_id, "killed")
        kill_confirmed = None
        for _ in range(100):
            if app.state.registry.get_agent(agent_id).get("status") == "killed":
                kill_confirmed = (time.perf_counter() - t0) * 1000
                break
        if kill_confirmed is None:
            raise HTTPException(500, "drill failed: kill did not propagate")

        hb = heartbeat(agent_id)
        if not hb.killed:
            raise HTTPException(500, "drill failed: heartbeat still live")
        heartbeat_confirmed = (time.perf_counter() - t0) * 1000

        app.state.registry.set_status(agent_id, previous)
        restored_status = app.state.registry.get_agent(agent_id).get("status")
        total = (time.perf_counter() - t0) * 1000
        report = DrillReport(
            agent_id=agent_id,
            kill_confirmed_ms=round(kill_confirmed, 2),
            heartbeat_confirmed_ms=round(heartbeat_confirmed, 2),
            restored=restored_status == previous,
            restored_status=restored_status,
            total_ms=round(total, 2),
        )
        _ledger_note(
            "kill.drill.complete",
            {"operator": req.operator, **report.model_dump(exclude={"note"})},
            agent_id,
        )
        return report

    return app
