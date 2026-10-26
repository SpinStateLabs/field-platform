"""``delegation`` CLI — mint | revoke | introspect | list | serve | doa check.

The CLI talks to the running HTTP service (it needs registry + ledger to
enforce the mint rules); it is not an offline tool.

The one exception is ``doa check``: a dry run of the mint route's DOA roster
gate, in-process, that mints nothing, writes nothing and opens no connection.
It does not re-implement the gate — it builds the real app and calls the real
``POST /tokens`` handler with a registry that answers "active", a ledger that
stops the handler at its first write, and a token store that refuses to save.
Reaching the ledger write means every gate clause before it passed.

Phase G (C-2): ``mint`` and ``revoke`` take ``--operator-id`` and
``--operator-key-file``, falling back to ``FIELD_OPERATOR`` with
``FIELD_OPERATOR_KEY_FILE`` or ``FIELD_OPERATOR_KEY``. The key file is read here,
stripped, and never printed. The pair is sent ONLY on ``POST /tokens`` and
``POST /tokens/{id}/revoke`` (``GUARDED_ROUTES``, RT1-10): ``introspect``,
``oauth-introspect`` and ``list`` never carry it. Under ENFORCE an identity
without ``mint_for_others`` may mint only with ``--granted-by`` equal to its own
id (design C-13).
"""

from __future__ import annotations

import os
import re
import sys
import urllib.parse
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from delegation_authority import __version__
from field_core import authn

app = typer.Typer(
    name="delegation", help="Delegation token authority.", no_args_is_help=True
)


def _base() -> str:
    return os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003").rstrip("/")


def _fail(resp: httpx.Response) -> None:
    typer.echo(f"error {resp.status_code}: {resp.json().get('detail', resp.text)}", err=True)
    raise typer.Exit(code=1)


# -- Phase G C-2: this CLI's own operator identity --------------------------------------
# (the same block is in the kill-switch and lifecycle CLIs: the services share no CLI
# package, and field-core's operator_headers() puts the pair on every request)

#: (method, path relative to the delegation base URL) of every delegation route
#: this CLI calls that carries an operator guard. Nothing else gets the pair.
GUARDED_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"/tokens")),
    ("POST", re.compile(r"/tokens/[^/]+/revoke")),
)
_OPERATOR_ID = re.compile(r"[A-Za-z0-9._@-]{1,64}")
_OPERATOR_KEY = re.compile(r"[A-Za-z0-9._~+/=-]{1,256}")
_MAX_KEY_FILE_BYTES = 4096
OPERATOR_ID_HELP = "Operator id, presented on guarded routes only (default: $FIELD_OPERATOR)."
OPERATOR_KEY_FILE_HELP = ("File holding that operator's key; read and stripped here, never printed "
                          "(default: $FIELD_OPERATOR_KEY_FILE, else $FIELD_OPERATOR_KEY).")


def _refuse(message: str) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=2)


def _read_key_file(path: str, strict: bool) -> str:
    """The stripped key in ``path``. ``strict`` (a file named on the command
    line): any problem exits 2 before anything is sent. Otherwise (named by
    FIELD_OPERATOR_KEY_FILE): a warning and no identity, as field-core's
    operator_headers does. The content is never printed."""
    problem = None
    key = ""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_MAX_KEY_FILE_BYTES + 1)
    except OSError as exc:
        problem = f"unreadable ({type(exc).__name__})"
    else:
        if len(raw) > _MAX_KEY_FILE_BYTES:
            problem = "larger than a key"
        else:
            try:
                key = raw.decode("utf-8-sig").strip()
            except UnicodeDecodeError:
                problem = "not UTF-8"
            else:
                if not key:
                    problem = "empty"
                elif not _OPERATOR_KEY.fullmatch(key):
                    problem = "not a single key token"
    if problem:
        if strict:
            _refuse(f"--operator-key-file is {problem}; nothing sent")
        typer.echo(f"warning: FIELD_OPERATOR_KEY_FILE is {problem}; no operator identity is sent",
                   err=True)
        return ""
    return key


def operator_pair(operator_id: str | None, key_file: Path | str | None) -> tuple[str, str] | None:
    """(id, key) for the guarded routes, or None. The flags win over the
    environment; FIELD_OPERATOR_KEY_FILE wins over FIELD_OPERATOR_KEY (an
    unusable file never falls back to the variable)."""
    explicit = operator_id is not None or key_file is not None
    op = (operator_id if operator_id is not None else os.environ.get("FIELD_OPERATOR", "")).strip()
    env_file = os.environ.get("FIELD_OPERATOR_KEY_FILE", "").strip()
    if key_file is not None:
        key = _read_key_file(str(key_file), strict=True)
    elif env_file:
        key = _read_key_file(env_file, strict=explicit) if (op or explicit) else ""
    else:
        key = os.environ.get("FIELD_OPERATOR_KEY", "")
    if explicit and not (op and key):
        _refuse("--operator-id and an operator key (--operator-key-file, FIELD_OPERATOR_KEY_FILE or "
                "FIELD_OPERATOR_KEY) go together; nothing sent")
    if not (op and key):
        return None
    if not _OPERATOR_ID.fullmatch(op):
        _refuse("the operator id is not a valid operator id; nothing sent")
    if not _OPERATOR_KEY.fullmatch(key):
        _refuse("the operator key is not a single key token (value not shown); nothing sent")
    return op, key


def is_guarded(method: str, path: str, base: str,
               routes: tuple[tuple[str, re.Pattern[str]], ...] = GUARDED_ROUTES) -> bool:
    """True only for an allowlisted (method, path) under ``base``."""
    prefix = urllib.parse.urlsplit(base).path.rstrip("/")
    if prefix:
        if not path.startswith(prefix + "/"):
            return False
        path = path[len(prefix):]
    return any(m == method.upper() and rx.fullmatch(path) for m, rx in routes)


class GuardedOperatorAuth(httpx.Auth):
    """Adds the operator pair to a request only when it is an allowlisted
    guarded route; every other request leaves without it."""

    def __init__(self, base: str, pair: tuple[str, str] | None,
                 routes: tuple[tuple[str, re.Pattern[str]], ...] = GUARDED_ROUTES):
        self._base, self._pair, self._routes = base, pair, routes

    def auth_flow(self, request):
        if self._pair and is_guarded(request.method, request.url.path, self._base, self._routes):
            request.headers["x-field-operator"], request.headers["x-field-operator-key"] = self._pair
        yield request


def _perimeter() -> dict[str, str]:
    """x-field-auth only. Never ``authn.auth_headers()``: that adds the env
    operator pair to every request, reads included."""
    secret = authn.shared_secret()
    return {authn.HEADER: secret} if secret else {}


def _client(pair: tuple[str, str] | None = None, timeout: float = 10.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers=_perimeter(), auth=GuardedOperatorAuth(_base(), pair))


_OP_ID = typer.Option(None, "--operator-id", help=OPERATOR_ID_HELP)
_OP_KEY_FILE = typer.Option(None, "--operator-key-file", help=OPERATOR_KEY_FILE_HELP)


@app.command()
def version() -> None:
    typer.echo(f"delegation-authority {__version__}")


@app.command()
def mint(
    agent_id: str = typer.Argument(...),
    granted_by: str = typer.Option(..., "--granted-by", help="Human grantor"),
    scope: list[str] = typer.Option(..., "--scope", help="Repeatable"),
    ttl: int = typer.Option(3600, "--ttl", help="Seconds until expiry"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Mint a scoped, expiring token for a registered agent."""
    pair = operator_pair(operator_id, operator_key_file)
    with _client(pair) as http:
        resp = http.post(
            f"{_base()}/tokens",
            json={
                "agent_id": agent_id,
                "granted_by": granted_by,
                "scope": scope,
                "ttl_seconds": ttl,
            },
        )
    if resp.status_code != 201:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def revoke(
    token_id: str = typer.Argument(...),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Revoke a token (idempotent)."""
    pair = operator_pair(operator_id, operator_key_file)
    with _client(pair) as http:
        resp = http.post(f"{_base()}/tokens/{token_id}/revoke")
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def introspect(token_id: str = typer.Argument(...)) -> None:
    """Check a token; exit 1 unless ACTIVE."""
    with _client() as http:
        resp = http.post(f"{_base()}/introspect", json={"token_id": token_id})
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
    with _client() as http:
        resp = http.post(f"{_base()}/oauth/introspect", data={"token": token})
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if not resp.json().get("active"):
        raise typer.Exit(code=1)


@app.command("list")
def list_cmd(agent_id: str = typer.Option(None, "--agent-id")) -> None:
    params = {"agent_id": agent_id} if agent_id else {}
    with _client() as http:
        resp = http.get(f"{_base()}/tokens", params=params)
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
