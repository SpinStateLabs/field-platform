"""S9-27: a damaged or unwritable records file is a named refusal (exit 2, one ``refused: <token>`` line, nothing run),
never a traceback, and never an EMPTY reading (an empty reading would lose alerts_proven and stage_done history and
hide an unacknowledged rollback).

Read faults: an undecodable file or a directory is ``records_unreadable``. Write faults: a failing append is
``records_unwritable`` on the ``record`` verbs and on a dry-run ``plan``; a failing append of a ``refused`` row never
replaces the ``Refused``. STAGES and the live-run path are untouched. Every value is made up."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("stage_controller_faults", ROOT / "tools" / "stage_controller.py")
sc = importlib.util.module_from_spec(_spec)
sys.modules["stage_controller_faults"] = sc
_spec.loader.exec_module(sc)

MARK = "MARKER-3f7a"


def cli(capsys, *argv):
    rc = sc.main(list(argv))
    out = capsys.readouterr()
    assert "Traceback" not in out.out + out.err
    return rc, out.out


def proven(path: Path) -> Path:
    path.write_text(json.dumps({"ts": "2026-11-07T00:00:00Z", "kind": "alerts_proven", "ok": True}) + "\n",
                    encoding="utf-8")
    return path


# -- reads -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("content", [b"\xff\xfe\x00bad", b'{"kind": "alerts_proven", "ok": true}\n\xff\n',
                                     b"\xc3\x28"], ids=["bytes", "good-row-then-bad-byte", "truncated-utf8"])
def test_an_undecodable_records_file_is_records_unreadable_not_empty(tmp_path, capsys, content):
    path = tmp_path / "records.jsonl"
    path.write_bytes(content)
    with pytest.raises(sc.Refused) as exc:
        sc.Records(path).rows()
    assert exc.value.reason == "records_unreadable"
    rc, out = cli(capsys, "plan", "--stage", "1", "--records", str(path))
    assert rc == 2 and out.strip() == "refused: records_unreadable"


def test_a_directory_as_the_records_path_is_records_unreadable(tmp_path, capsys):
    rc, out = cli(capsys, "plan", "--stage", "1", "--records", str(tmp_path))
    assert rc == 2 and out.strip() == "refused: records_unreadable"
    assert str(tmp_path) not in out


def test_the_refusal_never_carries_the_path_or_the_bytes(tmp_path):
    path = tmp_path / f"{MARK}.jsonl"
    path.write_bytes(MARK.encode() + b"\xff")
    with pytest.raises(sc.Refused) as exc:
        sc.Records(path).rows()
    assert MARK not in str(exc.value) and exc.value.__cause__ is None and exc.value.__suppress_context__


def test_a_missing_file_is_still_empty_and_a_damaged_line_is_still_skipped(tmp_path):
    assert sc.Records(tmp_path / "absent.jsonl").rows() == []
    path = tmp_path / "records.jsonl"
    path.write_text('not json\n{"kind": "alerts_proven", "ok": true}\n', encoding="utf-8")
    assert [r["kind"] for r in sc.Records(path).rows()] == ["alerts_proven"]


def test_a_missing_file_plan_is_still_alerts_not_proven(tmp_path, capsys):
    rc, out = cli(capsys, "plan", "--stage", "1", "--records", str(tmp_path / "absent.jsonl"))
    assert rc == 2 and out.strip() == "refused: alerts_not_proven"


# -- writes ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("argv", [["record", "alerts-proven"], ["record", "ack-rollback", "--stage", "1"],
                                  ["record", "gate", "G21"]], ids=["alerts-proven", "ack-rollback", "gate"])
def test_a_directory_as_the_records_path_makes_every_record_verb_a_named_refusal(tmp_path, capsys, argv):
    rc, out = cli(capsys, *argv, "--records", str(tmp_path))
    assert rc == 2 and out.strip() == "refused: records_unwritable"
    assert "recorded" not in out


@pytest.mark.parametrize("argv", [["record", "alerts-proven"], ["record", "ack-rollback", "--stage", "1"],
                                  ["record", "gate", "G21"]], ids=["alerts-proven", "ack-rollback", "gate"])
def test_a_failing_append_on_a_record_verb_is_a_named_refusal(tmp_path, capsys, monkeypatch, argv):
    def boom(self, kind, **fields):
        raise PermissionError(MARK)

    monkeypatch.setattr(sc.Records, "append", boom)
    rc, out = cli(capsys, *argv, "--records", str(tmp_path / "records.jsonl"))
    assert rc == 2 and out.strip() == "refused: records_unwritable" and MARK not in out


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="a read-only file is writable by root and by Windows ACL rules here")
@pytest.mark.parametrize("argv", [["record", "alerts-proven"], ["record", "ack-rollback", "--stage", "1"]])
def test_a_read_only_records_file_is_a_named_refusal(tmp_path, capsys, argv):
    path = proven(tmp_path / "records.jsonl")
    path.chmod(0o400)
    rc, out = cli(capsys, *argv, "--records", str(path))
    assert rc == 2 and out.strip() == "refused: records_unwritable"


def test_a_dry_run_plan_that_cannot_record_is_a_named_refusal(tmp_path, capsys, monkeypatch):
    path = proven(tmp_path / "records.jsonl")
    real = sc.Records.append

    def append(self, kind, **fields):
        if kind == "plan":
            raise PermissionError(MARK)
        return real(self, kind, **fields)

    monkeypatch.setattr(sc.Records, "append", append)
    rc, out = cli(capsys, "plan", "--stage", "1", "--records", str(path))
    assert rc == 2 and out.strip() == "refused: records_unwritable" and "may start" not in out


def test_a_failing_refused_row_never_replaces_the_refusal(tmp_path, monkeypatch):
    def boom(self, kind, **fields):
        raise OSError(MARK)

    monkeypatch.setattr(sc.Records, "append", boom)
    with pytest.raises(sc.Refused) as exc:
        sc.Controller(sc.Records(tmp_path / "records.jsonl")).run(99)
    assert exc.value.reason == "unknown_stage"


def test_the_happy_path_is_unchanged(tmp_path, capsys):
    path = tmp_path / "records.jsonl"
    assert cli(capsys, "record", "alerts-proven", "--records", str(path))[0] == 0
    rc, out = cli(capsys, "plan", "--stage", "1", "--records", str(path))
    assert rc == 0 and "stage 1 may start (dry run" in out
    kinds = [r["kind"] for r in sc.Records(path).rows()]
    assert kinds == ["alerts_proven", "plan"]
