"""C-573 (reviewer C-520 F-C520-1..5) with B-16 (reviewer C-482 F-C482-1/-2): the anchors file is parsed once, strictly,
and verified for order, genesis, a floor on its size and a signed record under a key."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from field_core.signing import generate_keypair
from sealed_ledger.anchors import load_anchors, parse_anchors, verify_anchors, write_anchor
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

runner = CliRunner()


def ledger(tmp_path, n=3):
    s = LedgerStore(tmp_path / "events.jsonl")
    for i in range(n):
        s.append(f"test.event.{i}", {"i": i})
    return s


def line(chain_length, head_hash, **extra):
    return json.dumps({"anchored_at": "2026-10-30T00:00:00+00:00", "chain_length": chain_length, "head_hash": head_hash, **extra})


# --- B-16: one parser, and garbage raises -------------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [b"this is not json\n", b'{"chain_length": 3, "head_h', b"\xff\xfe\xfa not utf-8\n",
                                 b'{"anchored_at": "x"}\n', b"[1, 2]\n"])
def test_load_anchors_raises_on_a_garbage_a_truncated_a_non_utf8_or_a_wrong_shape_line(tmp_path, raw):
    path = tmp_path / "a.jsonl"
    path.write_bytes(raw)
    with pytest.raises(ValueError):     # JSONDecodeError, UnicodeDecodeError and ValidationError are all ValueErrors
        load_anchors(path)


def test_verify_anchors_and_load_anchors_agree_on_what_a_file_holds(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    assert [a.head_hash for a in load_anchors(path)] == [a.head_hash for a in parse_anchors(path.read_bytes())]
    path.write_bytes(path.read_bytes() + b"garbage\n")
    with pytest.raises(ValueError):
        load_anchors(path)
    r = verify_anchors(s, path)
    assert r.ok is False and "not a readable anchor file" in r.first_failure


# --- F-C520-5: a byte order mark ----------------------------------------------------------------------------------------


def test_a_utf8_byte_order_mark_is_stripped_not_read_as_garbage(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert len(load_anchors(path)) == 1
    assert verify_anchors(s, path).ok is True


def test_a_byte_order_mark_alone_is_an_empty_file_and_still_a_failure(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    path.write_bytes(b"\xef\xbb\xbf\n")
    assert load_anchors(path) == []
    assert verify_anchors(s, path).ok is False


# --- F-C520-2: order and duplicates ------------------------------------------------------------------------------------


def _snap(s):
    snap = s.snapshot()
    return snap.global_length, snap.hash_at(snap.global_length - 1), snap.hash_at(0)


def test_an_anchor_with_a_lower_chain_length_after_a_higher_one_is_a_failure(tmp_path):
    s = ledger(tmp_path, 4)
    n, head, first = _snap(s)
    path = tmp_path / "a.jsonl"
    path.write_text(line(n, head) + "\n" + line(1, first) + "\n", encoding="utf-8")
    r = verify_anchors(s, path)
    assert r.ok is False and "anchor 1: out of order" in r.first_failure


def test_two_anchors_at_one_position_with_different_hashes_are_a_failure(tmp_path):
    s = ledger(tmp_path, 3)
    n, head, _ = _snap(s)
    path = tmp_path / "a.jsonl"
    path.write_text(line(n, head) + "\n" + line(n, "f" * 64) + "\n", encoding="utf-8")
    r = verify_anchors(s, path)
    assert r.ok is False and "name different hashes" in r.first_failure


def test_an_identical_repeat_is_an_idle_reanchor_and_counts_once(tmp_path):
    s = ledger(tmp_path, 3)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    write_anchor(s, path)
    r = verify_anchors(s, path)
    assert r.ok is True and r.anchors_checked == 2 and r.distinct_positions == 1


def test_anchors_in_order_count_each_position(tmp_path):
    s = ledger(tmp_path, 2)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    s.append("test.event.more", {})
    write_anchor(s, path)
    r = verify_anchors(s, path)
    assert r.ok is True and r.anchors_checked == 2 and r.distinct_positions == 2


# --- F-C520-1: a floor on the number of anchors ------------------------------------------------------------------------


def test_removing_the_newest_anchors_passes_without_a_floor_and_fails_with_one(tmp_path):
    s = ledger(tmp_path, 2)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    s.append("test.event.more", {})
    write_anchor(s, path)
    full = path.read_text(encoding="utf-8").splitlines()
    path.write_text(full[0] + "\n", encoding="utf-8")                   # the newest anchor is gone
    assert verify_anchors(s, path).ok is True                           # what the README says it cannot see
    r = verify_anchors(s, path, min_anchors=2)
    assert r.ok is False and "only 1 distinct anchor position(s), --min-anchors 2" in r.first_failure


def test_a_floor_at_or_below_the_count_passes(tmp_path):
    s = ledger(tmp_path, 2)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    assert verify_anchors(s, path, min_anchors=1).ok is True


def test_the_cli_min_anchors_option_fails_a_short_file_and_reports_distinct_positions(tmp_path):
    s = ledger(tmp_path, 2)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    write_anchor(s, path)
    base = ["verify", "--path", str(tmp_path / "events.jsonl"), "--anchors", str(path)]
    ok = runner.invoke(cli_app, base)
    assert ok.exit_code == 0 and "2 anchor(s) hold" in ok.output and "1 distinct position(s)" in ok.output
    bad = runner.invoke(cli_app, base + ["--min-anchors", "2"])
    assert bad.exit_code == 1 and "ANCHOR FAILURE" in bad.output and "--min-anchors 2" in bad.output


# --- F-C520-3: the genesis anchor --------------------------------------------------------------------------------------


def test_an_anchor_of_an_empty_ledger_verifies_and_still_verifies_after_events_are_appended(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    path = tmp_path / "a.jsonl"
    genesis = write_anchor(s, path)
    assert genesis.chain_length == 0
    assert verify_anchors(s, path).ok is True
    s.append("test.event.1", {})
    s.append("test.event.2", {})
    r = verify_anchors(s, path)
    assert r.ok is True and r.anchors_checked == 1


# --- F-C520-4: an unsigned anchor under a supplied key -----------------------------------------------------------------


def test_an_unsigned_anchor_is_a_failure_when_a_public_key_is_supplied(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)                                               # no private key: unsigned
    _, public = generate_keypair()
    r = verify_anchors(s, path, public_key_pem=public)
    assert r.ok is False and r.first_failure == "anchor 0: unsigned but a public key was supplied"


def test_a_signed_anchor_verifies_under_its_key_and_fails_under_another(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    write_anchor(s, path, private)
    ok = verify_anchors(s, path, public_key_pem=public)
    assert ok.ok is True and ok.signatures_checked == 1
    _, other = generate_keypair()
    bad = verify_anchors(s, path, public_key_pem=other)
    assert bad.ok is False and "signature invalid" in bad.first_failure
