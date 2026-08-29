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


@app.command(name="self-manifest")
def self_manifest() -> None:
    """Validate + print the Crosswalk's own governance manifest (ADR 07).
    Exit 1 if invalid — a governance artifact that fails validation is loud."""
    from field_core.validation import validate_manifest_data

    from compliance_crosswalk.self_manifest import (
        SELF_AGENT_ID,
        load_self_manifest,
        self_manifest_path,
    )

    path = self_manifest_path()
    data = load_self_manifest()
    result = validate_manifest_data(data)
    typer.echo(f"manifest : {path}")
    typer.echo(f"agent    : {SELF_AGENT_ID}")
    typer.echo(f"owner    : {data['identity']['principal']}")
    cap = data["enforcement"]["spend_cap"]
    typer.echo(f"suggestion budget : {cap['currency']} {cap['limit']} "
               f"{cap['period']} (on_breach {cap['on_breach']}) — apply with: "
               f"governor set-cap {SELF_AGENT_ID} --from-manifest <path>")
    typer.echo("scope (generation verbs only):")
    for entry in data["delegation"]["scope"]:
        typer.echo(f"  - {entry}")
    typer.echo(f"valid    : {result.ok}")
    if not result.ok:
        typer.echo("VALIDATION FAILED — the Crosswalk's own governance "
                   "artifact is broken; do not serve.", err=True)
        raise typer.Exit(code=1)


@app.command()
def suggest(
    manifest: Path = typer.Argument(..., help="FIELD manifest YAML"),
) -> None:
    """Gated mapping suggestions for unmapped manifest paths (ADR 07).
    SUGGESTION ONLY — below the precision floor renders as
    'unmapped — review required', never as a mapping."""
    from field_core.validation import load_manifest

    from compliance_crosswalk.suggestions import (
        resolve_suggest_floor,
        resolve_suggester,
        suggest as run_suggest,
    )

    suggester = resolve_suggester()
    if suggester is None:
        typer.echo(
            "suggester disabled (CROSSWALK_SUGGEST=off, the default). Set "
            "CROSSWALK_SUGGEST=mock for the deterministic keyless suggester, "
            "or =anthropic with ANTHROPIC_API_KEY and a governor cap for "
            "'compliance-crosswalk' (no unmetered LLM calls).", err=True)
        raise typer.Exit(code=1)
    if getattr(suggester, "name", "") == "anthropic":  # pragma: no cover
        import os

        import httpx
        from field_core.authn import auth_headers

        base = os.environ.get("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006").rstrip("/")
        try:
            resp = httpx.get(f"{base}/status/compliance-crosswalk",
                             timeout=5.0, headers=auth_headers())
        except Exception as exc:
            typer.echo(f"governor unreachable — refusing unmetered "
                       f"suggestions: {exc}", err=True)
            raise typer.Exit(code=1)
        if resp.status_code != 200:
            typer.echo("no spend cap configured for 'compliance-crosswalk' — "
                       "refusing unmetered suggestions (governor set-cap "
                       "compliance-crosswalk --from-manifest <self-manifest>)",
                       err=True)
            raise typer.Exit(code=1)

    data = load_manifest(manifest)
    results = run_suggest(data, suggester, resolve_suggest_floor())
    for s in results:
        typer.echo(s.model_dump_json())
    candidates = sum(1 for s in results if s.status == "candidate")
    typer.echo(f"\n{len(results)} unmapped path(s): {candidates} candidate(s), "
               f"{len(results) - candidates} 'unmapped — review required'. "
               f"Every entry is a suggestion pending human sign-off.")


@app.command()
def pack(
    manifest: Path = typer.Argument(..., help="FIELD manifest YAML"),
    signer: str = typer.Option(..., "--signer",
                               help="Named human signer — no pack without one"),
    agent_id: str = typer.Option(None, "--agent-id",
                                 help="Collect live evidence for this agent"),
    out_md: Path = typer.Option(None, "--out-md"),
    out_json: Path = typer.Option(None, "--out-json"),
) -> None:
    """Generate the evidence pack (ADR 07). Exit 3 when stale regulatory
    flags block generation — re-review them first (regwatch clear)."""
    import json

    from field_core.validation import load_manifest

    from compliance_crosswalk.api import collect_evidence
    from compliance_crosswalk.evidence_pack import StalePackError, generate_pack
    from compliance_crosswalk.staleness import StaleStore

    data = load_manifest(manifest)
    sources = collect_evidence(agent_id) if agent_id else None
    try:
        md, payload = generate_pack(data, signer=signer,
                                    stale_store=StaleStore(),
                                    agent_id=agent_id, sources=sources)
    except StalePackError as exc:
        typer.echo(f"PACK BLOCKED — stale regulatory corpus: {exc}", err=True)
        typer.echo("re-review with: crosswalk regwatch clear <framework> "
                   "--reviewed-by NAME", err=True)
        raise typer.Exit(code=3)
    if out_md:
        out_md.write_text(md, encoding="utf-8")
        typer.echo(f"pack written to {out_md}")
    if out_json:
        out_json.write_text(json.dumps(payload, indent=2, default=str),
                            encoding="utf-8")
        typer.echo(f"pack json written to {out_json}")
    if not out_md and not out_json:
        typer.echo(md)


regwatch_app = typer.Typer(name="regwatch", no_args_is_help=True,
                           help="Reg-version staleness: mark/clear/report. "
                                "Detection is operator-fed in v0.1; the "
                                "ENFORCEMENT (stale blocks packs) is code.")
app.add_typer(regwatch_app)


@regwatch_app.command(name="status")
def regwatch_status() -> None:
    import json

    from compliance_crosswalk.staleness import StaleStore

    typer.echo(json.dumps(StaleStore().status(), indent=2, default=str))


@regwatch_app.command(name="set-stale")
def regwatch_set_stale(
    framework: str = typer.Argument(...),
    reason: str = typer.Option(..., "--reason"),
    new_version: str = typer.Option(None, "--new-version"),
) -> None:
    """Flag a framework's corpus stale — pack generation blocks until a
    named re-review clears it."""
    from compliance_crosswalk.staleness import StaleStore, affected_controls

    flag = StaleStore().mark(framework, reason, new_version)
    typer.echo(f"stale: {flag['framework']} since {flag['flagged_at']} — "
               f"{flag['reason']}")
    typer.echo(f"affected controls: "
               f"{', '.join(affected_controls(framework)) or 'none cited'}")
    typer.echo("evidence-pack generation is BLOCKED until: crosswalk regwatch "
               "clear " + framework + " --reviewed-by NAME")


@regwatch_app.command(name="clear")
def regwatch_clear(
    framework: str = typer.Argument(...),
    reviewed_by: str = typer.Option(..., "--reviewed-by",
                                    help="Named human re-reviewer"),
) -> None:
    from compliance_crosswalk.staleness import StaleStore

    record = StaleStore().clear(framework, reviewed_by)
    typer.echo(f"cleared: {record['framework']} re-reviewed by "
               f"{record['reviewed_by']} at {record['cleared_at']}")


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
