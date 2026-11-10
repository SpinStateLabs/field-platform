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
