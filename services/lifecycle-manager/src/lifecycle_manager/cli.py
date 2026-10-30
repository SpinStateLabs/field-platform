"""``lifecycle`` CLI — sweep | provision | decommission | serve.

``sweep`` is the scheduled-job path: point Task Scheduler / cron at
``lifecycle sweep --roster owners.csv``. Exit codes: 0 clean, 3 findings
(including a retention-policy finding from the ledger's ``/retention/check``,
or that check being unavailable, and — where ``FIELD_WITNESS_EVERY`` is set — a
witness finding: no recent ``anchor.remote`` for the watched estate).
``serve`` runs the same sweep behind an HTTP API, optionally on an
in-process interval (``--every``); it is a daemon and has no exit code.

``provision`` and ``decommission`` are the two lifecycle transitions, and
both are deliberately CLI-only: they create and destroy authority, so they
need a human at a keyboard, not an HTTP route anything can reach. Exit
codes: 0 success, 1 refused or partially failed — and a partial run prints
which step stopped it, never a success line.

Phase G (C-2, C-13): ``provision``, ``decommission`` and ``sweep`` take
``--operator-id`` and ``--operator-key-file``, falling back to ``FIELD_OPERATOR``
with ``FIELD_OPERATOR_KEY_FILE`` or ``FIELD_OPERATOR_KEY``. The key file is read
here, stripped, and never printed. The pair is sent ONLY on the guarded routes
in ``GUARDED_ROUTES`` (RT1-10). ``provision`` without ``--grantor`` mints with
``granted_by`` equal to the operator id (a job identity has no
``mint_for_others``, so under ENFORCE that is the only grantor it may name).
Exit 2: the operator flags or key file are unusable (nothing sent).
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
from lifecycle_manager import __version__

# pretty_exceptions_show_locals=False: a verb holds the operator pair in a local, and an
# uncaught exception must never print it (PG0-CLI-R1-06; typer>=0.12 is allowed).
app = typer.Typer(name="lifecycle", help="Authority hygiene sweeps.", no_args_is_help=True,
                  pretty_exceptions_show_locals=False)


# -- Phase G C-2: this CLI's own operator identity --------------------------------------
# (the same block is in the kill-switch and delegation CLIs: the services share no CLI
# package, and field-core's operator_headers() puts the pair on every request)

#: Per service (keyed by its FIELD_<SVC>_URL client), the (method, path relative to
#: that service's base URL) of every guarded route this CLI's verbs call. Nothing
#: else gets the pair: registry and governor reads, token lists, check-ins and
#: ledger appends never carry it.
GUARDED_ROUTES: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "registry": (
        ("POST", re.compile(r"/agents")),               # provision: register
        ("PATCH", re.compile(r"/agents/[^/]+")),        # provision (re-register), decommission: retire
    ),
    "delegation": (
        ("POST", re.compile(r"/tokens")),               # provision: mint
        ("POST", re.compile(r"/tokens/[^/]+/revoke")),  # decommission: revoke
    ),
    "governor": (
        ("PUT", re.compile(r"/caps/[^/]+")),            # provision: cap
        ("PUT", re.compile(r"/rate-limits/[^/]+")),     # provision: rate limits
    ),
    "killswitch": (
        ("POST", re.compile(r"/kill/[^/]+")),           # decommission halt, sweep --auto-kill-orphans
    ),
}
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
               routes: tuple[tuple[str, re.Pattern[str]], ...] = ()) -> bool:
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
                 routes: tuple[tuple[str, re.Pattern[str]], ...] = ()):
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


#: service key -> (URL variable, default) for the estate clients
_SERVICE_URLS = {
    "registry": ("FIELD_REGISTRY_URL", "http://127.0.0.1:8001"),
    "ledger": ("FIELD_LEDGER_URL", "http://127.0.0.1:8002"),
    "delegation": ("FIELD_DELEGATION_URL", "http://127.0.0.1:8003"),
    "killswitch": ("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005"),
    "governor": ("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006"),
}


def _service_client(service: str, pair: tuple[str, str] | None, timeout: float = 20.0):
    var, default = _SERVICE_URLS[service]
    base = os.environ.get(var, default).rstrip("/")
    # trust_env=False: never read the process's proxy variables, and follow_redirects=False: the perimeter secret
    # (and, on guarded routes, the operator pair) must not follow a redirect or an ambient proxy (C-575)
    return base, httpx.Client(base_url=base, timeout=timeout, headers=_perimeter(), trust_env=False,
                              follow_redirects=False,
                              auth=GuardedOperatorAuth(base, pair, GUARDED_ROUTES.get(service, ())))


def estate_clients(pair: tuple[str, str] | None, timeout: float = 20.0) -> dict:
    """Every estate client the verbs use, each carrying x-field-auth on every
    request and the operator pair only on its service's guarded routes. The
    field-core clients get an injected client, so they add nothing of their own
    (their own-client mode would put the env pair on every request)."""
    from field_core.clients import LedgerClient, RegistryClient

    reg_base, reg = _service_client("registry", pair, timeout)
    led_base, led = _service_client("ledger", pair, timeout)
    return {
        "registry": RegistryClient(client=reg, base_url=reg_base),
        "registry_http": reg,
        "delegation": _service_client("delegation", pair, timeout)[1],
        "governor": _service_client("governor", pair, timeout)[1],
        "killswitch": _service_client("killswitch", pair, timeout)[1],
        "ledger": LedgerClient(client=led, base_url=led_base),
    }


_OP_ID = typer.Option(None, "--operator-id", help=OPERATOR_ID_HELP)
_OP_KEY_FILE = typer.Option(None, "--operator-key-file", help=OPERATOR_KEY_FILE_HELP)


@app.command()
def version() -> None:
    typer.echo(f"lifecycle-manager {__version__}")


@app.command()
def sweep(
    roster: Path = typer.Option(
        ..., "--roster",
        help="owners.csv (columns: owner, optional aliases — ';'-separated strings for the same human)",
    ),
    expiry_days: int = typer.Option(30, "--expiry-days"),
    reattest_days: int = typer.Option(90, "--reattest-days"),
    auto_kill_orphans: bool = typer.Option(
        False, "--auto-kill-orphans",
        help="Kill active orphaned agents via kill-switch. NEVER a default.",
    ),
    operator: str = typer.Option("lifecycle-manager (scheduled)", "--operator"),
    markdown: Path = typer.Option(None, "--markdown", help="Write report here"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Sweep registry + delegation for expiring/stale/orphaned authority.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    from lifecycle_manager.engine import (
        LifecycleEngine,
        SweepConfig,
        render_markdown,
        witness_watch_from_env,
    )

    clients = estate_clients(operator_pair(operator_id, operator_key_file), timeout=10.0)
    ledger = clients["ledger"]
    engine = LifecycleEngine(
        registry=clients["registry"],
        delegation=clients["delegation"],
        ledger=ledger,
        killswitch=clients["killswitch"] if auto_kill_orphans else None,
        # The retention policy is checked through the same ledger client. A
        # client that cannot run the check (a stand-in with only `append`) is
        # "not checked", exactly as retention=None.
        retention=ledger if hasattr(ledger, "retention_check") else None,
        # X4: only where this estate runs a witness (FIELD_WITNESS_EVERY set).
        witness=witness_watch_from_env(),
    )
    report = engine.sweep(
        roster_csv=roster.read_text(encoding="utf-8"),
        config=SweepConfig(
            expiry_horizon_days=expiry_days,
            reattestation_days=reattest_days,
            auto_kill_orphans=auto_kill_orphans,
            operator=operator,
        ),
    )
    if markdown:
        markdown.write_text(render_markdown(report), encoding="utf-8")
        typer.echo(f"sweep report written to {markdown}")
    else:
        typer.echo(report.model_dump_json(indent=2))
    # `is not None`, never truthiness: every pydantic model instance is truthy.
    if (report.expiring or report.reattestation_due or report.orphans
            or report.retention_policy is not None or report.witness is not None):
        raise typer.Exit(code=3)


def _provision_clients(pair: tuple[str, str] | None = None):
    """One place that builds the estate clients for the transition verbs."""
    return estate_clients(pair)


@app.command()
def provision(
    manifest: Path = typer.Option(..., "--manifest", help="FIELD manifest YAML"),
    owner: str = typer.Option(..., "--owner", help="Human owner recorded in the registry"),
    domain: str = typer.Option(..., "--domain", help="Operating domain (kill-switch kills by domain)"),
    grantor: str = typer.Option(
        None, "--grantor",
        help="granted_by for the mint (default: the operator id; required without one)",
    ),
    ttl_days: int = typer.Option(..., "--ttl-days", min=1),
    name: str = typer.Option(None, "--name", help="Display name (default: the manifest's agent name)"),
    manifest_ref: str = typer.Option(
        None, "--manifest-ref",
        help="Path the ESTATE will resolve, e.g. /data/manifests/x.yaml "
             "(default: the local --manifest path)",
    ),
    out: Path = typer.Option(None, "--out", help="Write the ProvisionReport JSON here"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Validate a manifest, then register + cap + rate limits + mint for that agent.

    An INVALID manifest (or unloadable enforcement.rate_limits) exits 1 with
    ZERO side effects. After that the steps
    run in order and stop at the first failure — the report says where, and
    nothing is rolled back.

    Without --grantor the mint's granted_by is the operator id (C-13: a job
    identity mints as itself). Without either, exit 2 and nothing is sent.

    Re-provisioning an agent that is already registered with the SAME owner
    and manifest_ref sends no PATCH (registry_outcome "unchanged", P29). A
    different owner or manifest_ref is PATCHed, which needs the registry_edit
    scope: under FIELD_OPERATOR_REQUIRE only don-admin holds it (design v0.4
    2.2.1), so as job-provision-gb10 or don it stops at the register step
    (403), fail closed.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    from lifecycle_manager.engine import LifecycleEngine, LifecycleError

    pair = operator_pair(operator_id, operator_key_file)
    if grantor is None:
        if pair is None:
            _refuse("give --grantor, or an operator identity to mint as (--operator-id with "
                    "--operator-key-file); nothing sent")
        grantor = pair[0]
    elif pair is not None and grantor != pair[0]:
        typer.echo(f"note: --grantor {grantor!r} is not the operator id {pair[0]!r}: under ENFORCE the "
                   "delegation authority accepts it only as an alias of that operator or with "
                   "mint_for_others", err=True)
    engine = LifecycleEngine(**_provision_clients(pair))
    try:
        report = engine.provision(
            manifest_path=manifest, owner=owner, domain=domain, grantor=grantor,
            ttl_days=ttl_days, name=name, manifest_ref=manifest_ref,
        )
    except LifecycleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    payload = report.model_dump_json(indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
        typer.echo(f"provision report written to {out}")
    else:
        typer.echo(payload)
    if not report.ok:
        failed = [s.step for s in report.steps if s.outcome == "failed"]
        typer.echo(
            f"error: provision stopped at {', '.join(failed) or 'an unknown step'} "
            "— the earlier steps were NOT rolled back",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def decommission(
    agent_id: str = typer.Argument(..., help="Registered agent id"),
    by: str = typer.Option(..., "--by", help="Human decommissioning (recorded, not authenticated)"),
    reason: str = typer.Option(..., "--reason"),
    out: Path = typer.Option(None, "--out", help="Write the DecommissionReport JSON here"),
    operator_id: str = _OP_ID,
    operator_key_file: Path = _OP_KEY_FILE,
) -> None:
    """Revoke every token, halt, retire, and record it on the ledger.

    An unknown agent exits 1 with nothing created. An already-retired agent
    is a recorded no-op (exit 0) and gets NO second kill.

    One operator pair is presented to every step, and under
    FIELD_OPERATOR_REQUIRE no single row of design v0.4 2.2.1 completes it:
    the local gate and the retire need decommission (don-admin), the revoke
    and the kill need revoke and kill (don). As don it is refused at the local
    gate (exit 2) before anything is sent. As don-admin the revoke and the
    kill are refused (403) and, act-first, the run goes on to retire the
    agent: exit 1 with its tokens unrevoked and the agent retired, not killed.

    Operator identity: --operator-id ID --operator-key-file PATH
    (the key is read from that file, never from argv).
    """
    from field_core import operator_auth
    from lifecycle_manager.engine import LifecycleEngine, LifecycleError

    # Phase G: a local CLI has no request, so it presents its operator pair
    # (--operator-id/--operator-key-file, else FIELD_OPERATOR with
    # FIELD_OPERATOR_KEY_FILE or FIELD_OPERATOR_KEY) against the same operators
    # file the services read, and again on each guarded route it calls.
    pair = operator_pair(operator_id, operator_key_file)
    presented = ({operator_auth.HEADER_OPERATOR: pair[0], operator_auth.HEADER_KEY: pair[1]}
                 if pair else {})
    try:
        auth = operator_auth.authenticate(presented, "decommission")
    except operator_auth.OperatorRefused as exc:
        typer.echo(f"error: operator auth refused ({exc.status}): {exc.detail}", err=True)
        raise typer.Exit(code=2)
    if auth.mode == operator_auth.LOG_ONLY and not auth.authenticated:
        typer.echo("warning: decommission is not operator-authenticated "
                   f"({auth.failure}); proceeding (log-only mode)", err=True)
    operator_auth.bind(auth)
    by = operator_auth.bind_body_operator(by)
    engine = LifecycleEngine(**_provision_clients(pair))
    try:
        report = engine.decommission(agent_id, by=by, reason=reason)
    except LifecycleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)
    payload = report.model_dump_json(indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
        typer.echo(f"decommission report written to {out}")
    else:
        typer.echo(payload)
    if not report.ok:
        typer.echo(
            "error: decommission ran act-first but did not complete cleanly — "
            "see `steps` above",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8012, "--port"),
    roster: Path = typer.Option(
        None,
        "--roster",
        help="Roster CSV the served sweep uses when a request omits roster_csv. "
        "Defaults to $FIELD_LIFECYCLE_ROSTER; with neither, POST /sweep answers 503.",
    ),
    every: int = typer.Option(
        0,
        "--every",
        envvar="FIELD_LIFECYCLE_EVERY",
        help="Run a sweep every N seconds in a background thread (0 = off, the default). "
        "The scheduler NEVER arms auto-kill: that needs an explicit request body flag.",
    ),
) -> None:
    """Serve GET /health, POST /sweep and GET /findings.

    The scheduler is in-process: it proves the interval fires, not that a cadence
    held on an estate — `GET /findings` carries the `swept_at` that proves a run.
    """
    import uvicorn

    from field_core.clients import LedgerClient
    from lifecycle_manager.api import create_app
    from lifecycle_manager.engine import witness_watch_from_env

    uvicorn.run(create_app(roster_path=roster, every=every, retention=LedgerClient(),
                           witness=witness_watch_from_env()),
                host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
