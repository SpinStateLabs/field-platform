"""Shared helpers for the C2 (retention by rotation) ledger tests.

Not a test module. The basename is unique across CI group 1, which runs
several services' tests in one pytest process without ``__init__.py`` files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from field_core.ledger import compute_event_hash
from field_core.signing import generate_keypair, sign_manifest
from sealed_ledger.store import LedgerStore, journal_path_for

KEY_PRIV, KEY_PUB = generate_keypair()
SLOW = os.environ.get("FIELD_SLOW_TESTS") == "1"  # full spec durations instead of bounded ones


def rotate(store: LedgerStore, reason: str = "test"):
    return store.rotate(private_key_pem=KEY_PRIV, operator="tester", reason=reason)


def fill(store: LedgerStore, n: int, tag: str = "x"):
    return [store.append("action", {"n": i, "tag": tag}, agent_id=f"a{i % 2}") for i in range(n)]


def listing(d: Path) -> dict[str, str]:
    """name -> sha256:size:mtime_ns for every file under ``d`` (recursive)."""
    out = {}
    for root, _dirs, files in os.walk(d):
        for name in files:
            p = Path(root) / name
            st = p.stat()
            out[str(p.relative_to(d))] = (
                f"{hashlib.sha256(p.read_bytes()).hexdigest()}:{st.st_size}:{st.st_mtime_ns}"
            )
    return dict(sorted(out.items()))


def three_segments(d: Path, name: str = "events.jsonl"):
    """4 events + rotate + 3 + rotate + 2 = 11 events.

    seg 1 = global 0..3; seg 2 = 4..7 (rotation event at 4); open seg 3 = 8..10
    (rotation event at 8). Returns (store, path, hashes in global order)."""
    p = d / name
    s = LedgerStore(p)
    hashes = [e.hash for e in fill(s, 4, "seg1")]
    hashes.append(rotate(s, "r1").rotation_event.hash)
    hashes += [e.hash for e in fill(s, 3, "seg2")]
    hashes.append(rotate(s, "r2").rotation_event.hash)
    hashes += [e.hash for e in fill(s, 2, "open")]
    return s, p, hashes


def edit_line(path: Path, idx: int, fn, rehash: bool = False) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[idx])
    fn(rec)
    if rehash:
        rec["hash"] = compute_event_hash(rec)
    lines[idx] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def archive_oldest_for_test(store: LedgerStore, archive_dir: Path) -> dict:
    """Test stand-in for retention apply (c2-ops builds the real verb): the
    journal ``archive`` op under both writer locks FIRST, then the rename, in
    the build spec's order. No sidecar, no age rule, no hold check."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    with store._writer():
        store._ensure_fresh_locked()
        from sealed_ledger.store import parse_journal, read_shared

        js = parse_journal(read_shared(store.journal_path))
        entry = next(e for e in js.closed if not e.get("archived_to"))
        src = store.path.parent / entry["file"]
        data = src.read_bytes()
        store._journal_append_locked({
            "op": "archive", "n": entry["n"], "file": entry["file"],
            "archived_to": str(archive_dir / entry["file"]),
            "sidecar": str(archive_dir / (entry["file"] + ".segment.json")),
            "sha256": hashlib.sha256(data).hexdigest(), "at": "2026-09-12T00:00:00+00:00",
            "operator": "test",
        })
        store._recover_locked()
    os.rename(src, archive_dir / entry["file"])
    return entry


def pre_c2_anchor_line(length: int, head: str, anchored_at: str = "2026-09-01T00:00:00+00:00") -> str:
    """An anchor exactly as the pre-C2 ``write_anchor`` signed and wrote it:
    the three-key record signed, the line without a ``segment`` key."""
    record = {"anchored_at": anchored_at, "chain_length": length, "head_hash": head}
    return json.dumps({**record, "signature": sign_manifest(record, KEY_PRIV)},
                      separators=(",", ":")) + "\n"


def journal_records(p: Path) -> list[dict]:
    return [json.loads(line) for line in journal_path_for(p).read_bytes().split(b"\n") if line.strip()]
