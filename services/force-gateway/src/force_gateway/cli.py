"""``forcegw`` CLI — presets | telemetry | serve."""

from __future__ import annotations

from field_core.authn import auth_headers

import os
import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from force_gateway import __version__

app = typer.Typer(name="forcegw", help="FORCE gateway.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_GATEWAY_URL", "http://127.0.0.1:8009").rstrip("/")


@app.command()
def version() -> None:
    typer.echo(f"force-gateway {__version__}")


@app.command()
def presets(show: str = typer.Option(None, "--show", help="Print a preset's block")) -> None:
    from force_gateway.presets import PRESETS, preset_block

    if show:
        typer.echo(preset_block(show))
        return
    for name, letters in PRESETS.items():
        typer.echo(f"{name:12s} {'+'.join(letters)}")


@app.command(name="self-manifest")
def self_manifest() -> None:
    """Validate + print the Gateway's own governance manifest (ADR 10).
    Exit 1 if invalid — a governance artifact that fails validation is loud."""
    from field_core.validation import validate_manifest_data

    from force_gateway.self_manifest import (
        SELF_AGENT_ID,
        load_self_manifest,
        self_manifest_path,
    )

    path = self_manifest_path()
    data = load_self_manifest()
    result = validate_manifest_data(data)
    typer.echo(f"manifest : {path}")
    typer.echo(f"agent    : {SELF_AGENT_ID}")
    typer.echo(f"owner    : {data['identity']['principal']}")
    cap = data["enforcement"]["spend_cap"]
    typer.echo(f"judge budget : {cap['currency']} {cap['limit']} {cap['period']}"
               f" (on_breach {cap['on_breach']}) — apply with: governor set-cap"
               f" {SELF_AGENT_ID} --from-manifest <path>")
    typer.echo("scope (observer verbs + the egress action llm.messages):")
    for entry in data["delegation"]["scope"]:
        typer.echo(f"  - {entry}")
    typer.echo(f"valid    : {result.ok}")
    if not result.ok:
        typer.echo("VALIDATION FAILED — the Gateway's own governance artifact "
                   "is broken; do not serve.", err=True)
        raise typer.Exit(code=1)


@app.command()
def telemetry() -> None:
    resp = httpx.get(f"{_base()}/telemetry", timeout=10.0, headers=auth_headers())
    typer.echo(resp.text)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8009, "--port"),
    mock: bool = typer.Option(False, "--mock", help="Serve the deterministic mock upstream (no API key needed)"),
) -> None:
    import uvicorn

    if mock:
        os.environ["FORCE_GATEWAY_MOCK"] = "1"
    governor = None
    if os.environ.get("FIELD_GOVERNOR_URL"):
        governor = httpx.Client(
            base_url=os.environ["FIELD_GOVERNOR_URL"], timeout=5.0, headers=auth_headers()
        )
    ledger = None
    if os.environ.get("FIELD_LEDGER_URL"):
        from field_core.clients import LedgerClient

        ledger = LedgerClient()
    from force_gateway.api import create_app

    uvicorn.run(create_app(governor_client=governor, ledger_client=ledger),
                host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
