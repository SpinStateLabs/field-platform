"""``ledger`` CLI — append | verify | anchor | export | verify-export | rotate |
hold place/release | retention apply/check | witness run | verify-witness | serve."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from sealed_ledger import __version__
from sealed_ledger.api import create_app, data_path, open_store
from sealed_ledger.store import LedgerStore

app = typer.Typer(name="ledger", help="Sealed hash-chained ledger.", no_args_is_help=True)


def _store(path: Path | None) -> LedgerStore:
    # F2: the signing policy comes from the environment (FIELD_LEDGER_SIGN_KEY,
    # FIELD_LEDGER_REQUIRE_SIGNING), like the served app's.
    return open_store(path or data_path())


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
    """Append one event to the chain (signed when FIELD_LEDGER_SIGN_KEY names a
    usable key; exit 2 if FIELD_LEDGER_REQUIRE_SIGNING=1 refuses it unsigned)."""
    from sealed_ledger.store import SigningRequired

    try:
        payload_obj = json.loads(payload)
        if not isinstance(payload_obj, dict):
            raise ValueError("payload must be a JSON object")
    except ValueError as exc:
        typer.echo(f"error: bad --payload: {exc}", err=True)
        raise typer.Exit(code=2)
    try:
        event = _store(path).append(event_type, payload_obj, agent_id)
    except SigningRequired as exc:
        typer.echo(f"error: append refused: {exc}", err=True)
        raise typer.Exit(code=2)
    typer.echo(event.model_dump_json())


def _busy(message: str) -> None:
    """A snapshot or lock that could not be obtained is NOT evidence of tampering."""
    typer.echo(f"BUSY — {message}; retry", err=True)
    raise typer.Exit(code=4)


def _load_event_pubkey(event_pubkey: Path | None) -> str | None:
    """--event-pubkey must be a readable Ed25519 PUBLIC key PEM (exit 2 otherwise)."""
    if event_pubkey is None:
        return None
    try:
        pem = event_pubkey.read_text(encoding="ascii")
        from field_core.signing import key_fingerprint

        key_fingerprint(pem)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        typer.echo(
            f"error: --event-pubkey is not a readable Ed25519 public key ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=2)
    return pem


def _check_event_signatures(indexed, public_key_pem: str) -> None:
    """F2: after the chain walk, verify every event that carries ``signature``
    under the SIGN public key. Any invalid signature => exit 1 naming the
    (global) index. Unsigned events are reported, never failed: pre-F2
    history and stop-type events accepted with ``signing_failed`` are legal.
    Prints exactly one summary line."""
    from field_core.signing import verify_event_signature

    signed = unsigned = 0
    first_unsigned = first_failed = first_unsigned_after_signed = None
    for index, event in indexed:
        if event.signature is None:
            unsigned += 1
            if first_unsigned is None:
                first_unsigned = index
            if event.signing_failed is True and first_failed is None:
                first_failed = index
            if signed and first_unsigned_after_signed is None:
                first_unsigned_after_signed = index
            continue
        if not verify_event_signature(event, public_key_pem):
            typer.echo(
                f"SIGNATURE INVALID — index {index}: event {event.event_id} ({event.event_type}) "
                "does not verify under --event-pubkey (mutated after signing, or another key)"
            )
            raise typer.Exit(code=1)
        signed += 1

    def fmt(i):
        return "none" if i is None else str(i)

    typer.echo(
        f"signed {signed} unsigned {unsigned} first_unsigned_index {fmt(first_unsigned)} "
        f"first_signing_failed_index {fmt(first_failed)} "
        f"first_unsigned_after_signed {fmt(first_unsigned_after_signed)}"
    )


@app.command()
def verify(
    path: Path = typer.Option(None, "--path", help="Ledger JSONL (default: FIELD_DATA_DIR)."),
    genesis: str = typer.Option(
        None, "--genesis",
        help="Verify the file ALONE, starting from this prev_hash (a closed or archived segment).",
    ),
    anchors: Path = typer.Option(None, "--anchors",
                                 help="Also verify against an anchor file."),
    pubkey: Path = typer.Option(None, "--pubkey",
                                help="Ed25519 public key PEM to verify anchor signatures "
                                "(the ANCHOR key, FIELD_LEDGER_ANCHOR_KEY's public half)."),
    event_pubkey: Path = typer.Option(None, "--event-pubkey",
                                      help="F2: Ed25519 public key PEM of the per-event SIGN key "
                                      "(FIELD_LEDGER_SIGN_KEY's public half). After the chain "
                                      "walk, every event carrying `signature` must verify; "
                                      "unsigned events are counted, not failed."),
) -> None:
    """Walk the chain; exit 1 on the first break (exit 4 if the ledger is busy).
    With --anchors, also prove history was not wholesale-rewritten since each
    anchor was taken. With --event-pubkey (F2), also verify every per-event
    signature and print `signed <n> unsigned <m> first_unsigned_index <i|none>
    first_signing_failed_index <i|none> first_unsigned_after_signed <i|none>`;
    an invalid signature is exit 1 naming the index.

    --path picks the mode: the open segment of a rotated ledger (its
    <stem>.segments.journal exists) => every live segment; an archived
    segment with <file>.segment.json beside it => that file from its sidecar
    (with --pubkey, also the signed rotation anchor); a live closed segment
    <stem>-<n> => that segment against its journal entry; any other file => a
    single file from the genesis hash, as before rotation existed.
    Read-only: never finishes a crashed rotation (the service does)."""
    from sealed_ledger.store import (
        LedgerBusy,
        _parse_events,
        journal_path_for,
        read_shared,
        sidecar_path_for,
        verify_closed_segment,
        verify_segment_file,
    )

    event_pubkey_pem = _load_event_pubkey(event_pubkey)
    target = path or data_path()
    if genesis is not None:
        if anchors:
            typer.echo("error: --anchors needs the whole ledger; not with --genesis", err=True)
            raise typer.Exit(code=2)
        from field_core.ledger import verify_chain

        data = read_shared(target)
        if data is None:
            typer.echo(f"error: no such file {target}", err=True)
            raise typer.Exit(code=2)
        try:
            events = _parse_events(data)
        except ValueError as exc:
            typer.echo(f"TAMPERED — unparseable line: {exc}")
            raise typer.Exit(code=1)
        result = verify_chain(events, genesis)
        if not result.ok:
            typer.echo(f"TAMPERED — {result.reason}")
            raise typer.Exit(code=1)
        typer.echo(f"OK — chain intact over {result.length} events")
        if event_pubkey_pem is not None:
            _check_event_signatures(enumerate(events), event_pubkey_pem)  # indices local to the file
        return
    if not journal_path_for(target).exists() and sidecar_path_for(target).exists():
        if anchors:
            typer.echo(
                "error: --anchors needs the whole ledger; an archived segment is verified "
                "from its sidecar (pass --pubkey to check its signed rotation anchor)",
                err=True,
            )
            raise typer.Exit(code=2)
        side = verify_segment_file(
            target, public_key_pem=pubkey.read_text(encoding="ascii") if pubkey else None
        )
        if not side["ok"]:
            typer.echo(f"TAMPERED — {side['reason']}")
            raise typer.Exit(code=1)
        typer.echo(
            f"OK — segment {side['segment']} of {side['logical']} intact over "
            f"{side['events']} events (global {side['global_first']}..{side['global_last']})"
        )
        if side["signature_checked"]:
            typer.echo("(signed rotation anchor verified: it pins this segment's head and chain_length)")
        else:
            typer.echo("(sidecar claims are unsigned; pass --pubkey to check the signed rotation anchor)")
        if event_pubkey_pem is not None:
            events = _parse_events(read_shared(target) or b"")
            _check_event_signatures(
                ((side["global_first"] + k, e) for k, e in enumerate(events)), event_pubkey_pem)
        return
    if not journal_path_for(target).exists():
        closed = verify_closed_segment(target)
        if closed is not None:
            entry, result = closed
            if anchors:
                typer.echo(
                    "error: --anchors needs the whole ledger; pass the open segment, "
                    "not a closed one",
                    err=True,
                )
                raise typer.Exit(code=2)
            if not result.ok:
                typer.echo(f"TAMPERED — {result.reason}")
                raise typer.Exit(code=1)
            logical = target.stem[: -len(f"-{entry['n']}")] + target.suffix
            typer.echo(
                f"OK — segment {entry['n']} of {logical} intact over "
                f"{result.verified_events} events (global {entry['start_index']}.."
                f"{entry['end_index']})"
            )
            if entry.get("state") == "pending-move":
                typer.echo(f"(archived in the journal to {entry['archived_to']}: a pending move, "
                           "completed by the next retention apply)")
            elif entry.get("state") == "pending-rotation":
                typer.echo(f"(rotation {entry['n']} is pending: the service or the next write "
                           "commits it)")
            if event_pubkey_pem is not None:
                events = _parse_events(read_shared(target) or b"")
                _check_event_signatures(
                    ((entry["start_index"] + k, e) for k, e in enumerate(events)), event_pubkey_pem)
            return
    try:
        store = _store(target)
    except LedgerBusy as exc:
        _busy(str(exc))
    result = store.verify()
    if not result.ok and (result.reason or "").startswith("ledger busy"):
        _busy(result.reason)
    if result.ok:
        typer.echo(f"OK — chain intact over {result.length} events")
        if result.segments is not None:
            typer.echo(
                f"({result.segments} segments, {result.archived_segments} archived; "
                f"{result.verified_events} events hash-verified)"
            )
    else:
        typer.echo(f"TAMPERED — {result.reason}")
        raise typer.Exit(code=1)
    if event_pubkey_pem is not None:
        # F2: every LIVE event (global indices), after the chain walk
        try:
            snap = store.snapshot()
        except LedgerBusy as exc:
            _busy(str(exc))
        _check_event_signatures(snap.indexed_events(), event_pubkey_pem)
    if anchors:
        from sealed_ledger.anchors import verify_anchors

        try:
            anchor_result = verify_anchors(
                store, anchors,
                public_key_pem=pubkey.read_text(encoding="ascii") if pubkey else None,
            )
        except LedgerBusy as exc:
            _busy(str(exc))
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
        if result.head_index is None:
            covered = "the chain was empty"
        elif result.archived_prefix:
            covered = (
                f"every live index {result.archived_prefix}..{result.head_index} is exported "
                f"(verified); indices 0..{result.archived_prefix - 1} are archived — verify "
                "them with ledger verify --path <archived file>"
            )
        else:
            covered = f"every index 0..{result.head_index} is exported (verified)"
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


def _served_base_url(offline: bool) -> str | None:
    """Where a mutating verb goes: the running service (FIELD_LEDGER_URL), or
    the files directly with --offline. Neither => usage error (exit 2)."""
    if offline:
        return None
    url = os.environ.get("FIELD_LEDGER_URL")
    if not url:
        typer.echo(
            "error: set FIELD_LEDGER_URL, or pass --offline with the service stopped", err=True
        )
        raise typer.Exit(code=2)
    return url


def _call_served(base_url: str, method: str, route: str, body: dict | None = None,
                 timeout: float = 60.0):
    """One request to the served ledger. httpx ``base_url`` joining keeps a
    path prefix such as ``/ledger`` (``urllib.parse.urljoin`` would drop it)."""
    import httpx

    from field_core.authn import auth_headers

    try:
        with httpx.Client(base_url=base_url, headers=auth_headers(), timeout=timeout) as client:
            return client.request(method, route.lstrip("/"), json=body)
    except httpx.HTTPError as exc:
        typer.echo(f"error: ledger at {base_url} unreachable: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=2)


def _served_detail(resp) -> str:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    return str(detail) if detail is not None else resp.text


@app.command()
def rotate(
    operator: str = typer.Option(..., "--operator", help="Who is rotating (recorded in the chain)."),
    reason: str = typer.Option(..., "--reason", help="Why (recorded in the chain)."),
    offline: bool = typer.Option(False, "--offline",
                                 help="Rotate the files directly (service stopped)."),
    path: Path = typer.Option(None, "--path", help="With --offline: the open segment."),
    key: Path = typer.Option(None, "--key",
                             help="With --offline: Ed25519 private key PEM "
                             "(default FIELD_LEDGER_ANCHOR_KEY)."),
    anchors: Path = typer.Option(None, "--anchors",
                                 help="Also append the signed rotation anchor to this file "
                                 "— ship it OFF-BOX."),
) -> None:
    """Close the open segment (retention by rotation). Through the service when
    FIELD_LEDGER_URL is set, else only with --offline. Never unsigned: no
    usable key => exit 2 and nothing is written. Exit 4 if the ledger is busy
    (on Windows: another process holds the file open)."""
    from sealed_ledger.anchors import AnchorRecord, append_anchor_line
    from sealed_ledger.api import load_anchor_key
    from sealed_ledger.store import (
        LedgerBusy,
        LedgerCorrupt,
        NoAnchorKey,
        RotationRefused,
        RotationResult,
        SigningRequired,
    )

    if not operator.strip() or not reason.strip():
        typer.echo("error: --operator and --reason must not be blank", err=True)
        raise typer.Exit(code=2)
    base_url = _served_base_url(offline)
    if base_url is not None:
        if path is not None or key is not None:
            typer.echo("error: --path and --key apply only with --offline", err=True)
            raise typer.Exit(code=2)
        resp = _call_served(base_url, "POST", "/rotate", {"operator": operator, "reason": reason})
        detail = _served_detail(resp)
        if resp.status_code == 503 and detail.startswith("ledger busy"):
            _busy(detail)
        if resp.status_code == 500:
            typer.echo(f"error: ledger corrupt: {detail}", err=True)
            raise typer.Exit(code=1)
        if resp.status_code != 200:
            typer.echo(f"error: rotate refused ({resp.status_code}): {detail}", err=True)
            raise typer.Exit(code=2)
        result = RotationResult.model_validate(resp.json())
    else:
        try:
            pem = load_anchor_key(key)
            result = _store(path).rotate(private_key_pem=pem, operator=operator, reason=reason)
        except LedgerBusy as exc:
            _busy(str(exc))
        except (NoAnchorKey, RotationRefused, SigningRequired) as exc:
            typer.echo(f"error: rotate refused: {exc}", err=True)
            raise typer.Exit(code=2)
        except LedgerCorrupt as exc:
            typer.echo(f"error: ledger corrupt: {exc}", err=True)
            raise typer.Exit(code=1)
    if anchors is not None:
        append_anchor_line(anchors, AnchorRecord.model_validate(result.anchor))
    typer.echo(result.model_dump_json(indent=2))


def _served_or_exit(resp, verb: str) -> dict:
    """Map a served mutating verb's status to the CLI's exit codes."""
    detail = _served_detail(resp)
    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code == 423:
        typer.echo(f"LEGAL HOLD — {detail}", err=True)
        raise typer.Exit(code=4)
    if resp.status_code == 503 and detail.startswith("ledger busy"):
        _busy(detail)
    if resp.status_code == 500:
        typer.echo(f"error: ledger corrupt: {detail}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"error: {verb} refused ({resp.status_code}): {detail}", err=True)
    raise typer.Exit(code=2)


def _offline_path_only(base_url: str | None, path: Path | None) -> None:
    if base_url is not None and path is not None:
        typer.echo("error: --path applies only with --offline", err=True)
        raise typer.Exit(code=2)


hold_app = typer.Typer(help="Legal hold: while it is in place, retention apply refuses.",
                       no_args_is_help=True)
app.add_typer(hold_app, name="hold")


@hold_app.command("place")
def hold_place(
    by: str = typer.Option(..., "--by", help="Who places the hold (recorded, not authenticated)."),
    reason: str = typer.Option(..., "--reason", help="Why (recorded in the chain)."),
    offline: bool = typer.Option(False, "--offline", help="Write the files directly (service stopped)."),
    path: Path = typer.Option(None, "--path", help="With --offline: the open segment."),
) -> None:
    """Place the legal hold (legal_hold.json beside the ledger, then a
    ledger.legal_hold.placed event). Exit 2 blank names / already held; 4 busy."""
    from sealed_ledger.store import HoldConflict, LedgerBusy, LedgerCorrupt, SigningRequired

    if not by.strip() or not reason.strip():
        typer.echo("error: --by and --reason must not be blank", err=True)
        raise typer.Exit(code=2)
    base_url = _served_base_url(offline)
    _offline_path_only(base_url, path)
    if base_url is not None:
        record = _served_or_exit(_call_served(base_url, "POST", "/hold", {"by": by, "reason": reason}),
                                 "hold place")
    else:
        try:
            record = _store(path).place_hold(by=by, reason=reason)
        except (HoldConflict, SigningRequired) as exc:
            typer.echo(f"error: hold refused: {exc}", err=True)
            raise typer.Exit(code=2)
        except LedgerBusy as exc:
            _busy(str(exc))
        except LedgerCorrupt as exc:
            typer.echo(f"error: ledger corrupt: {exc}", err=True)
            raise typer.Exit(code=1)
    typer.echo(json.dumps(record, indent=2, ensure_ascii=False))


@hold_app.command("release")
def hold_release(
    by: str = typer.Option(..., "--by", help="Who releases the hold (recorded, not authenticated)."),
    offline: bool = typer.Option(False, "--offline", help="Write the files directly (service stopped)."),
    path: Path = typer.Option(None, "--path", help="With --offline: the open segment."),
) -> None:
    """Release the legal hold (a ledger.legal_hold.released event, then the
    marker is removed). Exit 2 blank name / no hold; 4 busy."""
    from sealed_ledger.store import HoldConflict, LedgerBusy, LedgerCorrupt, SigningRequired

    if not by.strip():
        typer.echo("error: --by must not be blank", err=True)
        raise typer.Exit(code=2)
    base_url = _served_base_url(offline)
    _offline_path_only(base_url, path)
    if base_url is not None:
        record = _served_or_exit(_call_served(base_url, "POST", "/hold/release", {"by": by}),
                                 "hold release")
    else:
        try:
            record = _store(path).release_hold(by=by)
        except (HoldConflict, SigningRequired) as exc:
            typer.echo(f"error: release refused: {exc}", err=True)
            raise typer.Exit(code=2)
        except LedgerBusy as exc:
            _busy(str(exc))
        except LedgerCorrupt as exc:
            typer.echo(f"error: ledger corrupt: {exc}", err=True)
            raise typer.Exit(code=1)
    typer.echo(json.dumps(record, indent=2, ensure_ascii=False))


retention_app = typer.Typer(help="Estate retention: archive old closed segments; check the policy.",
                            no_args_is_help=True)
app.add_typer(retention_app, name="retention")


@retention_app.command("apply")
def retention_apply(
    days: int = typer.Option(..., "--days", min=0,
                             help="Archive closed segments closed more than N days ago."),
    operator: str = typer.Option(..., "--operator", help="Who archives (recorded in the chain)."),
    archive_dir: Path = typer.Option(
        None, "--archive-dir",
        help="Default FIELD_LEDGER_ARCHIVE_DIR, else FIELD_DATA_DIR/ledger-archive. Same filesystem "
        "as the ledger; not inside the live ledger dir.",
    ),
    allow_external: bool = typer.Option(False, "--allow-external",
                                        help="Allow an archive dir outside FIELD_DATA_DIR."),
    offline: bool = typer.Option(False, "--offline", help="Move the files directly (service stopped)."),
    path: Path = typer.Option(None, "--path", help="With --offline: the open segment."),
) -> None:
    """Move closed segments (never the open one) to the archive dir, oldest
    first, each with a <file>.segment.json sidecar; ledgered once as
    ledger.retention.applied. Exit 0 done (also when nothing was due); 1 a
    segment does not verify / corrupt; 2 refused or usage; 4 legal hold or busy."""
    from sealed_ledger.api import data_root, default_archive_dir
    from sealed_ledger.store import (
        ArchiveRefused,
        LedgerBusy,
        LedgerCorrupt,
        LegalHoldActive,
        SigningRequired,
    )

    if not operator.strip():
        typer.echo("error: --operator must not be blank", err=True)
        raise typer.Exit(code=2)
    base_url = _served_base_url(offline)
    _offline_path_only(base_url, path)
    if base_url is not None:
        body = {"days": days, "operator": operator, "allow_external": allow_external}
        if archive_dir is not None:
            body["archive_dir"] = str(archive_dir)  # a path on the LEDGER HOST
        result = _served_or_exit(_call_served(base_url, "POST", "/retention/apply", body),
                                 "retention apply")
    else:
        try:
            result = _store(path).archive_closed_segments(
                older_than_days=days, archive_dir=archive_dir or default_archive_dir(),
                operator=operator, allow_external=allow_external, data_dir=data_root(),
            )
        except LegalHoldActive as exc:
            typer.echo(f"LEGAL HOLD — {exc}", err=True)
            raise typer.Exit(code=4)
        except (ArchiveRefused, SigningRequired) as exc:
            typer.echo(f"error: retention apply refused: {exc}", err=True)
            raise typer.Exit(code=2)
        except LedgerBusy as exc:
            _busy(str(exc))
        except LedgerCorrupt as exc:
            typer.echo(f"error: ledger corrupt: {exc}", err=True)
            raise typer.Exit(code=1)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))


@retention_app.command("check")
def retention_check_cmd(
    offline: bool = typer.Option(False, "--offline",
                                 help="Check in this process (registry from FIELD_REGISTRY_URL)."),
    path: Path = typer.Option(None, "--path", help="With --offline: the open segment."),
) -> None:
    """Estate policy (FIELD_LEDGER_RETENTION_DAYS) vs every registered manifest's
    ledger.retention_days. Prints the JSON; exit 0 when ok, 3 otherwise
    (violation, no estate policy, unresolvable manifest ref, unavailable)."""
    base_url = _served_base_url(offline)
    _offline_path_only(base_url, path)
    if base_url is not None:
        resp = _call_served(base_url, "GET", "/retention/check")
        if resp.status_code != 200:
            typer.echo(f"error: retention check failed ({resp.status_code}): {_served_detail(resp)}",
                       err=True)
            raise typer.Exit(code=2)
        result = resp.json()
    else:
        from field_core.clients import RegistryClient
        from sealed_ledger.retention import retention_check

        result = retention_check(_store(path), RegistryClient()).model_dump(mode="json")
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("ok") is not True:
        raise typer.Exit(code=3)


witness_app = typer.Typer(help="X4 cross-estate witnessing (GB10-initiated).", no_args_is_help=True)
app.add_typer(witness_app, name="witness")


def _witness_logging() -> None:
    import logging

    from sealed_ledger.witness import log

    for old in [h for h in log.handlers if getattr(h, "_field_witness", False)]:
        log.removeHandler(old)
    handler = logging.StreamHandler(sys.stderr)  # the CURRENT stderr (the container log)
    handler.setFormatter(logging.Formatter("%(asctime)s witness %(levelname)s %(message)s"))
    handler._field_witness = True
    log.addHandler(handler)
    log.setLevel(logging.INFO)


@witness_app.command("run")
def witness_run(
    estate: str = typer.Option(..., "--estate", help="This (local) estate's name, e.g. gb10."),
    fly_url: str = typer.Option(..., "--fly-url", help="The remote estate's https origin."),
    every: int = typer.Option(3600, "--every", min=1, help="Seconds between ticks (first tick at start)."),
    once: bool = typer.Option(False, "--once", help="One tick, then exit 0 iff direction 1 appended."),
) -> None:
    """Direction 1: GET <fly-url>/ledger/health, append a signed anchor.remote{estate: fly}
    to the local ledger (FIELD_LEDGER_URL). Direction 2 only with
    FIELD_WITNESS_FLY_SECRET_FILE (D5). Signs with FIELD_LEDGER_ANCHOR_KEY; a failed read
    or an unusable key appends nothing and the loop keeps running."""
    import signal
    import threading
    from datetime import datetime, timezone

    from sealed_ledger import witness as w

    started_at = datetime.now(timezone.utc).isoformat()
    if not estate.strip():
        typer.echo("error: --estate must not be blank", err=True)
        raise typer.Exit(code=2)
    ledger_url = os.environ.get("FIELD_LEDGER_URL")
    if not ledger_url:
        typer.echo("error: set FIELD_LEDGER_URL (the witness appends through the served route)", err=True)
        raise typer.Exit(code=2)
    try:
        w.require_https(fly_url)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2)
    _witness_logging()
    witness = w.Witness(local_estate=estate, fly_url=fly_url, fly=w.build_fly_client(),
                        ledger=w.build_ledger_client(ledger_url), observer=w.observer_record(started_at))
    if once:
        outcome = witness.tick()
        raise typer.Exit(code=0 if outcome.direction1 == "appended" else 1)
    stop = threading.Event()
    try:
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except (ValueError, AttributeError):  # not the main thread
        pass
    w.log.info("witness armed: estate %s, remote %s, every %d s, first tick now", estate, fly_url, every)
    try:
        w.run_loop(witness.tick, every, stop)
    except KeyboardInterrupt:
        pass


@app.command("verify-witness")
def verify_witness_cmd(
    estate: str = typer.Option(..., "--estate", help="Check anchors whose payload.estate is NAME."),
    events_url: str = typer.Option(None, "--events-url",
                                   help="A ledger's /events route holding the anchors (GET)."),
    secret_file: Path = typer.Option(None, "--secret-file",
                                     help="With --events-url: x-field-auth for that ledger (https only)."),
    events_file: Path = typer.Option(None, "--events-file",
                                     help="Events copied out of the witnessing ledger (JSON array or JSONL)."),
    path: Path = typer.Option(None, "--path", help="The LOCAL ledger (default: FIELD_DATA_DIR)."),
    pubkey: Path = typer.Option(None, "--pubkey", help="The witness's Ed25519 public key PEM."),
) -> None:
    """Every anchor.remote{estate: NAME} must hold against the local chain: the hash at
    global index length-1 equals head_hash (and, with --pubkey, the signature verifies).
    The local chain must verify first. Exit 0 only if every anchor holds and at least one
    with length >= 1 held (a length-0 anchor compares nothing); 1 otherwise; 2 usage /
    source unreadable (a redirect is never followed); 4 busy. Only the anchors in the
    source are checked: GET /events serves the witnessing ledger's LIVE segments only."""
    from sealed_ledger import witness as w
    from sealed_ledger.store import LedgerBusy

    if (events_url is None) == (events_file is None):
        typer.echo("error: give exactly one of --events-url or --events-file", err=True)
        raise typer.Exit(code=2)
    if secret_file is not None and events_url is None:
        typer.echo("error: --secret-file applies only with --events-url", err=True)
        raise typer.Exit(code=2)
    public_key_pem = None
    if pubkey is not None:
        try:
            public_key_pem = pubkey.read_text(encoding="ascii")
            from field_core.signing import key_fingerprint

            key_fingerprint(public_key_pem)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            typer.echo(f"error: --pubkey is not a readable Ed25519 public key ({type(exc).__name__})", err=True)
            raise typer.Exit(code=2)
    try:
        if events_file is not None:
            events = w.load_events(events_file.read_bytes())
        else:
            secret = secret_file.read_text(encoding="utf-8").strip() if secret_file is not None else None
            events = w.fetch_events(events_url, secret or None)
    except w.DuplicateKey as exc:
        typer.echo(f"WITNESS FAILED — events source refused: {exc}")
        raise typer.Exit(code=1)
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: events source unreadable: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=2)
    except Exception as exc:  # noqa: BLE001 - transport errors
        typer.echo(f"error: events source unreachable: {type(exc).__name__}", err=True)
        raise typer.Exit(code=2)
    anchors = w.select_anchors(events, estate)
    try:
        store = _store(path)
        chain = store.verify()
        if not chain.ok and (chain.reason or "").startswith("ledger busy"):
            _busy(chain.reason)
        if not chain.ok:
            typer.echo(f"WITNESS FAILED — the local chain does not verify: {chain.reason}")
            raise typer.Exit(code=1)
        snap = store.snapshot()
    except LedgerBusy as exc:
        _busy(str(exc))
    result = w.verify_witness(snap, anchors, estate, public_key_pem=public_key_pem,
                              verified_length=chain.length)
    for line in result.lines:
        typer.echo(line)
    if not result.ok:
        raise typer.Exit(code=1)


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
