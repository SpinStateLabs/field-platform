"""S11-1: an event whose text cannot be UTF-8 encoded (a lone surrogate such as U+D800) is a REPORTED break from
verify_chain, not a UnicodeEncodeError traceback.

`json.loads` and a pydantic `str` accept '\\ud800'; `_canonical_bytes` then fails to encode it. A hash for such text
never existed, so nothing stored changes: `compute_event_hash` keeps raising (a typed ValueError for writers), and
`verify_chain` reports the index with a fixed text that never echoes the value. No `surrogatepass`: that would define
a new hash form.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from field_core.cli import app
from field_core.ledger import GENESIS_HASH, LedgerEvent, compute_event_hash, make_event, verify_chain

LONE = "\ud800"
FIXED = "hash cannot be recomputed at index {i} (text that cannot be encoded)"
runner = CliRunner()


def _bad_event(prev_hash: str, **fields) -> LedgerEvent:
    record = {"event_id": "e-bad", "ts": "2026-11-08T00:00:00+00:00", "event_type": "t", "agent_id": None,
              "payload": {"note": "a" + LONE}, "prev_hash": prev_hash, **fields}
    return LedgerEvent(**record, hash="0" * 64)


def test_compute_event_hash_still_raises_a_typed_value_error():
    with pytest.raises(ValueError):
        compute_event_hash({"event_id": "x", "payload": {"k": LONE}})


def test_verify_chain_reports_the_unencodable_event_as_a_break():
    good = make_event("ok")
    bad = _bad_event(good.hash)
    result = verify_chain([good, bad])
    assert result.ok is False
    assert result.first_break_index == 1 and result.length == 2
    assert result.reason == FIXED.format(i=1)


def test_the_reason_never_echoes_the_value():
    result = verify_chain([_bad_event(GENESIS_HASH, payload={"secretish": "SECRETISH" + LONE})])
    assert "SECRETISH" not in result.reason and "secretish" not in result.reason and LONE not in result.reason


def test_a_lone_surrogate_in_an_id_is_reported_too():
    result = verify_chain([_bad_event(GENESIS_HASH, event_id="id" + LONE)])
    assert result.ok is False and result.first_break_index == 0 and result.reason == FIXED.format(i=0)


def test_a_link_break_is_still_reported_first():
    """The prev_hash check runs before the recompute: its (existing) reason wins when both are wrong."""
    result = verify_chain([_bad_event("f" * 64)])
    assert result.ok is False and result.reason.startswith("link break at index 0")


def test_an_intact_chain_is_unchanged():
    a = make_event("a")
    b = make_event("b", prev_hash=a.hash)
    result = verify_chain([a, b])
    assert result.ok is True and result.length == 2 and result.reason is None


def test_the_cli_exits_1_tampered_with_no_traceback(tmp_path: Path):
    good = make_event("ok")
    bad = {"event_id": "e-bad", "ts": "2026-11-08T00:00:00+00:00", "event_type": "t", "agent_id": None,
           "payload": {"note": "a" + LONE}, "prev_hash": good.hash, "hash": "0" * 64}
    f = tmp_path / "chain.jsonl"
    f.write_text(good.model_dump_json() + "\n" + json.dumps(bad, ensure_ascii=True) + "\n", encoding="utf-8")
    assert "\\ud800" in f.read_text(encoding="utf-8")        # the escape, not the character, is on disk
    r = runner.invoke(app, ["verify-chain", str(f)])
    assert r.exit_code == 1, r.output
    assert "TAMPERED" in r.output
    assert "Traceback" not in r.output and not isinstance(r.exception, UnicodeEncodeError)
