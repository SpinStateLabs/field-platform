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


def _signed_file(tmp_path, n_events=2, anchors=2):
    """A ledger and an anchors file of `anchors` SIGNED anchors at different positions; returns (store, path, pub, priv)."""
    s = ledger(tmp_path, n_events)
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    for k in range(anchors):
        if k:
            s.append(f"test.event.more{k}", {})
        write_anchor(s, path, private)
    return s, path, public, private


def test_removing_the_newest_anchors_passes_without_a_floor_and_fails_with_one(tmp_path):
    s, path, public, _ = _signed_file(tmp_path)
    full = path.read_text(encoding="utf-8").splitlines()
    path.write_text(full[0] + "\n", encoding="utf-8")                   # the newest anchor is gone
    assert verify_anchors(s, path, public_key_pem=public).ok is True    # what the README says it cannot see
    r = verify_anchors(s, path, public_key_pem=public, min_anchors=2)
    assert r.ok is False and "only 1 signature-verified anchor position(s), --min-anchors 2" in r.first_failure


def test_a_floor_at_or_below_the_count_passes(tmp_path):
    s, path, public, _ = _signed_file(tmp_path)
    assert verify_anchors(s, path, public_key_pem=public, min_anchors=2).ok is True
    assert verify_anchors(s, path, public_key_pem=public, min_anchors=1).ok is True
    assert verify_anchors(s, path, public_key_pem=public, min_anchors=3).ok is False


def test_the_cli_min_anchors_option_fails_a_short_file_and_reports_distinct_positions(tmp_path):
    s, path, public, private = _signed_file(tmp_path, anchors=1)
    write_anchor(s, path, private)                                       # an idle repeat: 2 records, 1 position
    pub = tmp_path / "pub.pem"
    pub.write_text(public, encoding="ascii")
    base = ["verify", "--path", str(tmp_path / "events.jsonl"), "--anchors", str(path), "--pubkey", str(pub)]
    ok = runner.invoke(cli_app, base)
    assert ok.exit_code == 0 and "2 anchor(s) hold" in ok.output and "1 distinct position(s)" in ok.output
    bad = runner.invoke(cli_app, base + ["--min-anchors", "2"])
    assert bad.exit_code == 1 and "ANCHOR FAILURE" in bad.output and "--min-anchors 2" in bad.output
    fine = runner.invoke(cli_app, base + ["--min-anchors", "1"])
    assert fine.exit_code == 0


# --- C-647 (cloud reviewer C-600 F-C600-1/-2): the floor counts only what is verified ----------------------------------


def test_the_floor_is_refused_without_a_public_key(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    r = verify_anchors(s, path, min_anchors=1)
    assert r.ok is False and "needs the public key" in r.first_failure


def test_the_cli_refuses_the_floor_without_a_public_key_or_without_anchors(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    events = str(tmp_path / "events.jsonl")
    r = runner.invoke(cli_app, ["verify", "--path", events, "--anchors", str(path), "--min-anchors", "1"])
    assert r.exit_code == 2 and "--min-anchors needs --anchors and --pubkey" in r.output
    r = runner.invoke(cli_app, ["verify", "--path", events, "--min-anchors", "1"])
    assert r.exit_code == 2 and "--min-anchors needs --anchors and --pubkey" in r.output


def test_an_unsigned_record_added_to_a_short_signed_file_fails_verification_and_never_raises_the_count(tmp_path):
    """The padding attack: the floor says 2, the file has 1 signed position, an editor adds an unsigned record at a
    real chain position. With the key that record is "unsigned but a public key was supplied": a failure, not a count."""
    s, path, public, _ = _signed_file(tmp_path, anchors=1)
    n, head, _first = (s.snapshot().global_length, s.snapshot().hash_at(s.snapshot().global_length - 1), None)
    s.append("test.event.more", {})
    s2 = s.snapshot()
    padded = path.read_text(encoding="utf-8") + line(s2.global_length, s2.hash_at(s2.global_length - 1)) + "\n"
    path.write_text(padded, encoding="utf-8")
    r = verify_anchors(s, path, public_key_pem=public, min_anchors=2)
    assert r.ok is False and "anchor 1: unsigned but a public key was supplied" in r.first_failure


def test_a_forged_signed_looking_record_is_not_counted_either(tmp_path):
    """A record carrying some signature string that does not verify under the key is a failure, not a position."""
    s, path, public, _ = _signed_file(tmp_path, anchors=1)
    s.append("test.event.more", {})
    s2 = s.snapshot()
    forged = line(s2.global_length, s2.hash_at(s2.global_length - 1), signature="AAAA")
    path.write_text(path.read_text(encoding="utf-8") + forged + "\n", encoding="utf-8")
    r = verify_anchors(s, path, public_key_pem=public, min_anchors=2)
    assert r.ok is False and "signature invalid" in r.first_failure


def test_a_position_zero_record_with_any_other_hash_is_a_failure_not_a_position(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    write_anchor(s, path, private)
    forged = tmp_path / "forged.jsonl"
    forged.write_text(_sign_line(private, 0, "f" * 64) + "\n", encoding="utf-8")        # alone, so order does not trip first
    r = verify_anchors(s, forged, public_key_pem=public)
    assert r.ok is False and "position-0 anchor must carry the genesis hash" in r.first_failure


def test_a_position_zero_record_with_the_genesis_hash_counts_as_one_signed_position(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    write_anchor(s, path, private)                                       # the genesis anchor of an empty ledger
    assert verify_anchors(s, path, public_key_pem=public, min_anchors=1).ok is True
    assert verify_anchors(s, path, public_key_pem=public, min_anchors=2).ok is False


def test_a_position_zero_forgery_cannot_raise_the_floor_even_when_signed_by_the_key_holder_only_once(tmp_path):
    """Genesis hash at position 0 is one position however many such records are repeated; an idle repeat counts once."""
    s = LedgerStore(tmp_path / "events.jsonl")
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    for _ in range(3):
        write_anchor(s, path, private)
    r = verify_anchors(s, path, public_key_pem=public, min_anchors=2)
    assert r.ok is False and "only 1 signature-verified anchor position(s)" in r.first_failure


def _sign_line(private_pem, chain_length, head_hash):
    from sealed_ledger.anchors import AnchorRecord, signed_view
    from field_core.signing import sign_manifest

    rec = AnchorRecord(anchored_at="2026-10-30T00:00:00+00:00", chain_length=chain_length, head_hash=head_hash)
    rec.signature = sign_manifest(signed_view(rec), private_pem)
    return rec.model_dump_json(exclude={"segment"})


def _plain_help(args, **env):
    """The help text as a reader sees it: colour codes and the box characters of the rich help panel removed, white
    space collapsed. CI forces colour (FORCE_COLOR), which wraps a word in bold codes and broke a plain `in` check."""
    import re

    out = runner.invoke(cli_app, args, env=env).output
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    return " ".join(re.sub(r"[\u2502\u256d\u256e\u2570\u256f\u2500]", " ", out).split())


@pytest.mark.parametrize("env", [{}, {"FORCE_COLOR": "1", "COLUMNS": "200"}, {"FORCE_COLOR": "1", "COLUMNS": "120", "TERM": "xterm"}])
def test_the_help_says_the_floor_needs_the_key_with_or_without_colour(env):
    text = _plain_help(["verify", "--help"], **env)
    assert "SIGNATURE-VERIFIED" in text and "--pubkey" in text


def test_the_help_and_the_readme_say_the_floor_needs_the_key():
    import pathlib

    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "needs `--pubkey`" in readme and "SIGNATURE-VERIFIED" in readme and "genesis hash" in readme


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


# --- C-721 (reviewers C-688): strict record types, "\n" lines, the floor's usage check first, a visible note ---------------


@pytest.mark.parametrize("bad", ['"3"', "3.0", "true", "false", "null", "-1", "-3", "[3]", '"0"'])
def test_a_chain_length_that_is_not_a_non_negative_integer_is_an_invalid_record(tmp_path, bad):
    path = tmp_path / "a.jsonl"
    path.write_text('{"anchored_at": "2026-10-30T00:00:00+00:00", "chain_length": ' + bad + ', "head_hash": "' + "a" * 64 + '"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_anchors(path)
    s = ledger(tmp_path)
    r = verify_anchors(s, path)
    assert r.ok is False and "not a readable anchor file" in r.first_failure


def test_a_negative_position_no_longer_reaches_the_chain_check_with_a_misleading_text(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    path.write_text(line(-1, "a" * 64) + "\n", encoding="utf-8")
    r = verify_anchors(s, path)
    assert r.ok is False and "archived segment" not in r.first_failure and "out of order" not in r.first_failure


def test_a_genuine_integer_chain_length_still_parses(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text(line(0, "a" * 64) + "\n" + line(7, "b" * 64) + "\n", encoding="utf-8")
    assert [a.chain_length for a in load_anchors(path)] == [0, 7]


def test_two_records_joined_by_a_unicode_line_separator_are_one_bad_line_not_two_records():
    one, two = line(1, "a" * 64), line(2, "b" * 64)
    for sep in (" ", " ", "\x85", "\x0b", "\x0c", "\x1c"):
        with pytest.raises(ValueError):
            parse_anchors((one + sep + two + "\n").encode("utf-8"))


def test_lf_crlf_and_a_missing_final_newline_still_separate_records():
    one, two = line(1, "a" * 64), line(2, "b" * 64)
    assert len(parse_anchors((one + "\n" + two + "\n").encode())) == 2
    assert len(parse_anchors((one + "\r\n" + two + "\r\n").encode())) == 2
    assert len(parse_anchors((one + "\n" + two).encode())) == 2
    assert len(parse_anchors((one + "\n\n  \n" + two + "\n").encode())) == 2


def test_the_api_refuses_a_floor_below_one(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    write_anchor(s, path, private)
    for bad in (0, -1):
        r = verify_anchors(s, path, public_key_pem=public, min_anchors=bad)
        assert r.ok is False and "must be at least 1" in r.first_failure


def test_the_cli_usage_mistake_is_reported_before_the_chain_walk(tmp_path):
    """The usage check runs first: nothing of the verification (no OK line) is printed before the error."""
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    write_anchor(s, path)
    r = runner.invoke(cli_app, ["verify", "--path", str(tmp_path / "events.jsonl"), "--anchors", str(path), "--min-anchors", "1"])
    assert r.exit_code == 2 and "--min-anchors needs --anchors and --pubkey" in r.output
    assert "OK" not in r.output and "events hash-verified" not in r.output


def test_the_cli_says_when_no_floor_was_given_and_does_not_say_it_when_one_was(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    private, public = generate_keypair()
    write_anchor(s, path, private)
    pub = tmp_path / "pub.pem"
    pub.write_text(public, encoding="ascii")
    base = ["verify", "--path", str(tmp_path / "events.jsonl"), "--anchors", str(path), "--pubkey", str(pub)]
    plain = runner.invoke(cli_app, base)
    assert plain.exit_code == 0 and "note: no --min-anchors floor given" in plain.output and "complete off-box copy" in plain.output
    floored = runner.invoke(cli_app, base + ["--min-anchors", "1"])
    assert floored.exit_code == 0 and "note: no --min-anchors floor" not in floored.output


def test_a_failure_does_not_print_the_floor_note(tmp_path):
    s = ledger(tmp_path)
    path = tmp_path / "a.jsonl"
    path.write_text("garbage\n", encoding="utf-8")
    r = runner.invoke(cli_app, ["verify", "--path", str(tmp_path / "events.jsonl"), "--anchors", str(path)])
    assert r.exit_code == 1 and "note: no --min-anchors floor" not in r.output
