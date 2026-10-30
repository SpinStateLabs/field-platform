"""C-192 (reviewer C-186 F-C186-1, D-26): `ledger verify --anchors` fails closed.

`load_anchors` answered [] for an absent file and `verify_anchors` returned `ok=True anchors_checked=0`, so
`ledger verify --path L --anchors TYPO` printed "OK - 0 anchor(s) hold" and exited 0: a typo'd path was a pass.
With `--anchors` given, a missing file, an unreadable file, an unparseable file or a file holding zero records is
now a failure (exit 1, a message naming the file); without `--anchors` nothing changes."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from sealed_ledger.anchors import verify_anchors, write_anchor
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

runner = CliRunner()


def ledger(tmp_path, n=3):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    for i in range(n):
        s.append(f"test.event.{i}", {"i": i})
    return s, p


def verify_cli(p, *extra):
    return runner.invoke(cli_app, ["verify", "--path", str(p), *extra])


# --- the library ---------------------------------------------------------------------------------------


def test_a_nonexistent_anchors_file_is_a_failure(tmp_path):
    s, _ = ledger(tmp_path)
    r = verify_anchors(s, tmp_path / "TYPO.jsonl")
    assert r.ok is False and r.anchors_checked == 0
    assert "TYPO.jsonl" in r.first_failure and "does not exist" in r.first_failure


@pytest.mark.parametrize("content", ["", "\n", "   \n\t\n", "\n\n\n"])
def test_an_empty_or_blank_anchors_file_is_a_failure(tmp_path, content):
    s, _ = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    f.write_text(content, encoding="utf-8")
    r = verify_anchors(s, f)
    assert r.ok is False and r.anchors_checked == 0
    assert "no anchor records" in r.first_failure and "anchors.jsonl" in r.first_failure


def test_an_anchors_path_that_is_a_directory_is_an_unreadable_failure(tmp_path):
    s, _ = ledger(tmp_path)
    d = tmp_path / "anchors-dir"
    d.mkdir()
    r = verify_anchors(s, d)
    assert r.ok is False and "cannot be read" in r.first_failure


NL = bytes([10])
UNPARSEABLE = [b"not json" + NL, b'{"chain_length": "x"}' + NL, b"{" + NL,
               bytes([0xFF, 0xFE, 0x00]) + b"bad" + NL]


@pytest.mark.parametrize("content", UNPARSEABLE)
def test_an_unparseable_anchors_file_is_a_failure_not_a_crash(tmp_path, content):
    s, _ = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    f.write_bytes(content)
    r = verify_anchors(s, f)
    assert r.ok is False and r.anchors_checked == 0 and "not a readable anchor file" in r.first_failure


def test_a_real_anchors_file_still_verifies(tmp_path):
    s, _ = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    write_anchor(s, f)
    r = verify_anchors(s, f)
    assert r.ok and r.anchors_checked == 1


def test_a_real_file_with_blank_lines_around_the_record_still_verifies(tmp_path):
    s, _ = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    write_anchor(s, f)
    f.write_text("\n" + f.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    assert verify_anchors(s, f).ok


def test_a_rewritten_history_still_fails_with_its_own_message(tmp_path):
    s, _ = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    rec = json.loads(write_anchor(s, f).model_dump_json())
    rec["head_hash"] = "0" * 64
    f.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    r = verify_anchors(s, f)
    assert r.ok is False and "REWRITTEN" in r.first_failure


# --- the command ---------------------------------------------------------------------------------------


def test_the_cli_fails_on_a_typo_d_anchors_path(tmp_path):
    _, p = ledger(tmp_path)
    r = verify_cli(p, "--anchors", str(tmp_path / "TYPO.jsonl"))
    assert r.exit_code == 1, r.output
    assert "ANCHOR FAILURE" in r.output and "TYPO.jsonl" in r.output
    assert "anchor(s) hold" not in r.output


def test_the_cli_fails_on_an_empty_anchors_file(tmp_path):
    _, p = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    f.write_text("", encoding="utf-8")
    r = verify_cli(p, "--anchors", str(f))
    assert r.exit_code == 1, r.output
    assert "ANCHOR FAILURE" in r.output and "no anchor records" in r.output


def test_the_cli_fails_on_an_unreadable_anchors_path(tmp_path):
    _, p = ledger(tmp_path)
    d = tmp_path / "anchors-dir"
    d.mkdir()
    r = verify_cli(p, "--anchors", str(d))
    assert r.exit_code == 1, r.output
    assert "ANCHOR FAILURE" in r.output


def test_the_cli_still_passes_with_a_real_anchors_file(tmp_path):
    s, p = ledger(tmp_path)
    f = tmp_path / "anchors.jsonl"
    write_anchor(s, f)
    r = verify_cli(p, "--anchors", str(f))
    assert r.exit_code == 0, r.output
    assert "1 anchor(s) hold" in r.output


def test_without_anchors_nothing_changes(tmp_path):
    _, p = ledger(tmp_path)
    r = verify_cli(p)
    assert r.exit_code == 0, r.output
    assert "ANCHOR" not in r.output and "anchor(s) hold" not in r.output


def test_a_bad_anchors_path_does_not_hide_a_tampered_chain(tmp_path):
    """The chain verdict is printed and exits first; the anchors check is never a way to turn a failure green."""
    _, p = ledger(tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("test.event.1", "test.event.X")
    p.write_text(NL.decode().join(lines) + NL.decode(), encoding="utf-8")
    r = verify_cli(p, "--anchors", str(tmp_path / "TYPO.jsonl"))
    assert r.exit_code == 1 and "TAMPERED" in r.output
