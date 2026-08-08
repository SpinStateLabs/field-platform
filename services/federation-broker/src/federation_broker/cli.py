"""``fedbroker`` CLI — add-contract | contracts | crossing | serve."""

from __future__ import annotations

from field_core.authn import auth_headers

import json
import os
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from federation_broker import __version__

app = typer.Typer(name="fedbroker", help="Federation broker.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_FEDERATION_URL", "http://127.0.0.1:8010").rstrip("/")


def _fail(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    typer.echo(f"error {resp.status_code}: {detail}", err=True)
    raise typer.Exit(code=1)


@app.command()
def version() -> None:
    typer.echo(f"federation-broker {__version__}")


@app.command("add-contract")
def add_contract(
    contract_id: str = typer.Argument(...),
    org: str = typer.Option(..., "--org", help="Counterparty org"),
    scope: list[str] = typer.Option(..., "--scope", help="Repeatable allowed scope"),
    data_class: list[str] = typer.Option(..., "--data-class", help="Repeatable"),
    contract_ref: str = typer.Option(None, "--ref", help="Signed instrument location"),
) -> None:
    resp = httpx.put(
        f"{_base()}/contracts/{contract_id}",
        json={"contract_id": contract_id, "counterparty_org": org,
              "allowed_scopes": scope, "allowed_data_classes": data_class,
              "contract_ref": contract_ref, "active": True},
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def contracts() -> None:
    resp = httpx.get(f"{_base()}/contracts", timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def crossing(
    org: str = typer.Option(..., "--org"),
    agent_id: str = typer.Option(..., "--agent-id"),
    manifest: Path = typer.Option(..., "--manifest", help="Counterparty manifest YAML"),
    scope: str = typer.Option(..., "--scope"),
    data_class: str = typer.Option(..., "--data-class"),
) -> None:
    """Submit a crossing request; exit 0 ALLOW, 1 BLOCK."""
    from field_core.validation import load_manifest

    resp = httpx.post(
        f"{_base()}/crossing",
        json={"counterparty_org": org, "counterparty_agent_id": agent_id,
              "counterparty_manifest": load_manifest(manifest),
              "scope": scope, "data_class": data_class},
        timeout=15.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json()["decision"] != "ALLOW":
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8010, "--port"),
) -> None:
    import uvicorn

    from federation_broker.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
