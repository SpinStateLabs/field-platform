"""``sentinel`` CLI — check | clauses | serve."""

from __future__ import annotations

from field_core.authn import auth_headers

import os
import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from conformance_sentinel import __version__

app = typer.Typer(name="sentinel", help="Conformance sentinel.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_SENTINEL_URL", "http://127.0.0.1:8004").rstrip("/")


@app.command()
def version() -> None:
    typer.echo(f"conformance-sentinel {__version__}")


@app.command()
def check(
    agent_id: str = typer.Argument(...),
    action: str = typer.Argument(...),
    token_id: str = typer.Option(None, "--token-id"),
    irreversible: bool = typer.Option(False, "--irreversible"),
) -> None:
    """Ask the sentinel; exit 0 ALLOW, 2 ESCALATE, 1 BLOCK."""
    resp = httpx.post(
        f"{_base()}/check",
        json={"agent_id": agent_id, "action": action, "token_id": token_id,
              "irreversible": irreversible},
        timeout=15.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        typer.echo(f"error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(code=1)
    verdict = resp.json()
    typer.echo(resp.text)
    if verdict["decision"] == "BLOCK":
        raise typer.Exit(code=1)
    if verdict["decision"] == "ESCALATE":
        raise typer.Exit(code=2)


@app.command()
def clauses() -> None:
    resp = httpx.get(f"{_base()}/clauses", timeout=10.0, headers=auth_headers())
    for cid, text in resp.json().items():
        typer.echo(f"{cid:22s} {text}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8004, "--port"),
) -> None:
    import uvicorn

    from conformance_sentinel.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
