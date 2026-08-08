"""``replay`` CLI — run | serve."""

from __future__ import annotations

from field_core.authn import auth_headers

import os
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from incident_replay import __version__

app = typer.Typer(name="replay", help="Incident replay.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_REPLAY_URL", "http://127.0.0.1:8007").rstrip("/")


@app.command()
def version() -> None:
    typer.echo(f"incident-replay {__version__}")


@app.command()
def run(
    agent_id: str = typer.Argument(...),
    since: str = typer.Option(..., "--since", help="ISO 8601"),
    until: str = typer.Option(..., "--until", help="ISO 8601"),
    markdown: Path = typer.Option(
        None, "--markdown", help="Write the RACI-ready post-mortem here"
    ),
) -> None:
    """Reconstruct an incident window for an agent."""
    body = {"agent_id": agent_id, "since": since, "until": until}
    if markdown:
        resp = httpx.post(f"{_base()}/replay/markdown", json=body, timeout=30.0, headers=auth_headers())
        if resp.status_code != 200:
            typer.echo(f"error {resp.status_code}: {resp.text}", err=True)
            raise typer.Exit(code=1)
        markdown.write_text(resp.text, encoding="utf-8")
        typer.echo(f"post-mortem written to {markdown}")
    else:
        resp = httpx.post(f"{_base()}/replay", json=body, timeout=30.0, headers=auth_headers())
        if resp.status_code != 200:
            typer.echo(f"error {resp.status_code}: {resp.text}", err=True)
            raise typer.Exit(code=1)
        typer.echo(resp.text)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8007, "--port"),
) -> None:
    import uvicorn

    from incident_replay.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
