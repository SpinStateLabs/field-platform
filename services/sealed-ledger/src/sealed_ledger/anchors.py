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
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from field_core.signing import sign_manifest, verify_manifest
from sealed_ledger.store import LedgerStore


class AnchorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchored_at: str
    chain_length: int
    head_hash: str
    signature: str | None = None  # Ed25519 over the record minus this field


class AnchorVerification(BaseModel):
    ok: bool
    anchors_checked: int
    signatures_checked: int
    first_failure: str | None = None


def write_anchor(
    store: LedgerStore,
    anchors_path: str | Path,
    private_key_pem: str | None = None,
) -> AnchorRecord:
    events = list(store.iter_events())
    record = {
        "anchored_at": datetime.now(timezone.utc).isoformat(),
        "chain_length": len(events),
        "head_hash": events[-1].hash if events else store.head_hash,
    }
    signature = sign_manifest(record, private_key_pem) if private_key_pem else None
    anchor = AnchorRecord(**record, signature=signature)
    anchors_path = Path(anchors_path)
    anchors_path.parent.mkdir(parents=True, exist_ok=True)
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(anchor.model_dump_json() + "\n")
    return anchor


def load_anchors(anchors_path: str | Path) -> list[AnchorRecord]:
    path = Path(anchors_path)
    if not path.exists():
        return []
    return [
        AnchorRecord.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def verify_anchors(
    store: LedgerStore,
    anchors_path: str | Path,
    public_key_pem: str | None = None,
) -> AnchorVerification:
    """The current chain must still contain every anchored (position, hash)."""
    anchors = load_anchors(anchors_path)
    events = list(store.iter_events())
    signatures_checked = 0
    for i, anchor in enumerate(anchors):
        if public_key_pem is not None:
            if not anchor.signature:
                return AnchorVerification(
                    ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                    first_failure=f"anchor {i}: unsigned but a public key was supplied",
                )
            record = anchor.model_dump(exclude={"signature"})
            if not verify_manifest(record, anchor.signature, public_key_pem):
                return AnchorVerification(
                    ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                    first_failure=f"anchor {i}: signature invalid — the anchor "
                    "file itself was tampered with",
                )
            signatures_checked += 1
        if anchor.chain_length == 0:
            continue
        if len(events) < anchor.chain_length:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: chain shrank — anchored length "
                f"{anchor.chain_length}, current {len(events)} (history erased)",
            )
        actual = events[anchor.chain_length - 1].hash
        if actual != anchor.head_hash:
            return AnchorVerification(
                ok=False, anchors_checked=i, signatures_checked=signatures_checked,
                first_failure=f"anchor {i}: hash at position "
                f"{anchor.chain_length} is {actual[:12]}… but was anchored as "
                f"{anchor.head_hash[:12]}… — history was REWRITTEN",
            )
    return AnchorVerification(
        ok=True, anchors_checked=len(anchors), signatures_checked=signatures_checked
    )
