"""S12-18: an UNSIGNED sidecar is the file the verifier is meant not to trust, so a bad one is a failed verification
({ok: False, reason} / `ledger verify` exit 1 TAMPERED), never a traceback.

Two inputs used to escape: Infinity / 1e999 (json.loads gives float inf; int(inf) is OverflowError, not in the except
tuple) and an empty-segment claim (end_index = start_index - 1 beside a zero-byte file passed the count check, then
events[-1] raised IndexError).
The journal-entry siblings (_closed_bytes_problem, verify_closed_segment) need no guard: parse_journal already refuses
end_index < start_index (store.py:821), so an empty-segment claim cannot reach them."""

from __future__ import annotations

import json

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
    assert "invalid" in _assert_failed_not_crashed(two)["reason"]


@pytest.mark.parametrize("key", ["anchor", "logical"])
def test_C1_deep_nesting_inside_a_field_is_a_failed_verification(tmp_path, key):
    two, side_path = _two(tmp_path)
    deep = "[" * 100_000 + "]" * 100_000
    text = side_path.read_text(encoding="utf-8").rstrip()
    assert text.endswith("}")
    side_path.write_text(text[:-1] + f', "{key}": {deep}' + "}", encoding="utf-8")   # a duplicate key: the last value wins
    _assert_failed_not_crashed(two)


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
