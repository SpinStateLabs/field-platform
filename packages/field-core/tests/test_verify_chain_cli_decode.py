"""`field verify-chain FILE`: a file that is not valid UTF-8 is chain evidence, not a traceback (scout P-10).

Before this change `fh.readlines()` raised UnicodeDecodeError (a ValueError, so neither `except FileNotFoundError`
nor `except OSError` caught it): a traceback and exit 1 with no message. A ledger with a truncated multibyte write or
a binary file passed by mistake now reports `TAMPERED` with the byte offset and exits 1, the same verdict as an
unparseable line. The message names the offset only, never the bytes."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from field_core.cli import app
from field_core.ledger import GENESIS_HASH, make_event

runner = CliRunner()


def _chain_bytes(n: int = 3) -> bytes:
    prev, lines = GENESIS_HASH, []
    for i in range(n):
        e = make_event(f"event-{i}", prev_hash=prev)
        prev = e.hash
        lines.append(e.model_dump_json(exclude_none=True))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _run(path: Path):
    return runner.invoke(app, ["verify-chain", str(path)])


def test_a_valid_chain_then_one_0xff_byte_is_tampered_with_its_offset(tmp_path):
    good = _chain_bytes()
    f = tmp_path / "events.jsonl"
    f.write_bytes(good + b"\xff")
    r = _run(f)
    assert isinstance(r.exception, SystemExit), repr(r.exception)      # no traceback
    assert r.exit_code == 1
    assert f"TAMPERED — file is not valid UTF-8 at byte {len(good)}" in r.output
    assert "nothing verified" not in r.output or "TAMPERED" in r.output


def test_a_truncated_multibyte_character_is_tampered(tmp_path):
    good = _chain_bytes(2)
    f = tmp_path / "events.jsonl"
    f.write_bytes(good + b"\xe2\x82")                                   # the first two bytes of a three-byte euro sign
    r = _run(f)
    assert isinstance(r.exception, SystemExit) and r.exit_code == 1
    assert f"at byte {len(good)}" in r.output


def test_a_binary_file_is_tampered_at_its_first_bad_byte(tmp_path):
    f = tmp_path / "events.jsonl"
    f.write_bytes(b"\x80\x81\x82")
    r = _run(f)
    assert isinstance(r.exception, SystemExit) and r.exit_code == 1
    assert "TAMPERED — file is not valid UTF-8 at byte 0" in r.output


def test_the_message_never_repeats_the_bytes(tmp_path):
    f = tmp_path / "events.jsonl"
    f.write_bytes(_chain_bytes() + b"SECRETxx\xff")
    r = _run(f)
    assert r.exit_code == 1 and "SECRETxx" not in r.output and "\\xff" not in r.output


def test_a_valid_non_ascii_chain_still_verifies(tmp_path):
    prev = GENESIS_HASH
    e = make_event("événement ✓", prev_hash=prev)
    f = tmp_path / "events.jsonl"
    f.write_text(e.model_dump_json(exclude_none=True) + "\n", encoding="utf-8")
    r = _run(f)
    assert r.exit_code == 0 and "OK — chain intact over 1 events" in r.output
