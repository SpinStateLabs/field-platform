"""The rollback read check also covers event types whose payload shape changes. Synthetic fixtures only."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import rollback_read_check as rrc  # noqa: E402


def test_a_listed_changed_shape_is_exercised_even_when_no_type_is_added(monkeypatch):
    monkeypatch.setattr(rrc, "CHANGED", {"made.up_changed": ("a", {"new_key": 1})})
    assert rrc.select(set()) == ([], [], ["made.up_changed"])
    assert rrc.fixture("made.up_changed") == ("a", {"new_key": 1})


def test_added_types_still_need_a_fixture_and_a_changed_one_wins(monkeypatch):
    monkeypatch.setattr(rrc, "CHANGED", {"lifecycle.tick_failed": (None, {"error_class": "x"})})
    covered, uncovered, changed = rrc.select({"lifecycle.tick_failed", "kill.drill.refused", "made.up_new"})
    assert covered == ["kill.drill.refused", "lifecycle.tick_failed"] and uncovered == ["made.up_new"] and changed == []
    assert rrc.fixture("lifecycle.tick_failed") == (None, {"error_class": "x"})


def test_a_reader_that_requires_a_dropped_key_fails():
    assert rrc._cell(lambda: {"new_key": 1}["old_key"]) == {"status": "CRASH", "detail": "KeyError"}


def test_the_readers_run_on_this_tree_and_hand_back_the_shown_lines(tmp_path):
    types = ["kill.drill.refused", "lifecycle.tick_failed"]
    write, read = tmp_path / "write", tmp_path / "read"
    write.mkdir()
    done = rrc.child(sys.executable, "write", REPO, write, types)
    assert done.returncode == 0, done.stderr[-2000:]
    (read / rrc.LEDGER_REL.parent).mkdir(parents=True)
    (read / rrc.LEDGER_REL).write_bytes((write / rrc.LEDGER_REL).read_bytes())
    done = rrc.child(sys.executable, "read", REPO, read, types)
    assert done.returncode == 0, done.stderr[-2000:]
    report = json.loads((read / "result.json").read_text(encoding="utf-8"))
    for event_type in types:
        cells = report["types"][event_type]
        assert set(cells) == set(rrc.READERS)
        assert {c["status"] for c in cells.values()} <= {"OK", "SKIPPED"}, cells
        for reader in ("ops_console", "attest", "ops_overview"):
            assert cells[reader]["detail"], (event_type, reader)
    for name in ("attestation_pack", "lifecycle_sweep", "ops_ledger_sections"):
        assert report["whole"][name]["status"] == "OK", (name, report["whole"][name])


def test_the_shown_lines_are_printed(capsys):
    cells = {r: {"status": "OK"} for r in rrc.READERS}
    cells["replay"] = {"status": "OK", "detail": "made up line 123"}
    assert rrc.summarise({"types": {"made.up_changed": cells}, "whole": {}}, ["made.up_changed"], [], None, "a", "b") == 0
    assert "made.up_changed / replay: made up line 123" in capsys.readouterr().out
