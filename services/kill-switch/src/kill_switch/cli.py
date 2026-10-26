"""``killswitch`` CLI — agent | domain | drill | heartbeat | checkin |
liveness | revive | serve.

Named ``killswitch`` (not ``kill``) so it never shadows the shell builtin.

Phase G (C-2): the guarded verbs (``agent``, ``domain``, ``drill``,
``revive``) take ``--operator-id`` and ``--operator-key-file``, falling back to
``FIELD_OPERATOR`` with ``FIELD_OPERATOR_KEY_FILE`` or ``FIELD_OPERATOR_KEY``.
The key file is read here, stripped, and never printed; the key is never an
argument. The pair is sent ONLY on the guarded routes in ``GUARDED_ROUTES``
(RT1-10): ``heartbeat``, ``checkin`` and ``liveness`` never carry it, even when
the environment names an identity.
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

from field_core import authn
from kill_switch import __version__

# pretty_exceptions_show_locals=False: a verb holds the operator pair in a local, and an
# uncaught exception must never print it (PG0-CLI-R1-06; typer>=0.12 is allowed).
app = typer.Typer(name="killswitch", help="Agent kill switch.", no_args_is_help=True,
                  pretty_exceptions_show_locals=False)


def _base() -> str:
    return os.environ.get("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005").rstrip("/")


# -- Phase G C-2: this CLI's own operator identity --------------------------------------
# (the same block is in the lifecycle and delegation CLIs: the services share no CLI
# package, and field-core's operator_headers() puts the pair on every request)

#: (method, path relative to the kill-switch base URL) of every kill-switch route
#: this CLI calls that carries an operator guard. Nothing else gets the pair.
GUARDED_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"/kill/[^/]+")),
    ("POST", re.compile(r"/kill/domain/[^/]+")),
    ("POST", re.compile(r"/revive/[^/]+")),
    ("POST", re.compile(r"/drill/[^/]+")),
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


def _fail(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    typer.echo(f"error {resp.status_code}: {detail}", err=True)
    raise typer.Exit(code=1)


_OP_ID = typer.Option(None, "--operator-id", help=OPERATOR_ID_HELP)
_OP_KEY_FILE = typer.Option(None, "--operator-key-file", help=OPERATOR_KEY_FILE_HELP)


@app.command()
def version() -> None:
    typer.echo(f"kill-switch {__version__}")


@app.command()
def agent(
    agent_id: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator", help="Human operator"),
    reason: str = typer.Option(..., "--reason"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Kill one agent. One command.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    pair = operator_pair(operator_id, operator_key_file)
    with _client(pair) as http:
        resp = http.post(f"{_base()}/kill/{agent_id}", json={"operator": operator, "reason": reason})
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def domain(
    domain_name: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator"),
    reason: str = typer.Option(..., "--reason"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Kill every agent in a domain.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    pair = operator_pair(operator_id, operator_key_file)
    with _client(pair, timeout=30.0) as http:
        resp = http.post(f"{_base()}/kill/domain/{domain_name}",
                         json={"operator": operator, "reason": reason})
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def drill(
    agent_id: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Timed kill drill: kill, verify propagation, restore. Prints ms.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    pair = operator_pair(operator_id, operator_key_file)
    with _client(pair, timeout=30.0) as http:
        resp = http.post(f"{_base()}/drill/{agent_id}",
                         json={"operator": operator, "reason": "scheduled drill"})
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def heartbeat(agent_id: str = typer.Argument(...)) -> None:
    """Poll an agent's heartbeat; exit 1 if killed."""
    with _client() as http:
        resp = http.get(f"{_base()}/heartbeat/{agent_id}")
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json().get("killed"):
        raise typer.Exit(code=1)


@app.command()
def checkin(agent_id: str = typer.Argument(...)) -> None:
    """Record a liveness check-in (POST); exit 1 if killed. Operator/debug
    verb — real agents call ``FieldAgent.checkin()``."""
    with _client() as http:
        resp = http.post(f"{_base()}/heartbeat/{agent_id}")
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json().get("killed"):
        raise typer.Exit(code=1)


@app.command()
def liveness(
    stale_after: float = typer.Option(
        300.0, "--stale-after", help="Seconds without a check-in that count as stale"
    ),
) -> None:
    """List registry-active agents with no check-in inside the window.

    Stale means no check-in, NOT evidence the process is dead."""
    with _client(timeout=15.0) as http:
        resp = http.get(f"{_base()}/liveness", params={"stale_after": stale_after})
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def revive(
    agent_id: str = typer.Argument(...),
    operator: str = typer.Option(..., "--operator"),
    reason: str = typer.Option("post-incident revive", "--reason"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Revive a killed agent.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    pair = operator_pair(operator_id, operator_key_file)
    with _client(pair) as http:
        resp = http.post(f"{_base()}/revive/{agent_id}", json={"operator": operator, "reason": reason})
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
