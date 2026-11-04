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

#: captured at import: tests replace the module-level ``httpx`` with a stand-in that has no exception classes
_HTTP_ERRORS = (httpx.HTTPError, httpx.InvalidURL)

from incident_replay import __version__

app = typer.Typer(name="replay", help="Incident replay.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_REPLAY_URL", "http://127.0.0.1:8007").rstrip("/")


def _short(text: str, limit: int = 200) -> str:
    """An error body on one capped line: a proxy's HTML error page is not dumped into the terminal."""
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 1] + "…"


@app.command()
def version() -> None:
    typer.echo(f"incident-replay {__version__}")


@app.command()
def run(
    agent_id: str = typer.Argument(...),
    since: str = typer.Option(..., "--since", help="ISO 8601 instant with a time (a date alone is refused)"),
    until: str = typer.Option(..., "--until", help="ISO 8601 instant with a time (a date alone is refused)"),
    # a str, not a click Path: click stats a Path option while parsing, and a NUL byte there escapes as a ValueError
    # before this command runs (S6-15); the write is guarded below instead
    markdown: str = typer.Option(
        None, "--markdown", help="Write the RACI-ready post-mortem here"
    ),
) -> None:
    """Reconstruct an incident window for an agent. Exit 1 when the service is unreachable or refuses; exit 2 when the
    --markdown file cannot be written (the post-mortem is then printed to stdout, not lost)."""
    body = {"agent_id": agent_id, "since": since, "until": until}
    path = "/replay/markdown" if markdown else "/replay"
    try:
        resp = httpx.post(f"{_base()}{path}", json=body, timeout=30.0, headers=auth_headers())
    except _HTTP_ERRORS as exc:
        typer.echo(f"error: incident-replay unreachable ({type(exc).__name__})", err=True)
        raise typer.Exit(code=1)
    if resp.status_code != 200:
        typer.echo(f"error {resp.status_code}: {_short(resp.text)}", err=True)
        raise typer.Exit(code=1)
    if markdown:
        try:
            Path(markdown).write_text(resp.text, encoding="utf-8")
        except (OSError, ValueError) as exc:        # missing directory, a directory, permission, NUL byte
            typer.echo(f"error: cannot write {markdown!r} ({type(exc).__name__}); post-mortem follows on stdout",
                       err=True)
            typer.echo(resp.text)
            raise typer.Exit(code=2)
        typer.echo(f"post-mortem written to {markdown}")
    else:
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
