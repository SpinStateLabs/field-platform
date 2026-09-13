"""``delegation`` CLI — mint | revoke | introspect | list | serve | doa check.

The CLI talks to the running HTTP service (it needs registry + ledger to
enforce the mint rules); it is not an offline tool.

The one exception is ``doa check``: a dry run of the mint route's DOA roster
gate, in-process, that mints nothing, writes nothing and opens no connection.
It does not re-implement the gate — it builds the real app and calls the real
``POST /tokens`` handler with a registry that answers "active", a ledger that
stops the handler at its first write, and a token store that refuses to save.
Reaching the ledger write means every gate clause before it passed.
"""

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


doa_app = typer.Typer(
    name="doa",
    help="DOA roster tools. Dry runs only: nothing here mints or writes.",
    no_args_is_help=True,
)
app.add_typer(doa_app, name="doa")


class _GateCleared(Exception):
    """Raised by the dry-run ledger. The mint handler appends to the ledger
    only after its last refusal clause, so reaching it IS the ALLOW."""

    def __init__(self, payload: dict) -> None:
        super().__init__("dry run stopped at the ledger write")
        self.payload = payload


class _DryRunLedger:
    def append(self, event_type, payload=None, agent_id=None):
        raise _GateCleared(dict(payload or {}))


class _DryRunStore:
    """Never written. The ledger stop fires first; ``save`` refusing is the
    second wall, so a future reordering fails loudly instead of minting."""

    def list(self, agent_id=None):
        return []

    def get(self, token_id):
        from delegation_authority.store import TokenNotFoundError

        raise TokenNotFoundError(token_id)

    def save(self, token):
        raise RuntimeError("doa check is a dry run: it must never persist a token")


class _DryRunRegistry:
    """The registry step is not what is being checked: the agent is answered
    as registered and active, carrying the manifest_ref the operator named,
    VERBATIM — the route's own resolver then applies FIELD_MANIFEST_DIR to a
    relative ref exactly as a live mint would."""

    def __init__(self, manifest_ref: str | None) -> None:
        self._manifest_ref = manifest_ref

    def require_active_agent(self, agent_id: str) -> dict:
        return {"agent_id": agent_id, "status": "active", "manifest_ref": self._manifest_ref}


def dry_run_mint_gate(
    roster: Path,
    grantor: str,
    scope: list[str],
    ttl_days: int,
    manifest: Path | str | None = None,
    agent_id: str | None = None,
) -> tuple[int, str]:
    """Run the real mint handler against ``roster`` and return
    ``(exit_code, line)``: 0 ALLOW, 1 REFUSED, 2 no verdict.

    ``manifest`` is the registry record's ``manifest_ref`` and is handed to
    the route UNCHANGED: never absolutised against this process's working
    directory, so a relative ref resolves against ``FIELD_MANIFEST_DIR`` (or
    the working directory when that is unset) exactly as the route resolves
    the registry's ref.

    ``FIELD_DOA_ROSTER`` is set to ``roster`` for the call and restored
    afterwards, exactly as it was (including unset)."""
    from fastapi import HTTPException
    from fastapi.routing import APIRoute
    from pydantic import ValidationError

    from delegation_authority.api import MintRequest, create_app
    from delegation_authority.doa import ROSTER_ENV

    manifest_ref = str(manifest) if manifest is not None else None
    agent = agent_id or (Path(manifest).stem if manifest is not None else "dry-run-agent")
    try:
        request = MintRequest(
            agent_id=agent,
            granted_by=grantor,
            scope=list(scope),
            ttl_seconds=ttl_days * 86400,
        )
    except ValidationError as exc:
        return 2, f"ERROR invalid request (no verdict): {exc.errors(include_url=False)}"

    app_ = create_app(
        store=_DryRunStore(),
        ledger=_DryRunLedger(),
        registry=_DryRunRegistry(manifest_ref),
    )
    handler = next(
        r.endpoint
        for r in app_.routes
        if isinstance(r, APIRoute) and r.path == "/tokens" and "POST" in r.methods
    )

    saved = os.environ.get(ROSTER_ENV)
    os.environ[ROSTER_ENV] = str(roster)
    try:
        handler(request)
    except _GateCleared as cleared:
        if cleared.payload.get("doa_checked") is not True:
            return 2, (
                "ERROR the mint handler reached its ledger write without running "
                "the DOA roster gate — no verdict (nothing minted)"
            )
        return 0, (
            f"ALLOW grantor={grantor!r} scope={list(scope)} ttl_days={ttl_days} "
            f"agent={agent!r} — every DOA gate clause passed "
            "(dry run: nothing minted, nothing written)"
        )
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            clause, message = detail.get("clause_id"), detail.get("message")
        else:
            clause, message = None, detail
        head = f"REFUSED {clause} ({exc.status_code})" if clause else f"REFUSED ({exc.status_code})"
        return 1, f"{head}: {message}"
    except Exception as exc:  # noqa: BLE001 — never let a fault read as a verdict
        return 2, f"ERROR dry run failed (no verdict): {type(exc).__name__}: {exc}"
    finally:
        if saved is None:
            os.environ.pop(ROSTER_ENV, None)
        else:
            os.environ[ROSTER_ENV] = saved
    return 2, "ERROR the mint handler returned without reaching its ledger write — no verdict"


@doa_app.command("check")
def doa_check(
    roster: Path = typer.Option(..., "--roster", help="DOA roster YAML (the file FIELD_DOA_ROSTER would name)"),
    grantor: str = typer.Option(..., "--grantor", help="granted_by, exactly as the mint will send it"),
    scope: list[str] = typer.Option(..., "--scope", help="Repeatable"),
    ttl_days: int = typer.Option(..., "--ttl-days", help="Token lifetime in days"),
    manifest: str = typer.Option(
        None, "--manifest-ref", "--manifest",
        help="The agent's registry manifest_ref, EXACTLY as the record has it (passed to "
        "the route unchanged: a relative ref resolves against FIELD_MANIFEST_DIR). "
        "Omitted = an agent with no manifest_ref, which the gate refuses (422 D.scope)",
    ),
    agent_id: str = typer.Option(
        None, "--agent-id", help="Agent id used in messages (default: the manifest file's stem)"
    ),
) -> None:
    """Dry-run the mint route's DOA gate: print ALLOW or the refusal.

    Exit 0 ALLOW, 1 REFUSED (clause + message), 2 no verdict. Mints nothing,
    writes nothing, opens no connection. The registry is NOT read: the agent
    is taken as registered and active with --manifest-ref as its manifest_ref,
    so an unregistered (404) or killed (409) agent, a registry record whose
    manifest_ref differs, and the ledger write (502) are not evaluated. ALLOW
    means the roster gate passes for that agent state, not that a live mint
    will succeed."""
    code, line = dry_run_mint_gate(roster, grantor, scope, ttl_days, manifest, agent_id)
    typer.echo(line, err=code == 2)
    raise typer.Exit(code=code)


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
