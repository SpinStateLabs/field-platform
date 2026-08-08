"""``killswitch`` CLI — agent | domain | drill | heartbeat | revive | serve.

Named ``killswitch`` (not ``kill``) so it never shadows the shell builtin.
"""

from __future__ import annotations

from field_core.authn import auth_headers

import os
import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from kill_switch import __version__

app = typer.Typer(name="killswitch", help="Agent kill switch.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005").rstrip("/")


def _fail(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    typer.echo(f"error {resp.status_code}: {detail}", err=True)
    raise typer.Exit(code=1)


@app.command()
def version() -> None:
    typer.echo(f"kill-switch {__version__}")


@app.command()
def agent(
    agent_id: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator", help="Human operator"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Kill one agent. One command."""
    resp = httpx.post(
        f"{_base()}/kill/{agent_id}",
        json={"operator": operator, "reason": reason},
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def domain(
    domain_name: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator"),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    """Kill every agent in a domain."""
    resp = httpx.post(
        f"{_base()}/kill/domain/{domain_name}",
        json={"operator": operator, "reason": reason},
        timeout=30.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def drill(
    agent_id: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator"),
) -> None:
    """Timed kill drill: kill, verify propagation, restore. Prints ms."""
    resp = httpx.post(
        f"{_base()}/drill/{agent_id}",
        json={"operator": operator, "reason": "scheduled drill"},
        timeout=30.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def heartbeat(agent_id: str = typer.Argument(...)) -> None:
    """Poll an agent's heartbeat; exit 1 if killed."""
    resp = httpx.get(f"{_base()}/heartbeat/{agent_id}", timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json().get("killed"):
        raise typer.Exit(code=1)


@app.command()
def revive(
    agent_id: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator"),
    reason: str = typer.Option("post-incident revive", "--reason"),
) -> None:
    resp = httpx.post(
        f"{_base()}/revive/{agent_id}",
        json={"operator": operator, "reason": reason},
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8005, "--port"),
) -> None:
    import uvicorn

    from kill_switch.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
