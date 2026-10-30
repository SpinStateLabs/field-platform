"""``field`` CLI — validate manifests, list/show templates, verify chains."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

# Windows consoles default to a legacy codepage (cp1252) that cannot encode
# ✓/✗ or em-dashes and corrupts redirected template output. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from field_core import __version__
from field_core.ledger import GENESIS_HASH, LedgerEvent, verify_chain
from field_core.templates_api import TEMPLATE_NAMES, template_text
from field_core.validation import (
    ValidationStatus,
    render_validation_report,
    validate_manifest_file,
)

app = typer.Typer(
    name="field",
    help="FIELD Platform core CLI (Force Field Protocol).",
    no_args_is_help=True,
    # Never render local variables in a traceback: alert-test's frames hold the
    # Bearer header and the topic URL (older typer releases showed locals when
    # rich was installed; pyproject allows typer>=0.12).
    pretty_exceptions_show_locals=False,
)


@app.command()
def version() -> None:
    """Print field-core version."""
    typer.echo(f"field-core {__version__}")


@app.command()
def validate(
    manifest: Path = typer.Argument(
        Path("field-manifest.yaml"), help="Path to a FIELD manifest YAML."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the result as JSON."),
) -> None:
    """Validate a FIELD manifest (parity with the shipped /field validate)."""
    if not manifest.exists():
        typer.echo(f"error: no manifest at {manifest}", err=True)
        raise typer.Exit(code=2)
    result = validate_manifest_file(manifest)
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(render_validation_report(result))
    raise typer.Exit(code=0 if result.status is not ValidationStatus.INVALID else 1)


@app.command()
def templates(
    show: str = typer.Option(None, "--show", help="Print a template by name."),
    out: Path = typer.Option(
        None, "--out", help="With --show: write the template to this path (UTF-8)."
    ),
) -> None:
    """List the four shipped templates, or print one with --show."""
    if show:
        text = template_text(show)
        if out:
            out.write_text(text, encoding="utf-8")
            typer.echo(f"wrote {show} template to {out}")
        else:
            typer.echo(text)
        return
    for name in TEMPLATE_NAMES:
        typer.echo(name)


@app.command("verify-chain")
def verify_chain_cmd(
    # readable=False, like sealed-ledger's `ledger verify --path`: click's default
    # os.stat() then os.access() pre-check fails with exit 2 "is not readable"
    # when a rotation renames the file between the two calls. The open below
    # decides instead, and every way it can fail is a one-line exit 2 (never a
    # traceback): no such file (a mistyped path, or a rotation's rename window)
    # or not readable (permission denied, a directory).
    jsonl: Path = typer.Argument(
        ..., help="Path to a JSONL file of ledger events.", readable=False
    ),
    genesis: str = typer.Option(
        GENESIS_HASH, "--genesis",
        help="prev_hash the first event must carry (default 64 zeros). Pass the "
        "previous segment's head to verify a rotated segment on its own.",
    ),
) -> None:
    """Verify ONE hash-chained JSONL file; report the first break.

    Single-file only: on the open segment of a rotated ledger it reports
    ``link break at index 0`` (its first event continues the closed segment).
    Use ``ledger verify --path FILE`` for the whole rotated ledger."""
    if jsonl.with_name(f"{jsonl.stem}.segments.journal").exists():
        typer.echo(
            f"note: {jsonl} is the open segment of a rotated ledger — use: "
            f"ledger verify --path {jsonl}",
            err=True,
        )
    try:
        with jsonl.open(encoding="utf-8") as fh:
            lines = fh.readlines()  # same lines as iterating the file
    except FileNotFoundError:
        hint = ""
        if jsonl.with_name(f"{jsonl.stem}.segments.journal").exists():
            hint = (" (a rotated ledger: a rotation may have just renamed it — "
                    f"use: ledger verify --path {jsonl})")
        typer.echo(f"error: no such file: {jsonl}{hint}; nothing verified", err=True)
        raise typer.Exit(code=2)
    except OSError as exc:  # permission denied, a directory, ...
        typer.echo(
            f"error: cannot read {jsonl}: {exc.strerror or exc}; nothing verified",
            err=True,
        )
        raise typer.Exit(code=2)
    events = []
    for line_no, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(LedgerEvent.model_validate(json.loads(line)))
        except Exception as exc:  # malformed line is itself a chain failure
            typer.echo(f"TAMPERED — line {line_no} unparseable: {exc}", err=True)
            raise typer.Exit(code=1)
    result = verify_chain(events, genesis)
    if result.ok:
        typer.echo(f"OK — chain intact over {result.length} events")
    else:
        typer.echo(f"TAMPERED — {result.reason}")
        raise typer.Exit(code=1)


def _default_estate() -> str:
    import socket

    return (socket.gethostname() or "unknown")[:64]


@app.command("alert-test")
def alert_test_cmd(
    estate: str = typer.Option(
        None, "--estate",
        help="Estate name shown in the alert, e.g. gb10 or fly (default: host name; a "
             "container or machine host name is often hex and is then withheld)."),
) -> None:
    """Send one clearly marked TEST alert to the ntfy topic configured by
    FIELD_NTFY_TOPIC_FILE / FIELD_NTFY_TOPIC (never a command-line argument).
    Exit 0 delivered, 1 not delivered, 2 configuration missing or unusable
    (nothing was sent). Never prints the topic."""
    from field_core import alerts

    result = alerts.send_test(estate=estate or _default_estate())
    counters = alerts.health_fields()
    summary = (f"alerts_sent={counters['alerts_sent']} alerts_failed={counters['alerts_failed']} "
               f"alerts_content_withheld={counters['alerts_content_withheld']}")
    if result.ok:
        typer.echo(f"alert-test: TEST alert delivered (attempts={result.attempts}); {summary}")
        return
    typer.echo(f"alert-test: TEST alert NOT delivered (reason={result.reason}, "
               f"attempts={result.attempts}); {summary}", err=True)
    raise typer.Exit(code=2 if result.attempts == 0 else 1)


@app.command("alert-topic-init")
def alert_topic_init_cmd(
    out: Path = typer.Option(..., "--out", help="File to write the new topic to."),
    force: bool = typer.Option(False, "--force", help="Replace an existing file."),
) -> None:
    """Write a new unguessable ntfy topic to --out. The topic is never printed:
    the subscriber reads it from the file (docs/runbooks/ntfy-alerts.md)."""
    from field_core import alerts

    try:
        alerts.write_topic_file(out, overwrite=force)
    except FileExistsError:
        typer.echo(f"alert-topic-init: {out} exists; nothing written (use --force to replace)",
                   err=True)
        raise typer.Exit(code=1)
    except OSError as exc:
        typer.echo(f"alert-topic-init: cannot write {out} ({type(exc).__name__}); nothing written",
                   err=True)
        raise typer.Exit(code=2)
    typer.echo(f"alert-topic-init: wrote a new topic to {out} (not shown)")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
