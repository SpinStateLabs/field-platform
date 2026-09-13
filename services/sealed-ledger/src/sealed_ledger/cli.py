"""``ledger`` CLI — append | verify | anchor | export | verify-export | serve."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from sealed_ledger import __version__
from sealed_ledger.api import create_app, data_path
from sealed_ledger.store import LedgerStore

app = typer.Typer(name="ledger", help="Sealed hash-chained ledger.", no_args_is_help=True)


def _store(path: Path | None) -> LedgerStore:
    return LedgerStore(path or data_path())


@app.command()
def version() -> None:
    typer.echo(f"sealed-ledger {__version__}")


@app.command()
def append(
    event_type: str = typer.Argument(..., help="Event type, e.g. 'action'."),
    payload: str = typer.Option("{}", "--payload", help="JSON object payload."),
    agent_id: str = typer.Option(None, "--agent-id"),
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
) -> None:
    """Append one event to the chain."""
    try:
        payload_obj = json.loads(payload)
        if not isinstance(payload_obj, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        typer.echo(f"error: bad --payload: {exc}", err=True)
        raise typer.Exit(code=2)
    event = _store(path).append(event_type, payload_obj, agent_id)
    typer.echo(event.model_dump_json())


@app.command()
def verify(
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
    anchors: Path = typer.Option(None, "--anchors",
                                 help="Also verify against an anchor file."),
    pubkey: Path = typer.Option(None, "--pubkey",
                                help="Ed25519 public key PEM to verify anchor signatures."),
) -> None:
    """Walk the chain; exit 1 on the first break. With --anchors, also prove
    history was not wholesale-rewritten since each anchor was taken."""
    store = _store(path)
    result = store.verify()
    if result.ok:
        typer.echo(f"OK — chain intact over {result.length} events")
    else:
        typer.echo(f"TAMPERED — {result.reason}")
        raise typer.Exit(code=1)
    if anchors:
        from sealed_ledger.anchors import verify_anchors

        anchor_result = verify_anchors(
            store, anchors,
            public_key_pem=pubkey.read_text(encoding="ascii") if pubkey else None,
        )
        if anchor_result.ok:
            typer.echo(
                f"OK — {anchor_result.anchors_checked} anchor(s) hold "
                f"({anchor_result.signatures_checked} signature(s) verified)"
            )
        else:
            typer.echo(f"ANCHOR FAILURE — {anchor_result.first_failure}")
            raise typer.Exit(code=1)


@app.command()
def anchor(
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
    anchors: Path = typer.Option(..., "--anchors",
                                 help="Anchor JSONL to append to — store it OFF-BOX."),
    key: Path = typer.Option(None, "--key",
                             help="Ed25519 private key PEM to sign the anchor."),
) -> None:
    """Record (chain_length, head_hash) now. Schedule this; ship the file
    off-box or publish the record to a public chain."""
    from sealed_ledger.anchors import write_anchor

    record = write_anchor(
        _store(path), anchors,
        private_key_pem=key.read_text(encoding="ascii") if key else None,
    )
    typer.echo(record.model_dump_json())


@app.command()
def export(
    out_dir: Path = typer.Option(None, "--out-dir",
                                 help="Export directory; the bundle lands in OUT_DIR/<stamp>/."),
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
    since: str = typer.Option(None, "--since", help="ISO 8601 lower bound (inclusive)."),
    until: str = typer.Option(None, "--until", help="ISO 8601 upper bound (inclusive)."),
    agent_id: str = typer.Option(None, "--agent-id"),
    event_type: str = typer.Option(None, "--event-type"),
    sign_key: Path = typer.Option(None, "--sign-key",
                                  help="Ed25519 private key PEM: sign summary + chain_proof."),
) -> None:
    """Auditor export bundle: events.jsonl, summary.json, chain_proof.json
    (hash spine to head), signature.json (signed only with --sign-key)."""
    from sealed_ledger.bundle import InvalidSigningKey
    from sealed_ledger.filters import InvalidTimeBound

    private_key_pem = None
    if sign_key is not None:
        try:
            private_key_pem = sign_key.read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as exc:
            typer.echo(f"error: cannot read --sign-key: {exc}", err=True)
            raise typer.Exit(code=2)
    store = _store(path)
    try:
        summary = store.export(
            out_dir or store.path.parent / "exports",
            since=since,
            until=until,
            agent_id=agent_id,
            event_type=event_type,
            private_key_pem=private_key_pem,
        )
    except (InvalidTimeBound, InvalidSigningKey) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2)
    except OSError as exc:
        typer.echo(f"error: export failed: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(summary.model_dump_json(indent=2))


@app.command("verify-export")
def verify_export(
    bundle: Path = typer.Argument(..., help="Bundle directory (OUT_DIR/<stamp>/)."),
    pubkey: Path = typer.Option(None, "--pubkey",
                                help="Signer's Ed25519 public key PEM; required to attest the spine."),
) -> None:
    """Re-verify an export bundle offline; exit 1 naming the first failing index.
    Unsigned (or no --pubkey): internal consistency only — "spine unverified"."""
    from sealed_ledger.bundle import verify_bundle

    public_key_pem = None
    if pubkey is not None:
        try:
            public_key_pem = pubkey.read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as exc:
            typer.echo(f"error: cannot read --pubkey: {exc}", err=True)
            raise typer.Exit(code=2)
    result = verify_bundle(bundle, public_key_pem=public_key_pem)
    if not result.ok:
        where = (
            f"index {result.first_failing_index}: "
            if result.first_failing_index is not None
            else ""
        )
        typer.echo(f"EXPORT FAILED — {where}{result.reason}")
        raise typer.Exit(code=1)
    if result.event_count:
        span = f"{result.event_count} event(s) at indices {result.first_index}..{result.last_index}"
    else:
        span = "0 events"
    if result.spine_attested:
        typer.echo(
            f"OK — {span}; hashes recomputed; spine {result.first_index}..{result.head_index} "
            f"links to head_hash; signature valid (key {result.key_fingerprint})"
        )
    elif result.signed:
        typer.echo(
            f"OK — {span}; hashes recomputed; internally consistent; spine unverified "
            f"(signed, but no --pubkey given: signature not checked)"
        )
    else:
        typer.echo(
            f"OK — {span}; hashes recomputed; internally consistent; spine unverified (unsigned)"
        )
    typer.echo(f"head_index {result.head_index} head_hash {result.head_hash}")
    if result.unfiltered:
        covered = (
            "the chain was empty"
            if result.head_index is None
            else f"every index 0..{result.head_index} is exported (verified)"
        )
        typer.echo(f"filters: none — {covered}")
    else:
        recorded = ", ".join(
            f"{name}={value!r}" for name, value in (result.filters or {}).items() if value is not None
        )
        typer.echo(f"filters: {recorded} — completeness of a filtered export is not provable")
    if result.contiguous:
        typer.echo(
            f"contiguous: every link from index {result.first_index} to head was recomputed "
            f"from exported events — independent proof = this head_hash equals an off-box "
            f"anchor taken at chain_length {result.head_index + 1}"
        )
    else:
        typer.echo(
            "filtered: spine gaps are hash-only — an off-box anchor match proves the head, "
            "not the exported events; their positions rest on a signature checked with --pubkey"
        )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8002, "--port"),
) -> None:
    """Run the HTTP API."""
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
