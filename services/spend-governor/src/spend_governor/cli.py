"""``governor`` CLI — set-cap | spend | status | escalations | resolve | serve."""

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
    """Configure caps for an agent (from a manifest, or explicit limits).

    ``--from-manifest`` also loads ``enforcement.rate_limits`` (replacing the
    agent's set). Everything is validated BEFORE the first PUT: an unsupported
    cap period (per-run), an unknown rate-limit period, or rate_limits without
    a spend_cap exit 1 and configure nothing. stdout stays the cap JSON; the
    rate-limit summary and any declared-unenforced warning go to stderr."""
    limits = None
    if from_manifest:
        from field_core.manifest import FieldManifest
        from field_core.validation import load_manifest
        from spend_governor.core import SpendCapConfig, UnsupportedCapPeriodError
        from spend_governor.provisioning import (
            NO_SPEND_CAP_REFUSAL,
            RateLimitsRefusedError,
            rate_limits_from_manifest,
        )

        manifest = FieldManifest.from_dict(load_manifest(from_manifest))
        try:
            cap = SpendCapConfig.from_manifest(manifest, agent_id)
        except UnsupportedCapPeriodError as exc:
            typer.echo(f"error: UnsupportedCapPeriodError: {exc}", err=True)
            raise typer.Exit(code=1)
        except ValueError as exc:
            if manifest.enforcement.rate_limits and manifest.enforcement.spend_cap is None:
                typer.echo(f"error: {NO_SPEND_CAP_REFUSAL}; nothing was configured",
                           err=True)
            else:
                typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1)
        try:
            limits = rate_limits_from_manifest(manifest, agent_id)
        except RateLimitsRefusedError as exc:
            typer.echo(f"error: {exc}; nothing was configured", err=True)
            raise typer.Exit(code=1)
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
    resp = httpx.put(f"{_base()}/caps/{agent_id}", json=body, timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if limits is not None:
        from spend_governor.provisioning import load_rate_limits

        # The shared loader (lifecycle provision calls it too): with no
        # rate_limits in the manifest a stale set is cleared, and a pre-D1
        # governor with no /rate-limits route is left alone.
        loaded = load_rate_limits(
            lambda path: httpx.get(f"{_base()}{path}", timeout=10.0,
                                   headers=auth_headers()),
            lambda path, json: httpx.put(f"{_base()}{path}", json=json, timeout=10.0,
                                         headers=auth_headers()),
            limits,
        )
        if loaded.outcome == "unchanged":
            return
        if loaded.outcome == "failed":
            typer.echo("error: the cap was set but the rate limits were NOT loaded",
                       err=True)
            _fail(loaded.response)
        typer.echo(f"rate limits loaded for {agent_id}: {loaded.detail}", err=True)
        for r in loaded.declared_unenforced:
            typer.echo(
                f"WARNING: rate limit {r['action']!r} max {r['max']} per "
                f"{r['period']!r} is DECLARED, NOT ENFORCED by the governor — "
                "the period has no server-side meaning (gate-only); ledgered as "
                "spend.rate_limit_declared_unenforced", err=True)


@app.command()
def spend(
    agent_id: str = typer.Argument(...),
    cents: int = typer.Option(0, "--cents"),
    tokens: int = typer.Option(0, "--tokens"),
    actions: int = typer.Option(0, "--actions"),
    note: str = typer.Option(None, "--note"),
    action: str = typer.Option(None, "--action", help="Attribute the row to this action"),
) -> None:
    """Record a spend event; prints resulting status (exit 1 on BLOCK)."""
    body = {"agent_id": agent_id, "cents": cents, "tokens": tokens,
            "actions": actions, "note": note}
    if action is not None:  # omitted, not null: a pre-D1 governor forbids the key
        body["action"] = action
    resp = httpx.post(
        f"{_base()}/spend",
        json=body,
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 201:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json().get("state") == "BLOCK":
        raise typer.Exit(code=1)


@app.command("rate-limits")
def rate_limits(agent_id: str = typer.Argument(...)) -> None:
    """Show the agent's rate limits (enforced and declared-unenforced)."""
    resp = httpx.get(f"{_base()}/rate-limits/{agent_id}", timeout=10.0,
                     headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def status(
    agent_id: str = typer.Argument(...),
    action: str = typer.Option(None, "--action", help="Include this action's rate windows"),
) -> None:
    params = {"action": action} if action is not None else {}
    resp = httpx.get(f"{_base()}/status/{agent_id}", params=params, timeout=10.0,
                     headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def usage(
    agent_id: str = typer.Argument(...),
    model: str = typer.Option(None, "--model", help="Report usage of this model"),
    input_tokens: int = typer.Option(0, "--in"),
    output_tokens: int = typer.Option(0, "--out"),
    cache_read: int = typer.Option(0, "--cache-read"),
) -> None:
    """Report token usage (agents must); or show usage/cost/rogue with no --model."""
    if model is None:
        resp = httpx.get(f"{_base()}/usage/{agent_id}", timeout=10.0,
                         headers=auth_headers())
        if resp.status_code != 200:
            _fail(resp)
        typer.echo(resp.text)
        return
    resp = httpx.post(
        f"{_base()}/usage",
        json={"agent_id": agent_id, "model": model, "input_tokens": input_tokens,
              "output_tokens": output_tokens, "cache_read_tokens": cache_read},
        timeout=10.0, headers=auth_headers(),
    )
    if resp.status_code != 201:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json().get("rogue"):
        raise typer.Exit(code=3)


@app.command("set-policy")
def set_policy(
    agent_id: str = typer.Argument(...),
    allowed_model: list[str] = typer.Option(
        None, "--allowed-model", help="Repeatable; empty = any priced model"),
    token_rate_limit: int = typer.Option(None, "--token-rate-limit"),
    rate_window_seconds: int = typer.Option(3600, "--rate-window-seconds"),
) -> None:
    """Set the agent's usage policy (allow-list + burst ceiling)."""
    resp = httpx.put(
        f"{_base()}/policies/{agent_id}",
        json={"agent_id": agent_id, "allowed_models": allowed_model or [],
              "token_rate_limit": token_rate_limit,
              "rate_window_seconds": rate_window_seconds},
        timeout=10.0, headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def escalations(agent_id: str = typer.Option(None, "--agent-id")) -> None:
    params = {"agent_id": agent_id} if agent_id else {}
    resp = httpx.get(f"{_base()}/escalations", params=params, timeout=10.0, headers=auth_headers())
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
        headers=auth_headers(),
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
