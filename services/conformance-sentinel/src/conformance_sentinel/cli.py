"""``sentinel`` CLI — check | clauses | serve."""

from __future__ import annotations

from field_core.authn import auth_headers

import os
import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from conformance_sentinel import __version__

app = typer.Typer(name="sentinel", help="Conformance sentinel.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_SENTINEL_URL", "http://127.0.0.1:8004").rstrip("/")


@app.command()
def version() -> None:
    typer.echo(f"conformance-sentinel {__version__}")


@app.command()
def check(
    agent_id: str = typer.Argument(...),
    action: str = typer.Argument(...),
    token_id: str = typer.Option(None, "--token-id"),
    irreversible: bool = typer.Option(False, "--irreversible"),
) -> None:
    """Ask the sentinel; exit 0 ALLOW, 2 ESCALATE, 1 BLOCK."""
    resp = httpx.post(
        f"{_base()}/check",
        json={"agent_id": agent_id, "action": action, "token_id": token_id,
              "irreversible": irreversible},
        timeout=15.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        typer.echo(f"error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(code=1)
    verdict = resp.json()
    typer.echo(resp.text)
    if verdict["decision"] == "BLOCK":
        raise typer.Exit(code=1)
    if verdict["decision"] == "ESCALATE":
        raise typer.Exit(code=2)


@app.command(name="self-manifest")
def self_manifest() -> None:
    """Validate + print the Sentinel's own governance manifest (ADR 02 S4).
    Exit 1 if invalid — a governance artifact that fails validation is loud."""
    from field_core.validation import validate_manifest_data

    from conformance_sentinel.self_manifest import (
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
    typer.echo(f"judge budget : {cap['currency']} {cap['limit']} {cap['period']}"
               f" (on_breach {cap['on_breach']}) — apply with: governor set-cap"
               f" {SELF_AGENT_ID} --from-manifest <path>")
    typer.echo("scope (read-only grounding):")
    for entry in data["delegation"]["scope"]:
        typer.echo(f"  - {entry}")
    typer.echo(f"valid    : {result.ok}")
    if not result.ok:
        typer.echo("VALIDATION FAILED — the Sentinel's own governance artifact "
                   "is broken; do not serve.", err=True)
        raise typer.Exit(code=1)


@app.command()
def clauses() -> None:
    resp = httpx.get(f"{_base()}/clauses", timeout=10.0, headers=auth_headers())
    for cid, text in resp.json().items():
        typer.echo(f"{cid:22s} {text}")


@app.command()
def score(
    out_json: str = typer.Option(None, "--out-json", help="Write the JSON scorecard here."),
    out_md: str = typer.Option(None, "--out-md", help="Write the markdown scorecard here."),
    ledger_down_cmd: str = typer.Option(
        None, "--ledger-down-cmd",
        help="Shell command that stops the estate's sealed-ledger, enabling the "
             "ledger-unreachable seed group (run LAST, ledger left down). Only "
             "use against an ephemeral stack you own — never a shared estate.",
    ),
    manifest_dir: str = typer.Option(
        None, "--manifest-dir",
        help="Where the seed manifest is written; must be readable by the "
             "sentinel process (default: FIELD_MANIFEST_DIR or cwd).",
    ),
) -> None:
    """Run the S2 seeded-violation suite against a LOG-ONLY estate and emit
    the sourced scorecard. Exit 0 = gates pass, 3 = gates fail (ADR 02;
    thresholds proposed, ratified at PoC exit)."""
    import pathlib
    import subprocess

    from conformance_sentinel.measure import (
        MeasurementError,
        build_meta,
        compute_metrics,
        render_json,
        render_markdown,
        run_suite,
    )
    from conformance_sentinel.seeded import build_corpus, provision

    registry_base = os.environ.get("FIELD_REGISTRY_URL", "http://127.0.0.1:8001").rstrip("/")
    delegation_base = os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003").rstrip("/")
    sentinel = httpx.Client(base_url=_base(), timeout=15.0, headers=auth_headers())
    registry = httpx.Client(base_url=registry_base, timeout=10.0, headers=auth_headers())
    delegation = httpx.Client(base_url=delegation_base, timeout=10.0, headers=auth_headers())

    health = sentinel.get("/health")
    if health.status_code != 200:
        typer.echo(f"sentinel /health returned {health.status_code}", err=True)
        raise typer.Exit(code=1)
    mode = health.json().get("mode", "unknown")
    judge_state = health.json().get("judge", "off")

    mdir = pathlib.Path(manifest_dir or os.environ.get("FIELD_MANIFEST_DIR", "."))
    try:
        fixtures = provision(registry=registry, delegation=delegation, manifest_dir=mdir)

        def check(seed):
            r = sentinel.post("/check", json={
                "agent_id": fixtures.agent_id, "action": seed.action,
                "token_id": fixtures.tokens[seed.token_kind]})
            if r.status_code != 200:
                raise MeasurementError(f"/check returned {r.status_code}: {r.text}")
            return r.json()

        ledger_toggle = None
        if ledger_down_cmd:
            def ledger_toggle(down: bool) -> None:
                # Down only: the group runs last; nothing restarts the ledger.
                if down:
                    subprocess.run(ledger_down_cmd, shell=True, check=True)

        results = run_suite(check, build_corpus(), mode=mode,
                            ledger_toggle=ledger_toggle,
                            judge_state=judge_state)
    except MeasurementError as exc:
        typer.echo(f"measurement refused: {exc}", err=True)
        raise typer.Exit(code=1)

    commit = None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, timeout=5).stdout.strip() or None
    except Exception:
        pass

    sc = compute_metrics(results, judge_state=judge_state)
    meta = build_meta(runner="live", mode=mode,
                      ledger_seeds_included=ledger_down_cmd is not None,
                      engine_commit=commit)
    if out_json:
        pathlib.Path(out_json).write_text(render_json(sc, meta), encoding="utf-8")
    if out_md:
        pathlib.Path(out_md).write_text(render_markdown(sc, meta), encoding="utf-8")

    typer.echo(f"seeds run: {sc.run_seed_count}/{sc.total_seeds}"
               + (f" (skipped: {', '.join(sc.skipped_seed_ids)})" if sc.skipped_seed_ids else ""))
    typer.echo(f"gated catch: {len(sc.gated_caught_ids)}/{sc.violation_count}"
               f" = {sc.gated_catch_rate:.1%}  (gate >= 95%)")
    typer.echo(f"structural false-block: {len(sc.false_block_ids)}/{sc.conforming_count}"
               f" = {sc.structural_false_block_rate:.1%}  (gate <= 2%)")
    typer.echo(f"combined false-block incl. semantic gap: {sc.combined_false_block_rate:.1%}")
    typer.echo(f"routing-predicate coverage: {sc.routing_coverage:.1%} (mix-driven)")
    typer.echo(f"would-have-blocked: {sc.would_have_blocked}"
               f"  would-have-escalated: {sc.would_have_escalated}"
               f"  tokens/judgment: {sc.tokens_per_judgment}")
    typer.echo("gates: " + ("PASS" if sc.gates_passed else "FAIL")
               + " (proposed; ratified at PoC exit)")
    if not sc.gates_passed:
        raise typer.Exit(code=3)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8004, "--port"),
) -> None:
    import uvicorn

    from conformance_sentinel.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
