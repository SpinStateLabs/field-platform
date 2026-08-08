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
from field_core.ledger import LedgerEvent, verify_chain
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
    jsonl: Path = typer.Argument(..., help="Path to a JSONL file of ledger events."),
) -> None:
    """Verify a hash-chained JSONL ledger file; report the first break."""
    events = []
    with jsonl.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(LedgerEvent.model_validate(json.loads(line)))
            except Exception as exc:  # malformed line is itself a chain failure
                typer.echo(f"TAMPERED — line {line_no} unparseable: {exc}", err=True)
                raise typer.Exit(code=1)
    result = verify_chain(events)
    if result.ok:
        typer.echo(f"OK — chain intact over {result.length} events")
    else:
        typer.echo(f"TAMPERED — {result.reason}")
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
