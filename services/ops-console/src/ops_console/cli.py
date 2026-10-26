"""``console`` CLI — serve."""

from __future__ import annotations

import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from ops_console import __version__

app = typer.Typer(name="console", help="FIELD ops console.", no_args_is_help=True)


@app.command()
def version() -> None:
    typer.echo(f"ops-console {__version__}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8011, "--port"),
) -> None:
    """Serve the dashboard (service URLs from FIELD_*_URL env vars).

    Refuses to start (exit 2) when FIELD_OPERATOR, FIELD_OPERATOR_KEY or
    FIELD_OPERATOR_KEY_FILE is set: the console has no identity of its own."""
    import uvicorn

    from ops_console.api import ConsoleIdentityRefused, create_app, refuse_own_identity

    try:
        refuse_own_identity()
    except ConsoleIdentityRefused as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    typer.echo(f"FIELD Ops Console → http://{host}:{port}/")
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
