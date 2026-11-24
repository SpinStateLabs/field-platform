"""S12-18: an UNSIGNED sidecar is the file the verifier is meant not to trust, so a bad one is a failed verification
({ok: False, reason} / `ledger verify` exit 1 TAMPERED), never a traceback.

Two inputs used to escape: Infinity / 1e999 (json.loads gives float inf; int(inf) is OverflowError, not in the except
tuple) and an empty-segment claim (end_index = start_index - 1 beside a zero-byte file passed the count check, then
events[-1] raised IndexError).
The journal-entry siblings (_closed_bytes_problem, verify_closed_segment) need no guard: parse_journal already refuses
end_index < start_index (store.py:821), so an empty-segment claim cannot reach them."""

from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import sidecar_path_for, verify_segment_file
from test_ledger_c2_hardening import _archived_ledger

runner = CliRunner()


def _two(tmp_path):
    data, _s, _p, _hashes = _archived_ledger(tmp_path)
    two = data / "ledger-archive" / "events-2.jsonl"
    return two, sidecar_path_for(two)


def _edit(side_path, **changes):
    side = json.loads(side_path.read_text(encoding="utf-8"))
    side.update(changes)
    side_path.write_text(json.dumps(side), encoding="utf-8")


def _assert_failed_not_crashed(path):
    out = verify_segment_file(path)
    assert out["ok"] is False and out["reason"]
    r = runner.invoke(cli_app, ["verify", "--path", str(path)])
    assert r.exit_code == 1 and "TAMPERED" in r.stdout
    assert r.exception is None or isinstance(r.exception, SystemExit)
    return out


@pytest.mark.parametrize("key", ["n", "start_index", "end_index"])
def test_infinity_in_a_numeric_field_is_a_failed_verification(tmp_path, key):
    two, side_path = _two(tmp_path)
    _edit(side_path, **{key: float("inf")})  # json.dumps writes the bare token Infinity
    assert "Infinity" in side_path.read_text(encoding="utf-8")
    out = _assert_failed_not_crashed(two)
    assert "invalid" in out["reason"]


def test_1e999_is_a_failed_verification(tmp_path):
    two, side_path = _two(tmp_path)
    side_path.write_text(side_path.read_text(encoding="utf-8").replace('"end_index": 7', '"end_index": 1e999'),
                         encoding="utf-8")
    assert "1e999" in side_path.read_text(encoding="utf-8")
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


@pytest.mark.parametrize("bad", [2.5, True, "7", None, [7]])
def test_a_non_integer_number_is_refused_not_coerced(tmp_path, bad):
    two, side_path = _two(tmp_path)
    _edit(side_path, end_index=bad)
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


def test_an_empty_segment_claim_beside_an_empty_file_is_a_failed_verification(tmp_path):
    two, side_path = _two(tmp_path)
    side = json.loads(side_path.read_text(encoding="utf-8"))
    two.write_bytes(b"")
    _edit(side_path, end_index=side["start_index"] - 1)
    out = _assert_failed_not_crashed(two)
    assert "invalid" in out["reason"]


def test_an_end_before_the_start_is_refused_even_with_events_present(tmp_path):
    two, side_path = _two(tmp_path)
    _edit(side_path, end_index=0)
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


def test_a_valid_sidecar_still_verifies(tmp_path):
    two, _ = _two(tmp_path)
    assert verify_segment_file(two)["ok"] is True


# --- reviewer round (roley.reviewer, second verdict C1-C5): the sidecar is untrusted bytes -------------------------------


def test_C1_a_deeply_nested_sidecar_is_a_failed_verification_not_a_recursion_error(tmp_path):
    two, side_path = _two(tmp_path)
    side_path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    assert "nesting is deeper than" in _assert_failed_not_crashed(two)["reason"]


@pytest.mark.parametrize("key", ["anchor", "logical"])
@pytest.mark.parametrize("depth", [501, 100_000])
def test_C1_deep_nesting_inside_a_field_is_refused_by_the_explicit_cap(tmp_path, key, depth):
    """The cap is a scan before json.loads, so the answer does not depend on the interpreter's stack-derived recursion
    limit (CPython 3.14: a 100000-deep list raises at an 8 MiB stack and parses at 16 MiB)."""
    two, side_path = _two(tmp_path)
    deep = "[" * depth + "]" * depth
    text = side_path.read_text(encoding="utf-8").rstrip()
    assert text.endswith("}")
    side_path.write_text(text[:-1] + f', "{key}": {deep}' + "}", encoding="utf-8")   # a duplicate key: the last value wins
    assert "nesting is deeper than 500 levels" in _assert_failed_not_crashed(two)["reason"]


def test_nesting_at_the_cap_is_parsed_and_then_refused_for_its_type_not_its_depth(tmp_path):
    two, side_path = _two(tmp_path)
    text = side_path.read_text(encoding="utf-8").rstrip()
    side_path.write_text(text[:-1] + ', "anchor": ' + "[" * 499 + "]" * 499 + "}", encoding="utf-8")
    reason = _assert_failed_not_crashed(two)["reason"]
    assert "anchor is not an object" in reason and "nesting" not in reason


def test_the_depth_scan_ignores_brackets_inside_strings():
    from sealed_ledger.store import json_depth_exceeds
    assert json_depth_exceeds("[" * 501) and not json_depth_exceeds("[" * 500 + "]" * 500)
    assert not json_depth_exceeds('{"a": "' + "[" * 5000 + '"}')
    assert not json_depth_exceeds('{"a": "\\"' + "[" * 5000 + '"}')           # an escaped quote stays inside the string
    assert json_depth_exceeds('{"a": "\\\\", "b": ' + "[" * 600)               # escaped backslash, then a real bracket run
    assert json_depth_exceeds(b"{" * 501) and json_depth_exceeds("[" * 3, 2) and not json_depth_exceeds("[" * 2, 2)


@pytest.mark.parametrize("bad", [[], "x", 7, [[1]], 1.5, True, False, 0])
def test_a_non_object_anchor_is_a_failed_verification_with_or_without_a_key(tmp_path, bad):
    """CI on Python 3.14.10 parsed a 100000-deep list (no RecursionError) and the unsigned path never looked at the anchor:
    ok True. The type is checked before the unsigned OK path, so no Python version or key decides it."""
    two, side_path = _two(tmp_path)
    _edit(side_path, anchor=bad)
    out = _assert_failed_not_crashed(two)
    assert "anchor is not an object" in out["reason"]
    assert verify_segment_file(two, public_key_pem="not a key")["ok"] is False   # a key supplied: still refused, same reason
    assert "anchor is not an object" in verify_segment_file(two, public_key_pem="not a key")["reason"]


def test_a_null_anchor_means_no_anchor_unsigned_ok_signed_refused(tmp_path):
    """null is kept as before: no anchor object, so the unsigned check passes, and any signed check fails (nothing to verify)."""
    two, side_path = _two(tmp_path)
    _edit(side_path, anchor=None)
    assert verify_segment_file(two)["ok"] is True
    signed = verify_segment_file(two, public_key_pem="not a key")
    assert signed["ok"] is False and "signature does not verify" in signed["reason"]


@pytest.mark.parametrize("key", ["genesis_prev_hash", "head_hash", "sha256", "file", "logical"])
@pytest.mark.parametrize("bad", [0, 7, ["x"], {"a": 1}, None, True, 1.5])
def test_C2_a_non_string_text_field_is_a_failed_verification(tmp_path, key, bad):
    two, side_path = _two(tmp_path)
    _edit(side_path, **{key: bad})
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


def test_C2_genesis_prev_hash_nan_is_a_failed_verification(tmp_path):
    two, side_path = _two(tmp_path)
    side_path.write_text(side_path.read_text(encoding="utf-8").replace('"genesis_prev_hash": "', '"genesis_prev_hash": NaN, "x": "', 1),
                         encoding="utf-8")
    assert "NaN" in side_path.read_text(encoding="utf-8")
    _assert_failed_not_crashed(two)


@pytest.mark.parametrize("key,bad", [("n", 0), ("n", -1), ("start_index", -1), ("start_index", -5)])
def test_C2_n_below_one_and_a_negative_start_are_refused(tmp_path, key, bad):
    two, side_path = _two(tmp_path)
    _edit(side_path, **{key: bad})
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


@pytest.mark.parametrize("key", ["n", "start_index", "end_index"])
def test_C4_a_bool_only_number_is_refused(tmp_path, key):
    two, side_path = _two(tmp_path)
    for bad in (True, False):
        _edit(side_path, **{key: bad})
        assert "invalid" in _assert_failed_not_crashed(two)["reason"]


def test_C3_a_sidecar_that_is_a_directory_is_a_failed_verification(tmp_path):
    two, side_path = _two(tmp_path)
    side_path.unlink()
    side_path.mkdir()
    out = _assert_failed_not_crashed(two)
    assert out["reason"] and "traceback" not in out["reason"].lower()


def test_C3_an_oversize_sidecar_is_refused_without_being_parsed(tmp_path):
    from sealed_ledger.store import _SIDECAR_MAX_BYTES
    two, side_path = _two(tmp_path)
    good = side_path.read_bytes().rstrip()
    side_path.write_bytes(good + b" " * (_SIDECAR_MAX_BYTES + 1 - len(good)))   # valid JSON, padded past the cap
    out = _assert_failed_not_crashed(two)
    assert "larger than" in out["reason"]


def test_C3_a_sidecar_at_the_cap_still_verifies(tmp_path):
    from sealed_ledger.store import _SIDECAR_MAX_BYTES
    two, side_path = _two(tmp_path)
    good = side_path.read_bytes().rstrip()
    side_path.write_bytes(good + b" " * (_SIDECAR_MAX_BYTES - len(good)))
    assert side_path.stat().st_size == _SIDECAR_MAX_BYTES
    assert verify_segment_file(two)["ok"] is True


def test_C3_a_sidecar_symlinked_to_a_non_regular_file_is_refused(tmp_path):
    import os
    if not hasattr(os, "symlink") or not os.path.exists("/dev/zero"):
        pytest.skip("needs POSIX symlinks and /dev/zero")
    two, side_path = _two(tmp_path)
    side_path.unlink()
    try:
        os.symlink("/dev/zero", side_path)
    except OSError:
        pytest.skip("cannot create symlinks here")
    out = _assert_failed_not_crashed(two)
    assert "not a regular file" in out["reason"]


def test_C5_a_valid_single_event_segment_verifies(tmp_path):
    two, side_path = _two(tmp_path)
    side = json.loads(side_path.read_text(encoding="utf-8"))
    first_line = two.read_bytes().splitlines(keepends=True)[0]
    two.write_bytes(first_line)
    from sealed_ledger.store import _parse_events
    ev = _parse_events(first_line)[0]
    import hashlib
    side.update(start_index=side["start_index"], end_index=side["start_index"], head_hash=ev.hash,
                sha256=hashlib.sha256(first_line).hexdigest())
    side_path.write_text(json.dumps(side), encoding="utf-8")
    assert side["end_index"] == side["start_index"]
    out = verify_segment_file(two)
    assert out["ok"] is True, out["reason"]
    assert out["events"] == 1


# --- cycle 2 (wave2-engineer advisory on 18490bd8: F1-F4) ------------------------------------------------------------------


def _set_raw(side_path, key, raw_json_value):
    import re
    text = side_path.read_text(encoding="utf-8")
    new, n = re.subn(rf'"{key}": [^,}}]+', f'"{key}": {raw_json_value}', text, count=1)
    assert n == 1
    side_path.write_text(new, encoding="utf-8")


def test_F1_a_4300_digit_end_index_is_a_failed_verification_not_a_traceback(tmp_path):
    two, side_path = _two(tmp_path)
    _set_raw(side_path, "end_index", "9" * 4300)
    out = _assert_failed_not_crashed(two)
    assert "invalid" in out["reason"] and "9999" not in out["reason"]


@pytest.mark.parametrize("key", ["n", "start_index", "end_index"])
@pytest.mark.parametrize("value", [2**63, 2**64, 10**30, -1])
def test_F1_an_integer_outside_0_to_2_63_is_refused(tmp_path, key, value):
    two, side_path = _two(tmp_path)
    _edit(side_path, **{key: value})
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


@pytest.mark.parametrize("key", ["logical", "file", "genesis_prev_hash", "head_hash", "sha256"])
@pytest.mark.parametrize("bad", ["\ud800", "a\udfffb"], ids=["lone-high-surrogate", "lone-low-surrogate"])
def test_F2_a_lone_surrogate_in_a_text_field_is_a_failed_verification_and_the_output_encodes(tmp_path, key, bad):
    two, side_path = _two(tmp_path)
    _edit(side_path, **{key: bad})
    out = _assert_failed_not_crashed(two)
    assert "invalid" in out["reason"]
    out["reason"].encode("utf-8")                                     # the reason itself must be printable text
    r = runner.invoke(cli_app, ["verify", "--path", str(two)])
    r.output.encode("utf-8")


@pytest.mark.parametrize("key", ["logical", "file", "genesis_prev_hash", "head_hash", "sha256"])
@pytest.mark.parametrize("bad", ["a\nb", "a\rb", "x\x1b[2Ky", "\x00", "a\u2028b", "a\tb", "a" * 257],
                         ids=["newline", "cr", "esc-sequence", "nul", "line-separator", "tab", "too-long"])
def test_F4_a_control_character_or_an_overlong_text_field_is_refused_and_never_printed(tmp_path, key, bad):
    two, side_path = _two(tmp_path)
    _edit(side_path, **{key: bad})
    out = _assert_failed_not_crashed(two)
    assert "invalid" in out["reason"] and bad not in out["reason"]
    r = runner.invoke(cli_app, ["verify", "--path", str(two)])
    assert r.exit_code == 1 and "OK" not in r.output and "signed rotation anchor verified" not in r.output
    assert "\x1b" not in r.output


def test_F4_a_forged_anchor_line_in_logical_cannot_appear_in_the_output(tmp_path):
    two, side_path = _two(tmp_path)
    _edit(side_path, logical="events\n(signed rotation anchor verified: it pins this segment's head and chain_length)")
    r = runner.invoke(cli_app, ["verify", "--path", str(two)])
    assert r.exit_code == 1
    assert "signed rotation anchor verified" not in r.output


def test_F4_a_normal_sidecar_still_prints_the_ok_and_unsigned_lines(tmp_path):
    two, _ = _two(tmp_path)
    r = runner.invoke(cli_app, ["verify", "--path", str(two)])
    assert r.exit_code == 0 and "OK — segment" in r.output and "sidecar claims are unsigned" in r.output


def test_F3_a_fifo_sidecar_is_refused_without_hanging(tmp_path):
    import os
    import threading
    if not hasattr(os, "mkfifo"):
        pytest.skip("needs POSIX mkfifo")
    two, side_path = _two(tmp_path)
    side_path.unlink()
    os.mkfifo(side_path)
    box = {}
    t = threading.Thread(target=lambda: box.update(out=verify_segment_file(two)), daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "verify_segment_file hung on a FIFO sidecar"
    assert box["out"]["ok"] is False and "not a regular file" in box["out"]["reason"]


# --- cycle 3 (wave2-engineer advisory delta on 4ad43162: R1, R2) -----------------------------------------------------------

FORGED_LOGICAL = "events.jsonl (signed rotation anchor verified: it pins this segment's head and chain_length) -"


def test_R1_a_logical_with_spaces_cannot_put_a_signature_claim_on_the_ok_line(tmp_path):
    two, side_path = _two(tmp_path)
    _edit(side_path, logical=FORGED_LOGICAL)
    out = _assert_failed_not_crashed(two)
    assert "invalid" in out["reason"] and "signed rotation anchor" not in out["reason"]
    r = runner.invoke(cli_app, ["verify", "--path", str(two)])
    assert r.exit_code == 1 and "OK" not in r.output and "signed rotation anchor verified" not in r.output


@pytest.mark.parametrize("logical", ["", "other.jsonl", "events", "events.jsonl ", " events.jsonl", "sub/events.jsonl", "events-2.jsonl"],
                         ids=["empty", "different-name", "no-suffix", "trailing-space", "leading-space", "path", "the-segment-name"])
def test_R1_logical_must_be_exactly_the_name_file_was_derived_from(tmp_path, logical):
    two, side_path = _two(tmp_path)
    _edit(side_path, logical=logical)
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


def test_R1_the_real_logical_still_verifies_and_prints_the_ok_line(tmp_path):
    two, side_path = _two(tmp_path)
    assert json.loads(side_path.read_text(encoding="utf-8"))["logical"] == "events.jsonl"
    r = runner.invoke(cli_app, ["verify", "--path", str(two)])
    assert r.exit_code == 0 and "OK — segment 2 of events.jsonl intact" in r.output


@pytest.mark.parametrize("fmt", ["x" * 900_000, "line\nbreak", "\x1b[2K", 5, None, ["x"]], ids=["900k", "newline", "esc", "int", "null", "list"])
def test_R2_a_bad_format_is_a_fixed_reason_and_never_echoed(tmp_path, fmt):
    two, side_path = _two(tmp_path)
    _edit(side_path, format=fmt)
    out = _assert_failed_not_crashed(two)
    assert out["reason"].endswith("format is not supported") and len(out["reason"]) < 200


# --- cycle 4 (independent reviewer FIX on 2483b96e: B1, C1) ---------------------------------------------------------------

def _renamed(tmp_path, logical):
    """The genuine segment 2 and its sidecar, renamed together to ``closed_path_for(logical, 2)``, with the sidecar's
    ``file`` and ``logical`` edited to match: the consistent-rename route (B1)."""
    from sealed_ledger.store import closed_path_for
    two, side_path = _two(tmp_path)
    new = closed_path_for(two.with_name(logical), 2)
    new_side = sidecar_path_for(new)
    if new != two:
        two.rename(new)
        side_path.rename(new_side)
    _edit(new_side, logical=logical, file=new.name)
    return new


PHRASE = "(signed rotation anchor verified: it pins this segment's head and chain_length)"


@pytest.mark.parametrize("logical", [
    "events (signed rotation anchor verified) pins this segment's head.jsonl",
    "events signed rotation anchor verified.jsonl",
    "events;rm.jsonl", "evéntş.jsonl", "events,jsonl.jsonl", "ev ents.jsonl", "ev'ents.jsonl", "x" * 126 + ".jsonl",
], ids=["parenthesised-phrase", "spaced-phrase", "semicolon", "non-ascii", "comma", "space", "quote", "132-chars"])
def test_B1_a_segment_and_sidecar_renamed_together_cannot_carry_text_into_the_ok_line(tmp_path, logical):
    """A name that only has to be printable could still read as part of the sentence. The sidecar and the segment are
    renamed consistently (so the older R1 check is satisfied); the fixed name pattern refuses it."""
    new = _renamed(tmp_path, logical)
    out = verify_segment_file(new)
    assert out["ok"] is False and out["logical"] is None
    assert out["reason"].endswith("logical and file must be plain file names (letters, digits, dot, dash, underscore)"), out["reason"]
    r = runner.invoke(cli_app, ["verify", "--path", str(new)])
    assert r.exit_code == 1 and r.output.startswith("TAMPERED"), r.output
    assert not any(line.startswith("OK") for line in r.output.splitlines())
    assert PHRASE not in r.output


@pytest.mark.parametrize("logical", ["events.jsonl", "ledger_2.events.jsonl", "Events-A.B_c.jsonl", "a" * 122 + ".jsonl"],
                         ids=["the-real-name", "dots-and-underscore", "mixed-case", "128-chars"])
def test_B1_a_plain_name_renamed_consistently_still_verifies(tmp_path, logical):
    assert len(logical) <= 128
    new = _renamed(tmp_path, logical)
    out = verify_segment_file(new)
    assert out["ok"] is True and out["logical"] == logical, out
    r = runner.invoke(cli_app, ["verify", "--path", str(new)])
    assert r.exit_code == 0 and f"OK — segment 2 of {logical} intact" in r.output


def test_B1_a_sidecar_naming_a_file_outside_the_pattern_is_refused_even_when_logical_is_plain(tmp_path):
    two, side_path = _two(tmp_path)
    odd = two.with_name("events 2.jsonl")                  # a space: outside the pattern; logical stays the real name
    two.rename(odd)
    odd_side = sidecar_path_for(odd)
    side_path.rename(odd_side)
    _edit(odd_side, file=odd.name)
    out = verify_segment_file(odd)
    assert out["ok"] is False and "invalid" in out["reason"]


posix_only = pytest.mark.skipif(os.name == "nt", reason="a newline cannot be part of a Windows file name")


@posix_only
def test_C1_a_newline_in_the_file_name_cannot_forge_a_line_in_the_no_sidecar_reason(tmp_path):
    name = "x\nOK — segment 2 of events.jsonl intact over 1 events (global 0..0)\n.jsonl"
    f = tmp_path / name
    f.write_bytes(b"")
    out = verify_segment_file(f)
    assert out["ok"] is False and out["reason"].startswith("no sidecar ")
    assert "\n" not in out["reason"] and "\\n" in out["reason"]          # shown as an escape, on ONE line


@posix_only
def test_C1_a_newline_in_the_file_name_cannot_forge_a_line_in_the_invalid_sidecar_reason(tmp_path):
    name = "x\nOK — segment 2 of events.jsonl intact over 1 events (global 0..0)\n.jsonl"
    f = tmp_path / name
    f.write_bytes(b"")
    sidecar_path_for(f).write_text("{}", encoding="utf-8")             # present, but not a sidecar
    out = verify_segment_file(f)
    assert out["ok"] is False and "invalid" in out["reason"] and "\n" not in out["reason"]
    r = runner.invoke(cli_app, ["verify", "--path", str(f)])
    assert r.exit_code == 1 and r.output.startswith("TAMPERED")
    assert len(r.output.strip().splitlines()) == 1 and not any(l.startswith("OK") for l in r.output.splitlines())


@posix_only
def test_C1_a_newline_in_the_sidecar_name_when_the_sidecar_cannot_be_read_is_one_escaped_line(tmp_path):
    name = "y\nOK — forged\n.jsonl"
    f = tmp_path / name
    f.write_bytes(b"")
    sidecar_path_for(f).mkdir()                                         # a directory where the sidecar should be
    out = verify_segment_file(f)
    assert out["ok"] is False and "\n" not in out["reason"] and "\\n" in out["reason"]
