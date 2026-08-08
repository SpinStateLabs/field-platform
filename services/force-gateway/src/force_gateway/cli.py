"""``forcegw`` CLI — presets | telemetry | serve."""

from __future__ import annotations

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


@app.command()
def telemetry() -> None:
    resp = httpx.get(f"{_base()}/telemetry", timeout=10.0)
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
            base_url=os.environ["FIELD_GOVERNOR_URL"], timeout=5.0
        )
    from force_gateway.api import create_app

    uvicorn.run(create_app(governor_client=governor), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
