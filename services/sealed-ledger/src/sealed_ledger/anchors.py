"""External anchoring — defeating the full-history rewrite.

The chain alone proves internal consistency: an attacker who rewrites the
ENTIRE file from some point onward produces a forgery that passes
``verify_chain``. An anchor pins (chain_length, head_hash) at a moment in
time; verification then demands the current chain still contains that exact
hash at that exact position. Anchors are only as trustworthy as where you
keep them — store the anchor file OFF-BOX (another machine, WORM storage,
or published to a public blockchain via e.g. OpenTimestamps; the record is
one small JSON object). Optional Ed25519 signing binds anchors to the
auditor's key so the anchor file itself is tamper-evident.

Rotated ledgers (C2): positions are GLOBAL indices, resolved through one
consistent snapshot of every live segment. A position inside an archived
segment is an explicit failure, never a silent pass. ``segment`` is set only
on rotation anchors; when it is None it is left OUT of the signed bytes and of
the written line, so every record signed before C2 still verifies.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from field_core.ledger import GENESIS_HASH
from field_core.signing import sign_manifest, verify_manifest
from sealed_ledger.store import LedgerCorrupt, LedgerStore, read_shared


class AnchorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchored_at: str
    chain_length: int
    head_hash: str
    signature: str | None = None  # Ed25519 over the record minus this field
    segment: int | None = None  # C2: the closed segment, on rotation anchors only


def signed_view(anchor: AnchorRecord) -> dict:
    """The bytes the signature covers. ``segment`` is excluded EXPLICITLY when
    None (not ``exclude_none``): pre-C2 records never had the key."""
    exclude = {"signature"}
    if anchor.segment is None:
        exclude.add("segment")
    return anchor.model_dump(exclude=exclude)


class AnchorVerification(BaseModel):
    ok: bool
    anchors_checked: int
    signatures_checked: int
    first_failure: str | None = None
    distinct_positions: int | None = None   # C-573: anchors at different chain positions (a repeat counts once)


def append_anchor_line(anchors_path: str | Path, anchor: AnchorRecord) -> None:
    """Append one record (+ flush + fsync). A record without ``segment`` is
    written without the key, byte-compatible with pre-C2 readers."""
    anchors_path = Path(anchors_path)
    anchors_path.parent.mkdir(parents=True, exist_ok=True)
    exclude = {"segment"} if anchor.segment is None else None
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(anchor.model_dump_json(exclude=exclude) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def write_anchor(
    store: LedgerStore,
    anchors_path: str | Path,
    private_key_pem: str | None = None,
) -> AnchorRecord:
    snap = store.snapshot()  # one consistent (length, head) pair, never a cached head
    length = snap.global_length
    head = snap.head
    if length and head is None:
        raise LedgerCorrupt("cannot anchor: the live chain has a length but no readable head")
    record = {
        "anchored_at": datetime.now(timezone.utc).isoformat(),
        "chain_length": length,
        "head_hash": head if length else GENESIS_HASH,
    }
    signature = sign_manifest(record, private_key_pem) if private_key_pem else None
    anchor = AnchorRecord(**record, signature=signature)
    append_anchor_line(anchors_path, anchor)
    return anchor


def parse_anchors(raw: bytes) -> list[AnchorRecord]:
    """The records of an anchors file's bytes: one JSON object per non-blank line. A UTF-8 byte order mark (a Windows
    editor adds one) is stripped, not read as garbage (C-573, reviewer C-520 F-C520-5). Bad UTF-8, a garbage line or a
    truncated line raises (``UnicodeDecodeError`` or ``ValueError``): the one parser both ``load_anchors`` and
    ``verify_anchors`` use, so they cannot disagree about what a file holds (B-16, reviewer C-482 F-C482-2)."""
    text = raw.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    return [AnchorRecord.model_validate(json.loads(line)) for line in text.splitlines() if line.strip()]


def load_anchors(anchors_path: str | Path) -> list[AnchorRecord]:
    """Every record of an anchors file. An ABSENT file raises ``FileNotFoundError``: it is never read as "no anchors"
    (the fail-open shape C-192 closed for ``verify --anchors``; C-468, reviewer B-04 F-B04-1). An existing file with no
    records is an empty list; deciding whether that is acceptable belongs to the caller (``verify_anchors`` refuses it)."""
    raw = read_shared(anchors_path)
    if raw is None:
        raise FileNotFoundError(f"anchors file does not exist: {anchors_path}")
    return parse_anchors(raw)


def _no_anchors(reason: str) -> AnchorVerification:
    return AnchorVerification(ok=False, anchors_checked=0, signatures_checked=0, first_failure=reason)


def verify_anchors(
    store: LedgerStore,
    anchors_path: str | Path,
    public_key_pem: str | None = None,
    min_anchors: int | None = None,
) -> AnchorVerification:
    """The current chain must still contain every anchored (position, hash).

    Anchors must be in order: a chain_length below an earlier one, or two anchors at one position with different
    hashes, is a failure (C-573 F-C520-2); a repeat of the same (position, hash) is an idle re-anchor and counts once
    in ``distinct_positions``. ``min_anchors`` fails a file with fewer distinct positions: removing the NEWEST anchors
    leaves a valid older prefix that every other check passes, so a caller who knows how many there should be says so
    (F-C520-1); the guarantee that history was not erased depends on this file being the complete, off-box copy.

    An anchors file that is missing, unreadable, unparseable or holds no record is a FAILURE, not "0 anchors
    hold" (C-192, D-26): asked to check anchors, a typo'd path must not read as a pass (as ``witness`` already
    refuses a run that witnessed nothing)."""
    try:
        raw = read_shared(anchors_path)
    except OSError as exc:
        return _no_anchors(f"anchors file {anchors_path} cannot be read ({type(exc).__name__})")
    if raw is None:
        return _no_anchors(f"anchors file {anchors_path} does not exist: nothing can be checked")
    try:
        anchors = parse_anchors(raw)
    except ValueError as exc:     # JSONDecodeError, UnicodeDecodeError and pydantic's ValidationError
        return _no_anchors(f"anchors file {anchors_path} is not a readable anchor file ({type(exc).__name__})")
    if not anchors:
        return _no_anchors(f"anchors file {anchors_path} holds no anchor records: nothing can be checked")
    snap = store.snapshot()
    length = snap.global_length
    signatures_checked = 0
    seen: dict[int, str] = {}
    previous = -1
    for i, anchor in enumerate(anchors):
        if anchor.chain_length < previous:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: out of order — chain_length {anchor.chain_length} after {previous}",
            )
        if seen.setdefault(anchor.chain_length, anchor.head_hash) != anchor.head_hash:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: two anchors at position {anchor.chain_length} name different hashes",
            )
        previous = anchor.chain_length
        if public_key_pem is not None:
            if not anchor.signature:
                return AnchorVerification(
                    ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                    first_failure=f"anchor {i}: unsigned but a public key was supplied",
                )
            if not verify_manifest(signed_view(anchor), anchor.signature, public_key_pem):
                return AnchorVerification(
                    ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                    first_failure=f"anchor {i}: signature invalid — the anchor "
                    "file itself was tampered with",
                )
            signatures_checked += 1
        if anchor.chain_length == 0:
            continue
        if length < anchor.chain_length:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: chain shrank — anchored length "
                f"{anchor.chain_length}, current {length} (history erased)",
            )
        actual = snap.hash_at(anchor.chain_length - 1)
        if actual == "archived":
            entry = snap.archived_entry_for(anchor.chain_length - 1) or {}
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: position {anchor.chain_length} (global index "
                f"{anchor.chain_length - 1}) is in archived segment {entry.get('n')} "
                f"(archived_to {entry.get('archived_to')}) — verify it against the archive "
                "with ledger verify --path <archived file>, not the live chain",
            )
        if actual is None:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: position {anchor.chain_length} (global index "
                f"{anchor.chain_length - 1}) is missing from the live chain (segment file absent)",
            )
        if actual != anchor.head_hash:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: hash at position "
                f"{anchor.chain_length} is {actual[:12]}… but was anchored as "
                f"{anchor.head_hash[:12]}… — history was REWRITTEN",
            )
    if min_anchors is not None and len(seen) < min_anchors:
        return AnchorVerification(
            ok=False, anchors_checked=len(anchors), signatures_checked=signatures_checked,
            distinct_positions=len(seen),
            first_failure=f"only {len(seen)} distinct anchor position(s), --min-anchors {min_anchors}: "
            "the newest anchors may have been removed",
        )
    return AnchorVerification(
        ok=True, anchors_checked=len(anchors), signatures_checked=signatures_checked,
        distinct_positions=len(seen),
    )
