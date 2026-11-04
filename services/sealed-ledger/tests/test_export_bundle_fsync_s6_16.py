"""S6-16: every bundle file is flushed and fsynced before write_bundle returns, like
anchors.append_anchor_line already does."""

from __future__ import annotations

import os
from pathlib import Path

from sealed_ledger.store import LedgerStore


def test_each_bundle_file_is_flushed_then_fsynced(tmp_path, monkeypatch):
    store = LedgerStore(tmp_path / "events.jsonl")
    for i in range(3):
        store.append("action", {"seq": i}, agent_id="a")
    sizes, real = [], os.fsync

    def spy(fd):
        sizes.append(os.fstat(fd).st_size)     # > 0 only if the handle was flushed first
        return real(fd)
    monkeypatch.setattr(os, "fsync", spy)

    summary = store.export(tmp_path / "exports")

    bundle = Path(summary.bundle_dir)
    assert sorted(p.name for p in bundle.iterdir()) == [
        "chain_proof.json", "events.jsonl", "signature.json", "summary.json"]
    assert len(sizes) >= 4 and all(n > 0 for n in sizes[-4:])
