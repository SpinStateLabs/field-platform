"""`retro` CLI: scan, verify, keygen, synth. No network; reads logs, writes outputs.

Exit codes: 0 ok; 1 verification failed or a usage error; 2 ESCALATE findings
present (so a scheduled scan can alert from its exit status without parsing).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from field_core.signing import generate_keypair

from .engine import run_retro, write_outputs
from .evidence import verify_pack as _verify_pack
from .models import RetroConfig, Verdict
from .parsers import split_lines  # noqa: F401  (kept importable for parity checks)

app = typer.Typer(add_completion=False, help="Agent Incident Retro — offline rogue-agent log review.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_config(path: Optional[Path], **overrides) -> RetroConfig:
    data: dict = {}
    if path is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in overrides.items():
        if value is not None:
            data[key] = value
    return RetroConfig(**data)


@app.command()
def scan(
    logs: list[Path] = typer.Argument(..., help="log files to read (read-only)"),
    out: Path = typer.Option(..., "--out", "-o", help="output directory for report.md + evidence-pack.json"),
    key: Path = typer.Option(..., "--key", "-k", help="Ed25519 private key PEM (make one with `retro keygen`)"),
    fmt: str = typer.Option("clf", "--format", "-f", help="clf | jsonl"),
    preset: str = typer.Option("generic", "--preset", help="jsonl field preset: generic | cloudflare"),
    field: list[str] = typer.Option(None, "--field", help="jsonl override canonical=dotted.path (repeatable)"),
    config: Optional[Path] = typer.Option(None, "--config", help="JSON RetroConfig overrides"),
    gap: Optional[float] = typer.Option(None, "--session-gap-s"),
    no_raw: bool = typer.Option(False, "--no-raw", help="store line hashes only, not raw log text"),
    allow_ip: list[str] = typer.Option(None, "--allow-ip", help="authorized IP/CIDR (repeatable)"),
    allow_ua: list[str] = typer.Option(None, "--allow-ua", help="authorized UA substring (repeatable)"),
    force: bool = typer.Option(False, "--force", help="overwrite existing outputs"),
):
    """Scan LOGS and write a signed evidence pack + report."""
    overrides = {}
    for item in field or []:
        if "=" not in item:
            typer.echo(f"bad --field {item!r}; want canonical=dotted.path", err=True)
            raise typer.Exit(1)
        k, v = item.split("=", 1)
        overrides[k] = v
    cfg = _load_config(
        config,
        session_gap_s=gap,
        include_raw=(False if no_raw else None),
        allow_ips=(allow_ip or None),
        allow_ua_substrings=(allow_ua or None),
    )
    try:
        result = run_retro(list(logs), fmt=fmt, preset=preset, overrides=overrides or None, config=cfg)
        report_path, pack_path = write_outputs(
            result, out, key.read_text(encoding="utf-8"), _now_iso(), list(logs), force=force
        )
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    total_lines = sum(i.lines for i in result.inputs)
    unparsed = sum(i.unparsed for i in result.inputs)
    if total_lines and unparsed / total_lines > 0.5:
        typer.echo(
            f"WARNING: {unparsed}/{total_lines} lines did not parse as {fmt} "
            f"({unparsed / total_lines:.0%}). Wrong --format/--preset? A clean result on "
            f"mostly-unparsed logs is meaningless.",
            err=True,
        )
    v = result.counts["verdicts"]
    typer.echo(f"scanned {result.requests_total} requests in {result.sessions_total} sessions")
    typer.echo(f"ESCALATE {v['ESCALATE']} · REVIEW {v['REVIEW']} · AUTHORIZED {v['AUTHORIZED']} · CLEAR {v['CLEAR']}")
    typer.echo(f"wrote {report_path}")
    typer.echo(f"wrote {pack_path}")
    raise typer.Exit(2 if v["ESCALATE"] else 0)


@app.command()
def verify(
    pack: Path = typer.Argument(..., help="evidence-pack.json to verify"),
    pub: Path = typer.Option(..., "--pub", help="the signer's PUBLIC key PEM, obtained independently"),
    report: Optional[Path] = typer.Option(None, "--report", help="report.md to bind by digest"),
    sources: list[Path] = typer.Option(None, "--sources", help="the original log files, to re-hash every cited line"),
):
    """Verify a pack against a public key you supply (never trust the pack's own)."""
    data = json.loads(pack.read_text(encoding="utf-8"))
    report_bytes = report.read_bytes() if report else None
    source_map = None
    if sources:
        from .parsers import unique_labels

        source_map = {label: p.read_bytes() for p, label in zip(sources, unique_labels(list(sources)))}
    result = _verify_pack(data, pub.read_text(encoding="utf-8"), report_bytes, source_map)
    for check in result.checks:
        typer.echo(f"[{'ok ' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    skipped = []
    if report_bytes is None:
        skipped.append("report not checked (pass --report)")
    if source_map is None:
        skipped.append("source lines not checked (pass --sources)")
    if result.ok:
        note = f" — but {'; '.join(skipped)}" if skipped else ""
        typer.echo(f"VERIFIED{note}")
    else:
        typer.echo("VERIFICATION FAILED")
    raise typer.Exit(0 if result.ok else 1)


@app.command()
def keygen(
    out: Path = typer.Option(..., "--out", "-o", help="write the PRIVATE key PEM here"),
    pub: Optional[Path] = typer.Option(None, "--pub", help="also write the public key PEM here"),
    force: bool = typer.Option(False, "--force"),
):
    """Generate an Ed25519 signing keypair. Keep the private key off-box."""
    for target in (out, pub) if pub else (out,):
        if target.exists() and not force:
            typer.echo(f"{target} exists (use --force)", err=True)
            raise typer.Exit(1)
    private_pem, public_pem = generate_keypair()
    # create the private-key file 0600 from the start, so there is no window in
    # which it exists world-readable (chmod-after-write leaves such a window).
    # The mode in os.open applies only when the file is CREATED; with --force
    # over an existing key the chmod below brings a 0644 file down to 0600.
    import os

    try:
        fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(private_pem)
    except (OSError, ValueError):
        out.write_text(private_pem, encoding="utf-8")  # platforms without O_* modes
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass  # platforms without POSIX modes
    typer.echo(f"wrote private key {out}")
    if pub:
        pub.write_text(public_pem, encoding="utf-8")
        typer.echo(f"wrote public key {pub}")
    else:
        typer.echo(public_pem)


@app.command()
def synth(
    out: Path = typer.Option(..., "--out", "-o", help="write a synthetic combined-log fixture here"),
    seed: int = typer.Option(7, "--seed"),
    force: bool = typer.Option(False, "--force"),
):
    """Write a deterministic SYNTHETIC log (no real traffic) for the demo/tests."""
    from .synth import generate

    if out.exists() and not force:
        typer.echo(f"{out} exists (use --force)", err=True)
        raise typer.Exit(1)
    out.write_text(generate(seed=seed), encoding="utf-8", newline="\n")
    typer.echo(f"wrote {out}")


if __name__ == "__main__":
    app()
