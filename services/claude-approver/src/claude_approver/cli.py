"""``approver`` CLI - serve | version."""

from __future__ import annotations

import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from claude_approver import SERVICE, __version__

app = typer.Typer(name="approver", help="Claude Managed Agents approver.", no_args_is_help=True)


@app.command()
def version() -> None:
    typer.echo(f"{SERVICE} {__version__}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8014, "--port"),
) -> None:
    """Start the poller (daemon thread) and the HTTP surface."""
    import logging

    import uvicorn

    from claude_approver.api import create_app
    from claude_approver.core import Approver

    logging.basicConfig(level=logging.INFO)
    approver = Approver()
    approver.start()
    uvicorn.run(create_app(approver), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
