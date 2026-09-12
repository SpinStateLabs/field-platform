"""``registry`` CLI — add | list | attest | scan | serve."""

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
from agent_registry.store import (
    AgentNotFoundError,
    DuplicateAgentError,
    RegistryStore,
)

app = typer.Typer(name="registry", help="Agent identity registry.", no_args_is_help=True)


def _store(path: Path | None) -> RegistryStore:
    return RegistryStore(path or data_path())


def _ledger_attestation(record) -> tuple[bool, str]:
    """Append `registry.attested` for a CLI attestation. Returns (ok, note).

    The served route ledgers this event; the CLI writes the same column
    straight to SQLite, so without this it bypassed the audit trail entirely.
    ``ok`` is False ONLY when a ledger is configured and refuses — an
    unconfigured ledger is a stated local-operator mode, not a failure, but it
    is still announced rather than passed over in silence.
    """
    import os

    url = os.environ.get("FIELD_LEDGER_URL", "").strip()
    if not url:
        return True, (
            "note: FIELD_LEDGER_URL is unset — this attestation is NOT on the "
            "ledger. Set it, or use POST /agents/{id}/attest, if the "
            "attestation needs an audit record."
        )
    try:
        from field_core.clients import LedgerClient

        LedgerClient().append(
            "registry.attested",
            payload={
                "attested_by": record.attested_by,
                "attested_at": record.attested_at.isoformat()
                if record.attested_at
                else None,
                "via": "cli",
            },
            agent_id=record.agent_id,
        )
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        return False, (
            f"error: attested_at was written but the ledger refused the "
            f"registry.attested event ({exc}). The staleness clock has moved "
            f"with NO audit record — re-run against a reachable ledger."
        )
    return True, "ledgered: registry.attested"


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
def attest(
    agent_id: str = typer.Argument(..., help="Registered agent id"),
    by: str = typer.Option(..., "--by", help="Human who attested (recorded, not authenticated)"),
    path: Path = typer.Option(None, "--path"),
) -> None:
    """Record a human re-attestation — resets the lifecycle staleness clock.

    Exit 0 attested and ledgered (or attested with no ledger configured, which
    is announced); 1 unknown agent; 2 blank attester; 3 attested but the
    CONFIGURED ledger refused the event.

    `attested_at` is the only field that clears lifecycle-manager's
    `lifecycle.reattestation_due` escalation, so this write must never be
    silent. Writing the store without the ledger event is exactly how a
    compliance flag gets cleared with no audit record.
    """
    name = by.strip()
    if not name:
        typer.echo("error: --by must not be blank", err=True)
        raise typer.Exit(code=2)
    try:
        record = _store(path).attest(agent_id, name)
    except AgentNotFoundError:
        typer.echo(f"error: agent '{agent_id}' not registered", err=True)
        raise typer.Exit(code=1)
    typer.echo(record.model_dump_json(indent=2))
    ok, note = _ledger_attestation(record)
    typer.echo(note, err=not ok)
    if not ok:
        raise typer.Exit(code=3)


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
