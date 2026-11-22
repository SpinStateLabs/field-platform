"""S9-1: docs/runbooks/ntfy-alerts.md must not say the Phase G stage controller is missing. tools/stage_controller.py
exists and calls alert_senders.stage_transition and alert_senders.stage_aborted; test_alerts_lows_rt2.py (F3) pins the same
fact in the senders docstring, this pins it in the runbook. Reads files only."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs" / "runbooks" / "ntfy-alerts.md"
CONTROLLER = ROOT / "tools" / "stage_controller.py"


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_the_controller_the_runbook_names_exists_and_calls_both_senders():
    code = CONTROLLER.read_text(encoding="utf-8")
    assert "alert_senders.stage_transition" in code and "alert_senders.stage_aborted" in code


def test_the_runbook_no_longer_says_the_controller_is_missing():
    doc = _runbook()
    assert "not in this repository" not in doc
    assert "no controller in this repository" not in doc
    assert "tools/stage_controller.py" in doc


def test_the_two_classes_are_wired_not_planned():
    doc = _runbook()
    for cls in ("stage_transition", "stage_aborted"):
        row = next(line for line in doc.splitlines() if line.startswith(f"| `{cls}` |"))
        assert "tools/stage_controller.py" in row and "planned" not in row
    wired = doc.split("Also wired on main:")[1].split("Ledger event types")[0]
    assert "`stage_transition`" in wired and "`stage_aborted`" in wired


def test_the_classes_that_still_have_no_caller_stay_listed_as_such():
    doc = _runbook()
    no_caller = re.split(r"The\s+tests are", doc.split("with **no caller on main**:")[1])[0]
    for cls in ("rotation_failed", "rotation_overdue", "rotation_halted"):
        assert f"`{cls}`" in no_caller
    for cls in ("stage_transition", "stage_aborted"):
        assert f"`{cls}`" not in no_caller
    assert re.search(r"rotation_failed.*no caller on main", doc)
