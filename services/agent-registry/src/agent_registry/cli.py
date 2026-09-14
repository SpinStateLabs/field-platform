"""``registry`` CLI — add | list | attest | scan | serve."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from agent_registry import __version__
from agent_registry.api import create_app, data_path, unresolvable_manifest_ref
from agent_registry.discover import discover, load_n8n_file
from agent_registry.redaction import ScanInputError
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
    """Register an agent.

    Exit 0 registered; 1 already registered; 2 a set --manifest-ref that does
    not resolve (v1.2 D3b — the same field-core resolver and FIELD_MANIFEST_DIR
    rule as POST /agents; nothing is written)."""
    refusal = unresolvable_manifest_ref(manifest_ref)
    if refusal is not None:
        typer.echo(
            f"error: --manifest-ref {manifest_ref!r} does not resolve "
            f"({refusal['reason']}) against FIELD_MANIFEST_DIR="
            f"{refusal['manifest_dir']} — {refusal['hint']}",
            err=True,
        )
        raise typer.Exit(code=2)
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
    api_keys: Path = typer.Option(
        None, "--api-keys",
        help="API-key inventory CSV: key_name,owner,service,created,last_used"
        "[,last_used_by] (exported by you; at most 1 MiB)",
    ),
    secrets_text: Path = typer.Option(
        None, "--secrets-text",
        help="Text file scanned for credential-shaped strings (reported redacted)",
    ),
    principals: Path = typer.Option(
        None, "--principals",
        help="owners.csv (owner[,aliases]) widening the known owners for --api-keys",
    ),
    very_broad: bool = typer.Option(
        False, "--very-broad",
        help="Also match api_key|secret|token=value assignments (OFF by default: "
        "very high false-positive rate)",
    ),
    path: Path = typer.Option(None, "--path"),
) -> None:
    """Shadow-agent discovery: emit unregistered agent candidates.

    Exit 0 nothing found; 2 no input, or an input that is malformed or over
    1 MiB (named, never an empty report); 3 candidates or credential-shaped
    strings found — review them."""
    if n8n is None and accounts is None and api_keys is None and secrets_text is None:
        typer.echo(
            "error: provide --n8n, --accounts, --api-keys and/or --secrets-text",
            err=True,
        )
        raise typer.Exit(code=2)

    def _text(p: Path | None) -> str | None:
        if p is None:
            return None
        try:
            return p.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # named, never a traceback quoting bytes
            raise ScanInputError(f"{p.name} is not UTF-8 text") from None

    try:
        report = discover(
            registered=_store(path).list(),
            n8n_export=load_n8n_file(str(n8n)) if n8n else None,
            accounts_csv=_text(accounts),
            api_keys_csv=_text(api_keys),
            secrets_text=_text(secrets_text),
            principals_csv=_text(principals),
            include_very_broad=very_broad,
        )
    except ScanInputError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2)
    typer.echo(report.model_dump_json(indent=2))
    if report.candidates or report.secret_hits:
        typer.echo(
            f"\n{len(report.candidates)} unregistered agent / credential candidate(s) "
            f"and {len(report.secret_hits)} credential-shaped string(s) found — "
            "review and register, rotate or decommission.",
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
