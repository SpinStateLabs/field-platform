"""C-468 (reviewer B-04 F-B04-1): `load_anchors` never reads an absent anchors file as an empty list."""

from __future__ import annotations

import pytest

from sealed_ledger.anchors import AnchorRecord, load_anchors, write_anchor
from sealed_ledger.store import LedgerStore


def ledger(tmp_path, n=3):
    s = LedgerStore(tmp_path / "events.jsonl")
    for i in range(n):
        s.append(f"test.event.{i}", {"i": i})
    return s


def test_an_absent_anchors_file_raises_and_names_the_path(tmp_path):
    missing = tmp_path / "TYPO.jsonl"
    with pytest.raises(FileNotFoundError, match="TYPO.jsonl"):
        load_anchors(missing)


def test_an_absent_anchors_file_is_not_an_empty_list(tmp_path):
    try:
        result = load_anchors(tmp_path / "nope.jsonl")
    except FileNotFoundError:
        return
    pytest.fail(f"an absent file was read as {result!r}")


def test_a_present_anchors_file_loads_its_records_in_order(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "anchors.jsonl"
    first = write_anchor(s, path)
    s.append("test.event.more", {})
    second = write_anchor(s, path)
    loaded = load_anchors(path)
    assert [a.head_hash for a in loaded] == [first.head_hash, second.head_hash]
    assert all(isinstance(a, AnchorRecord) for a in loaded)


def test_an_existing_empty_file_is_an_empty_list_not_an_error(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_bytes(b"")
    assert load_anchors(path) == []
    path.write_bytes(b"\n\n")
    assert load_anchors(path) == []


def test_a_blank_line_between_records_is_skipped(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "anchors.jsonl"
    write_anchor(s, path)
    path.write_bytes(path.read_bytes() + b"\n")
    assert len(load_anchors(path)) == 1
