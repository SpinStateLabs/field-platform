"""``fieldagent`` CLI — version | heartbeat | checkin | check | report-usage | mint.

The shell-agent gate: ``check`` exits 0 ALLOW / 1 BLOCK / 2 ESCALATE, so
``fieldagent check my-agent "transfer funds" && do_it`` fails closed.
"""

from __future__ import annotations

import json
import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from field_agent import (
    ActionBlocked,
    ActionEscalated,
    AgentKilled,
    FieldAgent,
    UsageReportError,
    __version__,
    bootstrap,
)
from field_agent.errors import BootstrapError

app = typer.Typer(
    name="fieldagent",
    help="FIELD client SDK — put an agent under governance.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    typer.echo(f"field-agent {__version__}")


@app.command()
def heartbeat(agent_id: str = typer.Argument(...)) -> None:
    """Poll liveness; exit 1 on killed/unknown/unreachable (fail closed)."""
    agent = FieldAgent(agent_id)
    try:
        hb = agent.ensure_alive()
    except AgentKilled as exc:
        if exc.heartbeat is not None:
            typer.echo(exc.heartbeat.model_dump_json(indent=2))
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(hb.model_dump_json(indent=2))


@app.command()
def checkin(agent_id: str = typer.Argument(...)) -> None:
    """POST a liveness check-in; exit 1 on killed/unknown/unreachable.

    ``heartbeat`` only reads. This one WRITES ``last_seen`` server-side, so
    the agent stops reading stale on the kill-switch's ``GET /liveness``."""
    agent = FieldAgent(agent_id)
    try:
        hb = agent.checkin()
    except AgentKilled as exc:  # HeartbeatUnreachable ⊂ AgentKilled
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(hb.model_dump_json(indent=2))
    if hb.killed:
        typer.echo(
            f"kill-switch reports '{agent_id}' status={hb.status!r} — halting",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def check(
    agent_id: str = typer.Argument(...),
    action: str = typer.Argument(...),
    token_id: str = typer.Option(None, "--token-id", help="Delegation token id"),
    irreversible: bool = typer.Option(False, "--irreversible"),
) -> None:
    """Sentinel gate. Exit 0 ALLOW / 1 BLOCK / 2 ESCALATE."""
    agent = FieldAgent(agent_id, token_id=token_id)
    try:
        verdict = agent.check(action, irreversible=irreversible)
    except ActionEscalated as exc:
        typer.echo(json.dumps(exc.verdict, indent=2))
        raise typer.Exit(code=2)
    except ActionBlocked as exc:
        typer.echo(json.dumps(exc.verdict, indent=2))
        raise typer.Exit(code=1)
    typer.echo(json.dumps(verdict, indent=2))


@app.command("report-usage")
def report_usage(
    agent_id: str = typer.Argument(...),
    model: str = typer.Option(..., "--model"),
    input_tokens: int = typer.Option(0, "--input-tokens"),
    output_tokens: int = typer.Option(0, "--output-tokens"),
    cache_read_tokens: int = typer.Option(0, "--cache-read-tokens"),
    note: str = typer.Option(None, "--note"),
) -> None:
    """Report token usage. Exit 3 when rogue findings come back (mirrors
    ``governor usage``); exit 1 when the report did not land."""
    agent = FieldAgent(agent_id)
    try:
        report = agent.report_usage(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            note=note,
        )
    except UsageReportError as exc:
        typer.echo(f"usage NOT metered: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(report.model_dump_json(indent=2))
    if report.rogue:
        raise typer.Exit(code=3)


@app.command()
def mint(
    agent_id: str = typer.Argument(...),
    granted_by: str = typer.Option(
        ..., "--granted-by", help="Human grantor — never an agent"
    ),
    scope: list[str] = typer.Option(..., "--scope", help="Repeatable"),
    ttl_seconds: int = typer.Option(3600, "--ttl-seconds"),
) -> None:
    """Operator verb: mint a delegation token (wraps field_agent.bootstrap)."""
    try:
        token = bootstrap.mint(
            agent_id, granted_by=granted_by, scope=list(scope),
            ttl_seconds=ttl_seconds,
        )
    except BootstrapError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(token.model_dump_json(indent=2))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
