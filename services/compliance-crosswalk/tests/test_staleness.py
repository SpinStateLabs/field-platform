"""staleness tests — reg-version stale flags stay honest (ADR 07 §3/§4)."""

import time

import pytest

from compliance_crosswalk.mapping import CONTROLS
from compliance_crosswalk.staleness import (
    CORPUS_VERSION,
    StaleStore,
    affected_controls,
)


def test_mark_returns_flag_and_shows_in_active(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    flag = s.mark("osfi-e23", "guideline revision consultation opened")
    later = s.mark("eu-ai-act", "amendment published", new_version="2026-Q3")
    assert flag["framework"] == "osfi-e23"
    assert flag["reason"] == "guideline revision consultation opened"
    assert flag["new_version"] is None
    assert flag["flagged_at"]
    assert later["new_version"] == "2026-Q3"
    assert s.active() == [later, flag]  # sorted by framework


def test_unknown_framework_raises_valueerror(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    with pytest.raises(ValueError):
        s.mark("sox-404", "not a framework this crosswalk tracks")
    with pytest.raises(ValueError):
        affected_controls("sox-404")


def test_clear_is_named_removes_flag_and_writes_history(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    flag = s.mark("nist-ai-rmf", "RMF 2.0 draft announced")
    with pytest.raises(ValueError):
        s.clear("nist-ai-rmf", "")  # anonymous review is not a review
    assert len(s.active()) == 1  # the refused clear changed nothing
    review = s.clear("nist-ai-rmf", "D. Hagell")
    assert s.active() == []
    assert review["reviewed_by"] == "D. Hagell"
    assert review["cleared_at"]
    assert review["flag"] == flag  # the cleared flag is embedded, not lost
    assert s.status()["history"] == [review]


def test_clear_of_unflagged_framework_raises_keyerror(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    with pytest.raises(KeyError):
        s.clear("osfi-e23", "D. Hagell")


def test_remark_keeps_original_flagged_at(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    first = s.mark("eu-ai-act", "delegated act rumored")
    time.sleep(0.02)
    second = s.mark(
        "eu-ai-act", "delegated act confirmed", new_version="C(2026) 123"
    )
    # The stale window measures from FIRST detection; re-marking must not
    # restart the clock.
    assert second["flagged_at"] == first["flagged_at"]
    assert second["reason"] == "delegated act confirmed"
    assert len(s.active()) == 1


def test_persistence_second_store_sees_first_state(tmp_path):
    path = tmp_path / "flags.json"
    s1 = StaleStore(path)
    s1.mark("osfi-e23", "guideline revision consultation opened")
    s1.mark("eu-ai-act", "amendment published")
    s1.clear("eu-ai-act", "D. Hagell")
    s2 = StaleStore(path)
    assert [f["framework"] for f in s2.active()] == ["osfi-e23"]
    assert [h["framework"] for h in s2.status()["history"]] == ["eu-ai-act"]


def test_status_reports_stale_window_and_corpus_version(tmp_path):
    s = StaleStore(tmp_path / "flags.json")
    s.mark("nist-ai-rmf", "RMF 2.0 draft announced")
    time.sleep(0.02)
    status = s.status()
    assert status["corpus_version"] == CORPUS_VERSION == "corpus-2026-08-08"
    (flag,) = status["active"]
    assert isinstance(flag["stale_window_seconds"], float)
    assert flag["stale_window_seconds"] > 0


def test_affected_controls_covers_cited_entries_only():
    osfi = affected_controls("osfi-e23")
    assert osfi, "osfi-e23 has cited entries; affected set must be non-empty"
    known = {c.control_id for c in CONTROLS}
    assert set(osfi) <= known
    assert osfi == sorted(osfi)
    # ISO/IEC 42001 has zero cited entries (all pending-purchase): a version
    # bump affects no citation, and the honest answer is the empty list.
    assert affected_controls("iso-42001") == []
