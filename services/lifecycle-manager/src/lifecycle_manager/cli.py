"""``lifecycle`` CLI — sweep | serve.

``sweep`` is the scheduled-job path: point Task Scheduler / cron at
``lifecycle sweep --roster owners.csv``. Exit codes: 0 clean, 3 findings.
``serve`` runs the same sweep behind an HTTP API, optionally on an
in-process interval (``--every``); it is a daemon and has no exit code.
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
    roster: Path = typer.Option(..., "--roster", help="owners.csv (column: owner)"),
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
    from lifecycle_manager.engine import LifecycleEngine, SweepConfig, render_markdown

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
    engine = LifecycleEngine(
        registry=RegistryClient(),
        delegation=delegation,
        ledger=LedgerClient(),
        killswitch=killswitch,
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
    if report.expiring or report.reattestation_due or report.orphans:
        raise typer.Exit(code=3)


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

    from lifecycle_manager.api import create_app

    uvicorn.run(create_app(roster_path=roster, every=every), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
