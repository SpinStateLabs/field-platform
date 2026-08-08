"""``crosswalk`` CLI — run | frameworks | serve."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from compliance_crosswalk import __version__

app = typer.Typer(name="crosswalk", help="Compliance crosswalk.", no_args_is_help=True)


@app.command()
def version() -> None:
    typer.echo(f"compliance-crosswalk {__version__}")


@app.command()
def frameworks() -> None:
    from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, INGESTION_LOG

    counts: dict[str, int] = {key: 0 for key in FRAMEWORKS}
    for control in CONTROLS:
        for key, citation in control.citations.items():
            if citation.status == "cited":
                counts[key] += 1
    logged = {e["framework"]: e for e in INGESTION_LOG}
    for key, name in FRAMEWORKS.items():
        entry = logged.get(key, {})
        typer.echo(
            f"{key:12s} {name}\n"
            f"{'':12s} cited on {counts[key]}/{len(CONTROLS)} controls · "
            f"ingested: {entry.get('what', 'nothing')}"
        )


@app.command()
def run(
    manifest: Path = typer.Argument(..., help="FIELD manifest YAML"),
    agent_id: str = typer.Option(None, "--agent-id",
                                 help="Collect live evidence for this agent"),
    markdown: Path = typer.Option(None, "--markdown", help="Write report here"),
) -> None:
    """Evaluate coverage: declared vs. evidenced (offline unless --agent-id)."""
    from compliance_crosswalk.api import collect_evidence
    from compliance_crosswalk.engine import evaluate, render_markdown
    from field_core.validation import load_manifest

    data = load_manifest(manifest)
    sources = collect_evidence(agent_id) if agent_id else None
    report = evaluate(data, agent_id=agent_id, sources=sources)
    if markdown:
        markdown.write_text(render_markdown(report), encoding="utf-8")
        typer.echo(f"crosswalk written to {markdown}")
    else:
        typer.echo(report.model_dump_json(indent=2))
    if not report.manifest_valid:
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8008, "--port"),
) -> None:
    import uvicorn

    from compliance_crosswalk.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
