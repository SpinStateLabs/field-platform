"""``attest`` CLI — render."""

from __future__ import annotations

from field_core.authn import auth_headers

import os
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from attestation_reporter import __version__

app = typer.Typer(name="attest", help="Board pack renderer.", no_args_is_help=True)


@app.command()
def version() -> None:
    typer.echo(f"attestation-reporter {__version__}")


@app.command()
def render(
    out: Path = typer.Option(Path("./board-pack"), "--out", help="Output directory"),
    period: str = typer.Option(None, "--period", help='e.g. "Q3 2026"'),
    org: str = typer.Option("Spin State Labs", "--org"),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Attempt headless-browser PDF"),
) -> None:
    """Render the board pack from live services (JSON + HTML, PDF best-effort)."""
    import httpx

    from attestation_reporter.engine import PackEngine
    from attestation_reporter.render import render_html, render_pdf

    def client(env: str, default: str):
        base = os.environ.get(env, default)
        return httpx.Client(base_url=base, timeout=10.0, headers=auth_headers()), base

    registry, registry_base = client("FIELD_REGISTRY_URL", "http://127.0.0.1:8001")
    ledger, ledger_base = client("FIELD_LEDGER_URL", "http://127.0.0.1:8002")
    delegation, delegation_base = client("FIELD_DELEGATION_URL", "http://127.0.0.1:8003")
    governor, governor_base = client("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006")

    engine = PackEngine(
        registry=registry, registry_base=registry_base,
        ledger=ledger, ledger_base=ledger_base,
        delegation=delegation, delegation_base=delegation_base,
        governor=governor, governor_base=governor_base,
        org=org,
    )
    pack = engine.build(period=period)

    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "board-pack.json"
    html_path = out / "board-pack.html"
    json_path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(pack), encoding="utf-8")
    typer.echo(f"written: {json_path}")
    typer.echo(f"written: {html_path}")

    if pdf:
        ok, detail = render_pdf(html_path, out / "board-pack.pdf")
        if ok:
            typer.echo(f"written: {out / 'board-pack.pdf'} ({detail})")
        else:
            typer.echo(f"PDF skipped: {detail}")

    unavailable = [m.name for m in pack.all_metrics() if m.status == "unavailable"]
    if unavailable:
        typer.echo(
            f"note: {len(unavailable)} metric(s) unavailable "
            f"({'; '.join(unavailable[:4])}{'…' if len(unavailable) > 4 else ''})",
            err=True,
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
