"""``delegation`` CLI — mint | revoke | introspect | list | serve.

The CLI talks to the running HTTP service (it needs registry + ledger to
enforce the mint rules); it is not an offline tool.
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

from delegation_authority import __version__

app = typer.Typer(
    name="delegation", help="Delegation token authority.", no_args_is_help=True
)


def _base() -> str:
    return os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003").rstrip("/")


def _fail(resp: httpx.Response) -> None:
    typer.echo(f"error {resp.status_code}: {resp.json().get('detail', resp.text)}", err=True)
    raise typer.Exit(code=1)


@app.command()
def version() -> None:
    typer.echo(f"delegation-authority {__version__}")


@app.command()
def mint(
    agent_id: str = typer.Argument(...),
    granted_by: str = typer.Option(..., "--granted-by", help="Human grantor"),
    scope: list[str] = typer.Option(..., "--scope", help="Repeatable"),
    ttl: int = typer.Option(3600, "--ttl", help="Seconds until expiry"),
) -> None:
    """Mint a scoped, expiring token for a registered agent."""
    resp = httpx.post(
        f"{_base()}/tokens",
        json={
            "agent_id": agent_id,
            "granted_by": granted_by,
            "scope": scope,
            "ttl_seconds": ttl,
        },
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 201:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def revoke(token_id: str = typer.Argument(...)) -> None:
    """Revoke a token (idempotent)."""
    resp = httpx.post(f"{_base()}/tokens/{token_id}/revoke", timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def introspect(token_id: str = typer.Argument(...)) -> None:
    """Check a token; exit 1 unless ACTIVE."""
    resp = httpx.post(f"{_base()}/introspect", json={"token_id": token_id}, timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if not resp.json().get("active"):
        raise typer.Exit(code=1)


@app.command("oauth-introspect")
def oauth_introspect(token: str = typer.Argument(..., help="Token id")) -> None:
    """RFC 7662-shaped introspection; exit 1 unless active.

    Revoked, expired and unknown tokens all answer `{"active": false}` and
    nothing else — the response never says which.
    """
    resp = httpx.post(
        f"{_base()}/oauth/introspect",
        data={"token": token},
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if not resp.json().get("active"):
        raise typer.Exit(code=1)


@app.command("list")
def list_cmd(agent_id: str = typer.Option(None, "--agent-id")) -> None:
    params = {"agent_id": agent_id} if agent_id else {}
    resp = httpx.get(f"{_base()}/tokens", params=params, timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8003, "--port"),
) -> None:
    """Run the HTTP API (requires ledger + registry URLs in env)."""
    import uvicorn

    from delegation_authority.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
