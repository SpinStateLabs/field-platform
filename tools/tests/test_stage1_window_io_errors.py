"""B-S11-29: stage1_window fails with one fixed line and exit 2 when its output cannot be written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0]))

import stage1_window as sw  # noqa: E402

SERVICES = [label for label, _p, _s in sw.OPERATOR_BLOCK_SERVICES]
U, R = sw.sc.COUNTER_KEYS


def snap(t):
    return {"taken_at": t, "counters": {s: {U: 0, R: 0} for s in SERVICES}}


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_evaluate_with_an_unwritable_records_path_exits_2_and_never_claims_a_record(tmp_path, capsys):
    b, a = write(tmp_path, "b.json", snap(0)), write(tmp_path, "a.json", snap(30 * 3600))
    records_dir = tmp_path / "records-is-a-directory"
    records_dir.mkdir()
    code = sw.main(["evaluate", "--before", b, "--after", a, "--records", str(records_dir)])
    out = capsys.readouterr().out
    assert code == 2, out
    assert "recorded gate" not in out and "[PASS]" not in out and "Traceback" not in out
    assert "cannot write" in out and str(records_dir) not in out


def test_snapshot_with_an_unwritable_out_path_exits_2_without_a_traceback(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sw, "read_snapshot", lambda estate, now=None: snap(1))
    blocker = tmp_path / "a-regular-file"
    blocker.write_text("x", encoding="utf-8")
    code = sw.main(["snapshot", "--base", "http://127.0.0.1:1", "--out", str(blocker / "snap.json")])
    out = capsys.readouterr().out
    assert code == 2, out
    assert "cannot write" in out and "written;" not in out and "Traceback" not in out
