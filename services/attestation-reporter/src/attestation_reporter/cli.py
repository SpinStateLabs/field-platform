"""``attest`` CLI — render | verify | serve."""

from __future__ import annotations

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


def _refuse(message: str) -> typer.Exit:
    typer.echo(f"refused: {message}", err=True)
    return typer.Exit(code=2)


@app.command()
def render(
    out: Path = typer.Option(Path("./board-pack"), "--out", help="Output directory"),
    period: str = typer.Option(None, "--period", help='"2026-Q3" or "Q3 2026" (the UTC quarter)'),
    since: str = typer.Option(None, "--since", help="inclusive ISO 8601 date/timestamp; excludes --period"),
    until: str = typer.Option(None, "--until", help="inclusive ISO 8601 date/timestamp; excludes --period"),
    org: str = typer.Option("Spin State Labs", "--org"),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Attempt headless-browser PDF"),
    signer: str = typer.Option(None, "--signer", help="the named human signing board-pack.json"),
    sign_key: Path = typer.Option(None, "--sign-key", help="Ed25519 PEM private key (with --signer)"),
) -> None:
    """Render the board pack from live services (JSON + HTML, PDF best-effort).

    No --period/--since/--until ⇒ an all-time pack. --signer with --sign-key
    signs board-pack.json; without them the pack is an UNSIGNED DRAFT. Every
    refusal (bad window, blank signer, unusable key) is exit 2 before any
    service is queried or any file is written."""
    from datetime import datetime, timezone

    from attestation_reporter.api import engine_from_env
    from attestation_reporter.render import render_html, render_pdf
    from attestation_reporter.signing import InvalidSigningKey, load_signing_key, sign_pack
    from attestation_reporter.window import InvalidWindow, resolve_window

    now = datetime.now(timezone.utc)
    try:
        resolve_window(period, since, until, now=now)
    except InvalidWindow as exc:
        raise _refuse(str(exc))
    private_pem = None
    if signer is not None or sign_key is not None:
        if signer is None or not signer.strip():
            raise _refuse("--signer must name the human signing the pack (blank refused)")
        if sign_key is None:
            raise _refuse("--signer needs --sign-key (an Ed25519 PEM private key)")
        try:
            private_pem = load_signing_key(sign_key)
        except InvalidSigningKey as exc:
            raise _refuse(str(exc))

    # Same four env URLs + auth_headers() as `attest serve` (shared builder).
    engine = engine_from_env(org=org)
    pack = engine.build(period=period, since=since, until=until, now=now)
    if private_pem is not None:
        pack = sign_pack(pack, signer, private_pem, signed_via="cli")  # F4 provenance: the CLI path

    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "board-pack.json"
    html_path = out / "board-pack.html"
    json_path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(pack), encoding="utf-8")
    typer.echo(f"written: {json_path}")
    typer.echo(f"written: {html_path}")
    typer.echo(f"window: {pack.window.kind} {pack.window.since or '…'} .. {pack.window.until or '…'}")
    if pack.signed:
        typer.echo(f"signed by {pack.signer} via {pack.signed_via} · key {pack.key_fingerprint} · "
                   "the signed artefact is board-pack.json")
    else:
        typer.echo("UNSIGNED DRAFT (signed: false) — pass --signer and --sign-key to sign")

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


@app.command()
def verify(
    pack_json: Path = typer.Argument(..., help="board-pack.json (the signed artefact)"),
    pubkey: Path = typer.Option(..., "--pubkey", help="the signer's Ed25519 PEM public key"),
) -> None:
    """Verify a signed board-pack.json. Exit 0 valid, naming the signer and
    the provenance (signed_via: cli | estate-key; "unrecorded" for a pack
    signed before v1.2 F4); 1 unsigned (nothing to verify), wrong key, altered
    after signing, not canonical JSON (a duplicated key, NaN/Infinity), or
    unreadable input."""
    from attestation_reporter.signing import PackVerificationError, parse_pack_json, verify_pack

    try:
        raw = parse_pack_json(pack_json.read_text(encoding="utf-8"))
        public_pem = pubkey.read_text(encoding="ascii")
    except PackVerificationError as exc:  # a ValueError too: named before the generic read failure
        typer.echo(f"FAILED — {exc}", err=True)
        raise typer.Exit(code=1)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        typer.echo(f"FAILED — cannot read the pack or the key: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=1)
    try:
        facts = verify_pack(raw, public_pem)
    except PackVerificationError as exc:
        typer.echo(f"FAILED — {exc}", err=True)
        raise typer.Exit(code=1)
    via = facts["signed_via"] or "an unrecorded path (signed before v1.2 F4: no signed_via)"
    typer.echo(f"OK — signature valid: signed by {facts['signer']} via {via} at "
               f"{facts['signed_at']}, key {facts['key_fingerprint']}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8013, "--port"),
) -> None:
    """Serve GET /health, /pack (JSON) and /pack.html — windowed by
    ?period= or ?since=/?until=. An unsigned draft unless FIELD_ATTEST_SIGNER
    and FIELD_ATTEST_SIGN_KEY are both set and the key loads (F4): then every
    served pack is signed with the estate key, signed_via "estate-key", and
    /health reports signing on|off|error."""
    import uvicorn

    from attestation_reporter.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
