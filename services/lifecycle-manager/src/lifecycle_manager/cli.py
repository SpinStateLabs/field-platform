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

from lifecycle_manager import __version__

app = typer.Typer(name="lifecycle", help="Authority hygiene sweeps.", no_args_is_help=True)


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
) -> None:
    """Sweep registry + delegation for expiring/stale/orphaned authority."""
    import httpx

    from field_core.clients import LedgerClient, RegistryClient
    from lifecycle_manager.engine import (
        LifecycleEngine,
        SweepConfig,
        render_markdown,
        witness_watch_from_env,
    )

    delegation = httpx.Client(
        base_url=os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003"),
        timeout=10.0,
        headers=auth_headers(),
    )
    killswitch = None
    if auto_kill_orphans:
        killswitch = httpx.Client(
            base_url=os.environ.get("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005"),
            timeout=10.0,
            headers=auth_headers(),
        )
    ledger = LedgerClient()
    engine = LifecycleEngine(
        registry=RegistryClient(),
        delegation=delegation,
        ledger=ledger,
        killswitch=killswitch,
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


def _provision_clients(auto_kill_orphans: bool = False):
    """One place that builds the estate clients for the transition verbs."""
    import httpx

    from field_core.clients import LedgerClient, RegistryClient

    def _client(env: str, default: str) -> "httpx.Client":
        return httpx.Client(
            base_url=os.environ.get(env, default),
            timeout=20.0,
            headers=auth_headers(),
        )

    return {
        "registry": RegistryClient(),
        "registry_http": _client("FIELD_REGISTRY_URL", "http://127.0.0.1:8001"),
        "delegation": _client("FIELD_DELEGATION_URL", "http://127.0.0.1:8003"),
        "governor": _client("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006"),
        "killswitch": _client("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005"),
        "ledger": LedgerClient(),
    }


@app.command()
def provision(
    manifest: Path = typer.Option(..., "--manifest", help="FIELD manifest YAML"),
    owner: str = typer.Option(..., "--owner", help="Human owner recorded in the registry"),
    domain: str = typer.Option(..., "--domain", help="Operating domain (kill-switch kills by domain)"),
    grantor: str = typer.Option(..., "--grantor", help="Human granting the delegation"),
    ttl_days: int = typer.Option(..., "--ttl-days", min=1),
    name: str = typer.Option(None, "--name", help="Display name (default: the manifest's agent name)"),
    manifest_ref: str = typer.Option(
        None, "--manifest-ref",
        help="Path the ESTATE will resolve, e.g. /data/manifests/x.yaml "
             "(default: the local --manifest path)",
    ),
    out: Path = typer.Option(None, "--out", help="Write the ProvisionReport JSON here"),
) -> None:
    """Validate a manifest, then register + cap + rate limits + mint for that agent.

    An INVALID manifest (or unloadable enforcement.rate_limits) exits 1 with
    ZERO side effects. After that the steps
    run in order and stop at the first failure — the report says where, and
    nothing is rolled back.
    """
    from lifecycle_manager.engine import LifecycleEngine, LifecycleError

    engine = LifecycleEngine(**_provision_clients())
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
) -> None:
    """Revoke every token, halt, retire, and record it on the ledger.

    An unknown agent exits 1 with nothing created. An already-retired agent
    is a recorded no-op (exit 0) and gets NO second kill.
    """
    from lifecycle_manager.engine import LifecycleEngine, LifecycleError

    engine = LifecycleEngine(**_provision_clients())
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
