"""``ledger`` CLI — append | verify | export | serve."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from sealed_ledger import __version__
from sealed_ledger.api import create_app, data_path
from sealed_ledger.store import LedgerStore

app = typer.Typer(name="ledger", help="Sealed hash-chained ledger.", no_args_is_help=True)


def _store(path: Path | None) -> LedgerStore:
    return LedgerStore(path or data_path())


@app.command()
def version() -> None:
    typer.echo(f"sealed-ledger {__version__}")


@app.command()
def append(
    event_type: str = typer.Argument(..., help="Event type, e.g. 'action'."),
    payload: str = typer.Option("{}", "--payload", help="JSON object payload."),
    agent_id: str = typer.Option(None, "--agent-id"),
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
) -> None:
    """Append one event to the chain."""
    try:
        payload_obj = json.loads(payload)
        if not isinstance(payload_obj, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        typer.echo(f"error: bad --payload: {exc}", err=True)
        raise typer.Exit(code=2)
    event = _store(path).append(event_type, payload_obj, agent_id)
    typer.echo(event.model_dump_json())


@app.command()
def verify(
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
) -> None:
    """Walk the chain; exit 1 on the first break."""
    result = _store(path).verify()
    if result.ok:
        typer.echo(f"OK — chain intact over {result.length} events")
    else:
        typer.echo(f"TAMPERED — {result.reason}")
        raise typer.Exit(code=1)


@app.command()
def export(
    out_dir: Path = typer.Option(None, "--out-dir", help="Export directory."),
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
) -> None:
    """Auditor export: JSONL copy + verification summary."""
    store = _store(path)
    summary = store.export(out_dir or store.path.parent / "exports")
    typer.echo(summary.model_dump_json(indent=2))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8002, "--port"),
) -> None:
    """Run the HTTP API."""
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
