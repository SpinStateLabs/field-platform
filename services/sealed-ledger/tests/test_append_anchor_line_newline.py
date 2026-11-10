"""S9-18: `append_anchor_line` never glues a record onto a last line that lacks its newline.

It opened the file in append mode and wrote `record + "\\n"` without looking at the tail. A file whose last line has no newline (a torn
append after a power loss, or an off-box copy saved by a Windows tool that drops the final newline) therefore got `{...}{...}` on one
line; `parse_anchors` splits on "\\n" only, so it raised, `verify_anchors` said "not a readable anchor file" and `load_anchors` raised:
one missing newline made every older anchor in the file unusable. Now, with a non-empty file that does not end in a newline: a last line
that is a complete record gets its newline first; a last line that is a torn partial record is refused by name (LedgerCorrupt, the error
the anchor commands already handle) and nothing is written. fsync and the segment-key-omitted shape are unchanged."""

import json
from pathlib import Path

import pytest

from sealed_ledger.anchors import AnchorRecord, append_anchor_line, load_anchors, verify_anchors, write_anchor
from sealed_ledger.store import LedgerCorrupt, LedgerStore


def rec(n=1, head="a" * 64, segment=None):
    return AnchorRecord(anchored_at="2026-11-07T00:00:00+00:00", chain_length=n, head_hash=head, segment=segment)


def line(r):
    return r.model_dump_json(exclude={"segment"} if r.segment is None else None)


def test_an_absent_file_and_its_parent_directory_are_created(tmp_path):
    path = tmp_path / "deep" / "er" / "anchors.jsonl"
    append_anchor_line(path, rec())
    assert path.read_text(encoding="utf-8") == line(rec()) + "\n"


def test_an_empty_file_gets_the_record_and_one_newline(tmp_path):
    path = tmp_path / "anchors.jsonl"
    path.write_bytes(b"")
    append_anchor_line(path, rec())
    assert path.read_bytes().replace(b"\r\n", b"\n") == (line(rec()) + "\n").encode()      # text mode writes CRLF on Windows (unchanged)


def test_a_normal_append_to_a_newline_terminated_file_adds_exactly_one_line(tmp_path):
    path = tmp_path / "anchors.jsonl"
    append_anchor_line(path, rec(1))
    append_anchor_line(path, rec(2))
    assert path.read_text(encoding="utf-8").split("\n") == [line(rec(1)), line(rec(2)), ""]


def test_a_complete_last_record_without_a_newline_gets_its_newline_first(tmp_path):
    path = tmp_path / "anchors.jsonl"
    path.write_bytes(line(rec(1)).encode())                    # no trailing newline
    append_anchor_line(path, rec(2))
    assert path.read_text(encoding="utf-8") == line(rec(1)) + "\n" + line(rec(2)) + "\n"
    assert [a.chain_length for a in load_anchors(path)] == [1, 2]


def test_a_crlf_terminated_file_is_not_given_an_extra_newline_problem(tmp_path):
    path = tmp_path / "anchors.jsonl"
    path.write_bytes((line(rec(1)) + "\r\n").encode())
    append_anchor_line(path, rec(2))
    assert [a.chain_length for a in load_anchors(path)] == [1, 2]


@pytest.mark.parametrize("tail", ['{"anchored_at": "2026-11-07T00:00:00+00:00", "chain_len', '{"anchored_at"', "{", "garbage",
                                  '{"anchored_at": "x", "chain_length": -1, "head_hash": "h"}'],
                         ids=["torn-key", "torn-early", "brace", "garbage", "invalid-record"])
def test_a_torn_or_invalid_last_line_is_refused_by_name_and_nothing_is_written(tmp_path, tail):
    path = tmp_path / "anchors.jsonl"
    before = (line(rec(1)) + "\n" + tail).encode()
    path.write_bytes(before)
    with pytest.raises(LedgerCorrupt, match="partial record"):
        append_anchor_line(path, rec(2))
    assert path.read_bytes() == before


def test_a_bom_prefixed_file_without_a_final_newline_keeps_its_bom_and_stays_readable(tmp_path):
    path = tmp_path / "anchors.jsonl"
    path.write_bytes(b"\xef\xbb\xbf" + line(rec(1)).encode())
    append_anchor_line(path, rec(2))
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"\n")
    assert [a.chain_length for a in load_anchors(path)] == [1, 2]


def test_a_bom_only_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "anchors.jsonl"
    path.write_bytes(b"\xef\xbb\xbf")
    append_anchor_line(path, rec(1))
    assert [a.chain_length for a in load_anchors(path)] == [1]


def test_the_segment_key_is_omitted_when_none_and_written_when_set(tmp_path):
    path = tmp_path / "anchors.jsonl"
    append_anchor_line(path, rec(1))
    append_anchor_line(path, rec(2, segment=3))
    first, second = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert "segment" not in first and second["segment"] == 3


def test_two_write_anchor_calls_on_a_newline_less_file_verify_ok(tmp_path):
    store = LedgerStore(tmp_path / "events.jsonl")
    for i in range(3):
        store.append(f"test.event.{i}", {"i": i})
    path = tmp_path / "anchors.jsonl"
    write_anchor(store, path)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))           # an off-box copy that lost its final newline
    store.append("test.event.more", {})
    write_anchor(store, path)
    store.append("test.event.more2", {})
    write_anchor(store, path)
    result = verify_anchors(store, path)
    assert result.ok is True and result.anchors_checked == 3, result.first_failure
