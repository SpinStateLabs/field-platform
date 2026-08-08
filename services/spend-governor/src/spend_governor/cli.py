"""``governor`` CLI — set-cap | spend | status | escalations | resolve | serve."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from spend_governor import __version__

app = typer.Typer(name="governor", help="Spend governor.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006").rstrip("/")


def _fail(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    typer.echo(f"error {resp.status_code}: {detail}", err=True)
    raise typer.Exit(code=1)


@app.command()
def version() -> None:
    typer.echo(f"spend-governor {__version__}")


@app.command("set-cap")
def set_cap(
    agent_id: str = typer.Argument(...),
    from_manifest: Path = typer.Option(
        None, "--from-manifest", help="Derive the dollar cap from a FIELD manifest"
    ),
    limit_cents: int = typer.Option(None, "--limit-cents"),
    token_limit: int = typer.Option(None, "--token-limit"),
    action_limit: int = typer.Option(None, "--action-limit"),
    period: str = typer.Option("daily", "--period", help="daily|monthly|total"),
    escalate_at_pct: int = typer.Option(80, "--escalate-at-pct"),
) -> None:
    """Configure caps for an agent (from a manifest, or explicit limits)."""
    if from_manifest:
        from field_core.manifest import FieldManifest
        from field_core.validation import load_manifest
        from spend_governor.core import SpendCapConfig

        manifest = FieldManifest.from_dict(load_manifest(from_manifest))
        cap = SpendCapConfig.from_manifest(manifest, agent_id)
        if token_limit:
            cap = cap.model_copy(update={"token_limit": token_limit})
        if action_limit:
            cap = cap.model_copy(update={"action_limit": action_limit})
        body = cap.model_dump()
    else:
        body = {
            "agent_id": agent_id,
            "limit_cents": limit_cents,
            "token_limit": token_limit,
            "action_limit": action_limit,
            "period": period,
            "escalate_at_pct": escalate_at_pct,
        }
    resp = httpx.put(f"{_base()}/caps/{agent_id}", json=body, timeout=10.0)
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def spend(
    agent_id: str = typer.Argument(...),
    cents: int = typer.Option(0, "--cents"),
    tokens: int = typer.Option(0, "--tokens"),
    actions: int = typer.Option(0, "--actions"),
    note: str = typer.Option(None, "--note"),
) -> None:
    """Record a spend event; prints resulting status (exit 1 on BLOCK)."""
    resp = httpx.post(
        f"{_base()}/spend",
        json={"agent_id": agent_id, "cents": cents, "tokens": tokens,
              "actions": actions, "note": note},
        timeout=10.0,
    )
    if resp.status_code != 201:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json().get("state") == "BLOCK":
        raise typer.Exit(code=1)


@app.command()
def status(agent_id: str = typer.Argument(...)) -> None:
    resp = httpx.get(f"{_base()}/status/{agent_id}", timeout=10.0)
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def escalations(agent_id: str = typer.Option(None, "--agent-id")) -> None:
    params = {"agent_id": agent_id} if agent_id else {}
    resp = httpx.get(f"{_base()}/escalations", params=params, timeout=10.0)
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def resolve(
    escalation_id: str = typer.Argument(...),
    resolved_by: str = typer.Option(..., "--by", help="Human resolver"),
) -> None:
    resp = httpx.post(
        f"{_base()}/escalations/{escalation_id}/resolve",
        json={"resolved_by": resolved_by},
        timeout=10.0,
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8006, "--port"),
) -> None:
    import uvicorn

    from spend_governor.api import create_app

    ledger = None
    if os.environ.get("FIELD_LEDGER_URL"):
        from field_core.clients import LedgerClient

        ledger = LedgerClient()
    uvicorn.run(create_app(ledger=ledger), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
