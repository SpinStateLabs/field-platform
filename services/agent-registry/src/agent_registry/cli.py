"""``registry`` CLI — add | list | scan | serve."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from agent_registry import __version__
from agent_registry.api import create_app, data_path
from agent_registry.discover import discover, load_n8n_file
from agent_registry.models import AgentCreate, AgentStatus
from agent_registry.store import DuplicateAgentError, RegistryStore

app = typer.Typer(name="registry", help="Agent identity registry.", no_args_is_help=True)


def _store(path: Path | None) -> RegistryStore:
    return RegistryStore(path or data_path())


@app.command()
def version() -> None:
    typer.echo(f"agent-registry {__version__}")


@app.command()
def add(
    agent_id: str = typer.Argument(..., help="Slug id, e.g. invoicing-agent"),
    name: str = typer.Option(..., "--name"),
    owner: str = typer.Option(..., "--owner", help="Human owner"),
    domain: str = typer.Option("general", "--domain"),
    manifest_ref: str = typer.Option(None, "--manifest-ref"),
    path: Path = typer.Option(None, "--path", help="SQLite file (default FIELD_DATA_DIR)"),
) -> None:
    """Register an agent."""
    try:
        record = _store(path).add(
            AgentCreate(
                agent_id=agent_id,
                name=name,
                owner=owner,
                domain=domain,
                manifest_ref=manifest_ref,
            )
        )
    except DuplicateAgentError:
        typer.echo(f"error: agent '{agent_id}' already registered", err=True)
        raise typer.Exit(code=1)
    typer.echo(record.model_dump_json(indent=2))


@app.command("list")
def list_cmd(
    status: AgentStatus = typer.Option(None, "--status"),
    domain: str = typer.Option(None, "--domain"),
    path: Path = typer.Option(None, "--path"),
) -> None:
    """List registered agents."""
    records = _store(path).list(status=status, domain=domain)
    if not records:
        typer.echo("(no agents registered)")
        return
    for r in records:
        typer.echo(
            f"{r.agent_id:24s} {r.status.value:8s} domain={r.domain:12s} "
            f"owner={r.owner}"
        )


@app.command()
def scan(
    n8n: Path = typer.Option(None, "--n8n", help="n8n workflow export JSON"),
    accounts: Path = typer.Option(None, "--accounts", help="service-account CSV"),
    path: Path = typer.Option(None, "--path"),
) -> None:
    """Shadow-agent discovery: emit unregistered agent candidates."""
    if n8n is None and accounts is None:
        typer.echo("error: provide --n8n and/or --accounts", err=True)
        raise typer.Exit(code=2)
    report = discover(
        registered=_store(path).list(),
        n8n_export=load_n8n_file(str(n8n)) if n8n else None,
        accounts_csv=accounts.read_text(encoding="utf-8") if accounts else None,
    )
    typer.echo(report.model_dump_json(indent=2))
    if report.candidates:
        typer.echo(
            f"\n{len(report.candidates)} unregistered agent candidate(s) found — "
            "review and register or decommission.",
            err=True,
        )
        raise typer.Exit(code=3)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8001, "--port"),
) -> None:
    """Run the HTTP API."""
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
