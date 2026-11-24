"""Backlog B5: G18 needs its clean-window evidence, and a gate row counts only when ``ok`` is exactly True.

Before B5, ``stage_controller record gate G18`` wrote a G18 row by hand with no clean-window evidence, and Stage 2's
precondition took it. These tests pin:

* ``record gate G18`` is refused (exit 2, nothing written); the row comes from ``tools/stage1_window.py`` only;
* a G18 row counts only while it carries ``window_hours`` >= 24 (finite), ``window_end`` (positive int) and
  ``services`` == 8, so an evidence-less or doctored-short row leaves Stage 2 refused with ``gate_G18_not_recorded``;
* for G18 and G22, a row whose ``ok`` is not exactly ``True`` ("true", 1, missing, false) never counts;
* ``stage1_window evaluate --records`` writes no row for a clean window shorter than 24 hours, and the row it writes
  for a long one counts.
"""
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import stage1_window as sw  # noqa: E402
import stage_controller as sc  # noqa: E402

GO = "Go for Stage 2."
EVIDENCE = {"window_hours": 30.0, "window_end": 1_790_000_000, "services": 8}


def _ready(tmp_path, *, g18=None, g22_ok=True):
    """Records Stage 2 needs, with the G18 row given by ``g18`` (a dict of row fields, or None for no row)."""
    r = sc.Records(tmp_path / "records.jsonl")
    r.append("alerts_proven", ok=True)
    r.append("gate", gate="G22", ok=g22_ok)
    if g18 is not None:
        r.append("gate", gate="G18", **g18)
    return r


def _refusal(records):
    try:
        sc.preconditions(2, records, GO)
    except sc.Refused as exc:
        return exc.reason
    return None


def test_record_gate_g18_by_hand_is_refused_and_writes_nothing(tmp_path, capsys):
    rec = tmp_path / "r.jsonl"
    assert sc.main(["record", "gate", "G18", "--records", str(rec)]) == 2
    assert "stage1_window.py" in capsys.readouterr().out
    assert not rec.exists()
    assert sc.main(["record", "gate", "G22", "--records", str(rec)]) == 0     # the other gates still record by hand


def test_a_g18_row_with_its_evidence_lets_stage_two_start(tmp_path):
    assert _refusal(_ready(tmp_path, g18={"ok": True, **EVIDENCE})) is None


def test_an_evidence_less_g18_row_does_not_count(tmp_path):
    # the exact row the old ``record gate G18`` wrote
    assert _refusal(_ready(tmp_path, g18={"ok": True})) == "gate_G18_not_recorded"


@pytest.mark.parametrize("field,bad", [
    ("window_hours", None), ("window_hours", 23.99), ("window_hours", "30"), ("window_hours", True),
    ("window_hours", math.nan), ("window_hours", math.inf), ("window_hours", -30.0), ("window_hours", 10 ** 400),
    ("window_end", None), ("window_end", 0), ("window_end", -1), ("window_end", "1790000000"), ("window_end", True),
    ("window_end", 1.79e9),
    ("services", None), ("services", 7), ("services", 9), ("services", "8"), ("services", True),
])
def test_a_g18_row_with_missing_or_bad_evidence_does_not_count(tmp_path, field, bad):
    row = {"ok": True, **EVIDENCE}
    if bad is None:
        del row[field]
    else:
        row[field] = bad
    assert not sc.g18_evidence_ok(row)
    if not (isinstance(bad, float) and not math.isfinite(bad)) and not (isinstance(bad, int) and bad == 10 ** 400):
        # NaN/inf/huge ints are not JSON round-trippable; the in-memory check above covers them
        assert _refusal(_ready(tmp_path, g18=row)) == "gate_G18_not_recorded"


def test_exactly_24_hours_is_enough(tmp_path):
    assert _refusal(_ready(tmp_path, g18={"ok": True, **EVIDENCE, "window_hours": 24})) is None


@pytest.mark.parametrize("ok", ["true", 1, "1", "yes", False, None, [True], {"v": True}])
def test_a_g18_row_whose_ok_is_not_exactly_true_does_not_count(tmp_path, ok):
    row = {**EVIDENCE} if ok is None else {"ok": ok, **EVIDENCE}
    assert _refusal(_ready(tmp_path, g18=row)) == "gate_G18_not_recorded"


@pytest.mark.parametrize("ok", ["true", 1, "1", False, None])
def test_a_g22_row_whose_ok_is_not_exactly_true_does_not_count(tmp_path, ok):
    r = sc.Records(tmp_path / "records.jsonl")
    r.append("alerts_proven", ok=True)
    r.append("gate", gate="G18", ok=True, **EVIDENCE)
    if ok is None:
        r.append("gate", gate="G22")
    else:
        r.append("gate", gate="G22", ok=ok)
    assert not r.gate_ok("G22")
    assert _refusal(r) == "gate_G22_not_recorded"


def test_a_good_g18_row_still_needs_the_build_sha_when_one_is_given(tmp_path):
    sha = "ab12cd34" * 5
    r = sc.Records(tmp_path / "records.jsonl")
    r.append("alerts_proven", ok=True, sha8=sha[:8])
    r.append("gate", gate="G22", ok=True, sha8=sha[:8])
    r.append("gate", gate="G18", ok=True, **EVIDENCE)                         # evidence, but no sha8
    with pytest.raises(sc.Refused) as e:
        sc.preconditions(2, r, GO, build_sha=sha)
    assert e.value.reason == "gate_G18_not_recorded"


# ---- the writer side: stage1_window --------------------------------------------------------------------------------

def _snap(t):
    return {"taken_at": t, "counters": {
        label: {k: 0 for k in sc.COUNTER_KEYS} for label, _path, _svc in sw.OPERATOR_BLOCK_SERVICES}}


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_one_minimum_defines_both_sides():
    assert sw.DEFAULT_MIN_HOURS == sc.G18_MIN_WINDOW_HOURS == 24.0
    assert len(sw.OPERATOR_BLOCK_SERVICES) == len(sc.EIGHT_SERVICES)


def test_stage1_window_writes_no_g18_row_for_a_clean_window_under_24_hours(tmp_path, capsys):
    b, a = _write(tmp_path, "b.json", _snap(0)), _write(tmp_path, "a.json", _snap(2 * 3600))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--min-hours", "1", "--records", str(rec)]) == 1
    assert not rec.exists()
    assert "no row written" in capsys.readouterr().out


def test_the_row_stage1_window_writes_is_one_the_controller_counts(tmp_path):
    b, a = _write(tmp_path, "b.json", _snap(0)), _write(tmp_path, "a.json", _snap(30 * 3600))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec)]) == 0
    r = sc.Records(rec)
    assert r.gate_ok("G18")
    r.append("alerts_proven", ok=True)
    r.append("gate", gate="G22", ok=True)
    assert _refusal(r) is None


# ---- B5 review (teammate-don on 6b7d072): the writer checks its own row ----------------------------------------------

def test_stage1_window_writes_a_counted_row_at_exactly_24_hours(tmp_path):
    b, a = _write(tmp_path, "b.json", _snap(0)), _write(tmp_path, "a.json", _snap(24 * 3600))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec)]) == 0
    assert sc.Records(rec).gate_ok("G18")


def test_stage1_window_writes_no_row_just_under_24_hours(tmp_path):
    b, a = _write(tmp_path, "b.json", _snap(0)), _write(tmp_path, "a.json", _snap(24 * 3600 - 1))
    rec = tmp_path / "records.jsonl"
    assert sw.main(["evaluate", "--before", b, "--after", a, "--min-hours", "1", "--records", str(rec)]) == 1
    assert not rec.exists()


def _with_ninth_label(snap):
    snap["counters"]["extra-service"] = {k: 0 for k in sc.COUNTER_KEYS}
    return snap


@pytest.mark.parametrize("case", ["ninth_label", "negative_taken_at"])
def test_stage1_window_never_prints_recorded_for_a_row_the_controller_ignores(tmp_path, capsys, case):
    if case == "ninth_label":
        before, after = _with_ninth_label(_snap(0)), _with_ninth_label(_snap(30 * 3600))
    else:
        before, after = _snap(-40 * 3600), _snap(-10 * 3600)     # window_end before the epoch
    b, a = _write(tmp_path, "b.json", before), _write(tmp_path, "a.json", after)
    rec = tmp_path / "records.jsonl"
    code = sw.main(["evaluate", "--before", b, "--after", a, "--records", str(rec)])
    out = capsys.readouterr().out
    assert "recorded gate G18" not in out
    assert not sc.Records(rec).gate_ok("G18")
    if code == 0:                                  # only acceptable if no row was written at all
        assert not rec.exists()
