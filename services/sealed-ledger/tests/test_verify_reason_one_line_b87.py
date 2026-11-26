"""B87: a verification reason is printed as ONE line, whatever the file under test contains.

Before: segment content reached a ``TAMPERED`` line unescaped. A line with an extra key put pydantic's multi-line
ValidationError text, key and all, on the screen, so a key holding a newline and the words of the success line put those
words on a line of their own (exit 1, unsigned mode); ``verify_chain`` echoed twelve raw characters of ``prev_hash`` and
``hash``. Now every ``TAMPERED`` / ``ANCHOR FAILURE`` / ``EXPORT FAILED`` reason goes through ``_one_line`` (control,
format and line-separator characters written as visible escapes, a length cap), and a line that does not parse is named
by its exception class and a fixed text, never by the message. Exit codes and the OK line are unchanged.

Every input here is file CONTENT, not a file name, so none of these tests needs a POSIX-only file system."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from sealed_ledger import store as store_mod
from sealed_ledger.cli import REASON_MAX_CHARS, _one_line, app as cli_app
from sealed_ledger.store import _closed_bytes_problem, verify_segment_file
from test_ledger_c2_hardening import _archived_ledger

runner = CliRunner()

PHRASE = "(signed rotation anchor verified: it pins this segment's head and chain_length)"
ESC = chr(27)


def _two(tmp_path):
    data, _s, _p, _hashes = _archived_ledger(tmp_path)
    return data / "ledger-archive" / "events-2.jsonl"


def _rewrite_first_line(path, change):
    lines = path.read_text(encoding="utf-8").split("\n")
    event = json.loads(lines[0])
    change(event)
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines), encoding="utf-8")


def _verify(path, *extra):
    r = runner.invoke(cli_app, ["verify", "--path", str(path), *extra])
    assert r.exception is None or isinstance(r.exception, SystemExit), r.exception
    return r


def _assert_one_tampered_line(r, forbidden=()):
    out = r.stdout
    lines = out.splitlines()
    assert r.exit_code == 1, (r.exit_code, out)
    assert len(lines) == 1 and lines[0].startswith("TAMPERED"), lines
    assert ESC not in out and "\r" not in out
    for text in forbidden:
        assert text not in out, (text, out)
    assert not any(line.startswith("OK") or line.startswith("(") for line in lines)


# ---- the reviewer's input: an extra key whose NAME holds a newline and the success-line words ----------------------

def test_an_extra_key_with_a_newline_and_the_success_words_is_one_tampered_line(tmp_path):
    two = _two(tmp_path)
    key = "x\n" + PHRASE + "\ny"
    _rewrite_first_line(two, lambda e: e.update({key: 1}))
    assert PHRASE in two.read_text(encoding="utf-8")          # the forged words are really in the file
    r = _verify(two)
    _assert_one_tampered_line(r, forbidden=(PHRASE, "Extra inputs", "validation error", "extra_forbidden"))
    assert r.stdout.startswith("TAMPERED — segment 2: unparseable line: ValidationError (the message is not echoed)")


def test_the_same_input_through_the_sidecar_reason_function(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: e.update({"x\n" + PHRASE + "\ny": 1}))
    out = verify_segment_file(two)
    assert out["ok"] is False and "\n" not in out["reason"] and PHRASE not in out["reason"]
    assert out["reason"] == "segment 2: unparseable line: ValidationError (the message is not echoed)"


def test_the_same_input_through_the_genesis_route(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: e.update({"x\n" + PHRASE + "\ny": 1}))
    r = _verify(two, "--genesis", "0" * 64)
    _assert_one_tampered_line(r, forbidden=(PHRASE, "Extra inputs"))
    assert r.stdout.startswith("TAMPERED — unparseable line: ValidationError (the message is not echoed)")


def test_the_closed_segment_check_names_the_class_not_the_pydantic_text():
    bad = json.dumps({"x\n" + PHRASE + "\ny": 1}).encode("utf-8")
    problem = _closed_bytes_problem(bad, {"start_index": 0, "end_index": 0}, "0" * 64, None)
    assert problem is not None
    index, reason = problem
    assert index == 0 and reason == "unparseable line: ValidationError (the message is not echoed)"


def test_a_line_that_is_not_json_is_named_by_its_class_too(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: None)
    two.write_text("{not json\n" + two.read_text(encoding="utf-8"), encoding="utf-8")
    r = _verify(two)
    _assert_one_tampered_line(r)
    assert "JSONDecodeError (the message is not echoed)" in r.stdout


# ---- verify_chain echoes twelve characters of prev_hash / hash -------------------------------------------------------

def test_a_raw_newline_in_prev_hash_is_one_escaped_line(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: e.update(prev_hash="ab\n(signed r" + "0" * 60))
    r = _verify(two)
    _assert_one_tampered_line(r)
    assert "link break at index " in r.stdout and "ab\\n(signed r" in r.stdout        # the escape, two characters


def test_a_raw_newline_and_cr_in_hash_is_one_escaped_line(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: e.update(hash="x\r\n(signed rot" + "0" * 50))
    r = _verify(two)
    _assert_one_tampered_line(r)
    assert "hash mismatch at index " in r.stdout and "x\\r\\n(signed" in r.stdout


def test_ansi_escapes_in_a_hash_field_are_visible_escapes_not_a_repaint(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: e.update(hash=ESC + "[2J" + ESC + "[31mred"))
    r = _verify(two)
    _assert_one_tampered_line(r)
    assert "\\x1b[2J" in r.stdout and "\\x1b[31m" in r.stdout


def test_a_lone_surrogate_in_a_hash_field_is_an_escape_not_an_encode_error(tmp_path):
    two = _two(tmp_path)
    _rewrite_first_line(two, lambda e: e.update(prev_hash="\ud800" + "0" * 63))
    r = _verify(two)
    _assert_one_tampered_line(r)
    assert "\\ud800" in r.stdout


# ---- a line nested past the recursion limit is a failed verification, not a traceback --------------------------------

def test_a_deeply_nested_segment_line_is_a_tampered_reason_not_a_traceback(tmp_path):
    two = _two(tmp_path)
    two.write_bytes(b"[" * 200000 + b"]" * 200000 + b"\n")
    r = _verify(two)
    _assert_one_tampered_line(r)
    assert "unparseable line: nesting is deeper than 500 levels" in r.stdout


def test_a_deeply_nested_line_on_the_genesis_route_is_tampered_too(tmp_path):
    two = _two(tmp_path)
    two.write_bytes(b"[" * 200000 + b"]" * 200000 + b"\n")
    r = _verify(two, "--genesis", "0" * 64)
    _assert_one_tampered_line(r)
    assert "nesting is deeper than 500 levels" in r.stdout


# ---- the escape function itself -----------------------------------------------------------------------------------

def test_ordinary_reasons_are_unchanged():
    reason = "segment 2: hash mismatch at index 3: stored abcdef012345… != recomputed 0123456789ab… (record was mutated)"
    assert _one_line(reason) == reason
    assert _one_line("sidecar 'events-2.jsonl.segment.json' invalid: end_index is out of range") == \
        "sidecar 'events-2.jsonl.segment.json' invalid: end_index is out of range"


@pytest.mark.parametrize("text, expected", [
    ("a\nb", "a\\nb"),
    ("a\rb", "a\\rb"),
    ("a\tb", "a\\tb"),
    ("a" + ESC + "[0m", "a\\x1b[0m"),
    ("a\x00b", "a\\x00b"),
    ("a\x7fb", "a\\x7fb"),
    ("a\x85b", "a\\x85b"),
    ("a b", "a\\u2028b"),
    ("a b", "a\\u2029b"),
    ("a‮b", "a\\u202eb"),
    ("a​b", "a\\u200bb"),
    ("a\ud800b", "a\\ud800b"),
    ("a\U000e0001b", "a\\U000e0001b"),
])
def test_control_format_and_separator_characters_become_visible_escapes(text, expected):
    out = _one_line(text)
    assert out == expected
    assert out.isprintable() and len(out.splitlines()) == 1


def test_a_very_long_reason_is_cut_and_says_how_much():
    out = _one_line("x" * (REASON_MAX_CHARS + 1234))
    assert out.startswith("x" * REASON_MAX_CHARS) and out.endswith("(1234 more characters not shown)")
    assert len(out) < REASON_MAX_CHARS + 60
    # a reason of control characters is cut AFTER escaping, so the visible line is what is bounded
    out2 = _one_line("\n" * 10000)
    assert len(out2.splitlines()) == 1 and out2.endswith("more characters not shown)")


def test_a_very_long_reason_through_the_cli_is_one_bounded_line(tmp_path, monkeypatch):
    two = _two(tmp_path)
    monkeypatch.setattr(store_mod, "verify_segment_file", lambda *a, **k: {"ok": False, "reason": "x\n(OK)\r" * 5000})
    r = _verify(two)
    assert r.exit_code == 1 and len(r.stdout.splitlines()) == 1
    assert r.stdout.startswith("TAMPERED — x\\n(OK)\\rx\\n") and len(r.stdout) < REASON_MAX_CHARS + 100


def test_a_valid_segment_still_prints_the_unchanged_ok_lines(tmp_path):
    two = _two(tmp_path)
    r = _verify(two)
    assert r.exit_code == 0
    lines = r.stdout.splitlines()
    assert lines[0].startswith("OK — segment 2 of events.jsonl intact over ") and len(lines) == 2
    assert lines[1] == "(sidecar claims are unsigned; pass --pubkey to check the signed rotation anchor)"
