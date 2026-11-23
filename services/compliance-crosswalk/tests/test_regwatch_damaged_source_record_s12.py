"""S12-26: a damaged stored source record is a named 'store-damaged' row, never a traceback and never a silent re-baseline.

_compare used the stored `prior` as is: `prior["first_seen"]` (KeyError), `int(prior.get("raw_bytes", 0))` (ValueError /
TypeError), `dict(record)` in source_record (TypeError for a non-dict), and `{}` fell into the changed branch. All of it ran
inside store.transaction(), so run_check was an anonymous traceback (a 500 from POST /regwatch/check). A re-baseline would
erase a change detection, so the damaged URL is left exactly as stored and the run exits 2."""
from __future__ import annotations

import json

import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.mapping import SRC_EU_ART12, SRC_EU_ART14, SRC_EU_OFFICIAL, SRC_NIST, SRC_OSFI
from compliance_crosswalk.staleness import StaleStore
from test_regwatch import FakeFetcher, by_framework, page, store  # noqa: F401 (fixture)

DAMAGED_TEXT = "stored source record is damaged"
GOOD = {"sha256": "ab" * 32, "raw_bytes": 10, "first_seen": "2026-01-01T00:00:00+00:00"}


def _damage(store, url, record):
    """Baseline once, then overwrite one URL's stored record on disk with ``record``."""
    regwatch.run_check(store, FakeFetcher())
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["sources"][url] = record
    store.path.write_text(json.dumps(data), encoding="utf-8")
    return json.loads(store.path.read_text(encoding="utf-8"))["sources"]


BAD_RECORDS = [
    pytest.param({}, id="empty-dict"),
    pytest.param(5, id="int"),
    pytest.param("text", id="str"),
    pytest.param([GOOD], id="list"),
    pytest.param({"sha256": 7}, id="sha256-int"),
    pytest.param({"sha256": "x", "raw_bytes": "n/a", "first_seen": "t"}, id="raw-bytes-str"),
    pytest.param({"sha256": "x", "raw_bytes": None, "first_seen": "t"}, id="raw-bytes-null"),
    pytest.param({"sha256": "x", "raw_bytes": True, "first_seen": "t"}, id="raw-bytes-bool"),
    pytest.param({"sha256": "x", "raw_bytes": 3}, id="first-seen-missing"),
    pytest.param({"raw_bytes": 3, "first_seen": "t"}, id="sha256-missing"),
    pytest.param({"sha256": 7, "raw_bytes": 3, "first_seen": "t"}, id="sha256-int-others-fine"),
    pytest.param({"sha256": "x", "first_seen": "t"}, id="raw-bytes-missing"),
    pytest.param({"sha256": "x", "raw_bytes": 3, "first_seen": 9}, id="first-seen-int"),
]


@pytest.mark.parametrize("record", BAD_RECORDS)
def test_a_damaged_record_is_a_named_row_exit_2_and_stays_exactly_as_stored(store, record):  # noqa: F811
    before = _damage(store, SRC_OSFI, record)
    report = regwatch.run_check(store, FakeFetcher())
    rows = by_framework(report)
    assert report["exit_code"] == regwatch.EXIT_UNREACHABLE == 2
    assert rows["osfi-e23"]["status"] == "store-damaged"
    source = rows["osfi-e23"]["sources"][0]
    assert source["status"] == "store-damaged" and source["url"] == SRC_OSFI and DAMAGED_TEXT in source["error"]
    assert SRC_OSFI in report["unreachable"] and report["flagged"] == []
    assert rows["osfi-e23"]["flag_active"] is False and store.active() == []
    after = json.loads(store.path.read_text(encoding="utf-8"))["sources"]
    assert after[SRC_OSFI] == before[SRC_OSFI]          # not re-baselined, not touched
    # the other frameworks are still read, and their records still advance
    assert rows["nist-ai-rmf"]["status"] == "unchanged" and rows["eu-ai-act"]["status"] == "unchanged"
    assert after[SRC_NIST]["last_seen"] != before[SRC_NIST]["last_seen"]


def test_the_damaged_text_does_not_echo_the_stored_value(store):  # noqa: F811
    _damage(store, SRC_OSFI, {"sha256": "SECRET-STORED-VALUE", "raw_bytes": "n/a", "first_seen": "t"})
    report = regwatch.run_check(store, FakeFetcher())
    assert "SECRET-STORED-VALUE" not in json.dumps(report)


def test_a_damaged_record_does_not_hide_a_change_elsewhere(store):  # noqa: F811
    _damage(store, SRC_OSFI, 5)
    changed = FakeFetcher({SRC_NIST: page("NIST text that is entirely different now.")})
    report = regwatch.run_check(store, changed)
    assert by_framework(report)["osfi-e23"]["status"] == "store-damaged"
    assert report["exit_code"] == regwatch.EXIT_CHANGED


def test_a_valid_record_is_still_compared_as_before(store):  # noqa: F811
    regwatch.run_check(store, FakeFetcher())
    report = regwatch.run_check(store, FakeFetcher())
    assert report["exit_code"] == 0
    assert {r["status"] for r in report["frameworks"] if r["framework"] != "iso-42001"} == {"unchanged"}


def test_check_file_refuses_a_damaged_record_and_writes_nothing(store, tmp_path):  # noqa: F811
    before = _damage(store, SRC_OSFI, 5)
    page = tmp_path / "osfi.html"
    page.write_bytes(FakeFetcher().default)
    with pytest.raises(regwatch.ManualFileRefused) as exc:
        regwatch.check_file("osfi-e23", page, "tester", store=store)
    assert DAMAGED_TEXT in str(exc.value)
    assert json.loads(store.path.read_text(encoding="utf-8"))["sources"] == before


# --- reviewer round (roley.reviewer, don.reviewer): the invariant is that a standing stale flag is never cleared or hidden ----


def _write_record(store, url, record):
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["sources"][url] = record
    store.path.write_text(json.dumps(data), encoding="utf-8")


def test_C1_a_standing_flag_survives_a_damaged_run_and_flag_active_stays_true(store):  # noqa: F811
    regwatch.run_check(store, FakeFetcher())
    changed = FakeFetcher({SRC_NIST: page("NIST text that is entirely different now.")})
    assert regwatch.run_check(store, changed)["exit_code"] == regwatch.EXIT_CHANGED
    flag_before = [f for f in store.active() if f["framework"] == "nist-ai-rmf"]
    assert flag_before, "the change run must leave a standing flag"
    _write_record(store, SRC_NIST, 5)
    report = regwatch.run_check(store, changed)
    row = by_framework(report)["nist-ai-rmf"]
    assert row["status"] == "store-damaged" and row["flag_active"] is True
    assert [f for f in store.active() if f["framework"] == "nist-ai-rmf"] == flag_before   # not cleared, not rewritten
    assert report["exit_code"] == regwatch.EXIT_UNREACHABLE


def test_C1_a_flag_on_another_framework_is_untouched_by_a_damaged_run(store):  # noqa: F811
    regwatch.run_check(store, FakeFetcher())
    regwatch.run_check(store, FakeFetcher({SRC_NIST: page("NIST text that is entirely different now.")}))
    flag_before = [f for f in store.active() if f["framework"] == "nist-ai-rmf"]
    _write_record(store, SRC_OSFI, 5)
    report = regwatch.run_check(store, FakeFetcher({SRC_NIST: page("NIST text that is entirely different now.")}))
    rows = by_framework(report)
    assert rows["osfi-e23"]["status"] == "store-damaged" and rows["nist-ai-rmf"]["flag_active"] is True
    assert [f for f in store.active() if f["framework"] == "nist-ai-rmf"] == flag_before


def test_C2_a_damaged_mirror_record_and_a_change_on_the_other_mirror_in_the_same_framework(store):  # noqa: F811
    official_down = {SRC_EU_OFFICIAL: ConnectionError("down")}
    regwatch.run_check(store, FakeFetcher(official_down))                 # baseline the mirror tier
    before_art12 = json.loads(store.path.read_text(encoding="utf-8"))["sources"][SRC_EU_ART12]
    _write_record(store, SRC_EU_ART12, 5)
    report = regwatch.run_check(store, FakeFetcher({**official_down, SRC_EU_ART14: page("Article 14 text is entirely different now.")}))
    row = by_framework(report)["eu-ai-act"]
    by_url = {s["url"]: s["status"] for s in row["sources"]}
    assert by_url[SRC_EU_ART12] == "store-damaged" and by_url[SRC_EU_ART14] == "changed"
    assert row["status"] == "changed" and report["exit_code"] == regwatch.EXIT_CHANGED
    assert json.loads(store.path.read_text(encoding="utf-8"))["sources"][SRC_EU_ART12] == 5   # left as stored
    assert before_art12 != 5


def test_C3_a_non_dict_record_is_never_echoed_by_run_check_or_check_file(store, tmp_path):  # noqa: F811
    regwatch.run_check(store, FakeFetcher())
    _write_record(store, SRC_OSFI, "SECRET-STORED-VALUE")
    assert "SECRET-STORED-VALUE" not in json.dumps(regwatch.run_check(store, FakeFetcher()))
    src = tmp_path / "osfi.html"
    src.write_bytes(FakeFetcher().default)
    with pytest.raises(regwatch.ManualFileRefused) as exc:
        regwatch.check_file("osfi-e23", src, "tester", store=store)
    assert "SECRET-STORED-VALUE" not in str(exc.value)
