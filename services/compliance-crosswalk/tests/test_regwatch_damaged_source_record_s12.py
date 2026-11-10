"""S12-26: a damaged stored source record is a named 'store-damaged' row, never a traceback and never a silent re-baseline.

_compare used the stored `prior` as is: `prior["first_seen"]` (KeyError), `int(prior.get("raw_bytes", 0))` (ValueError /
TypeError), `dict(record)` in source_record (TypeError for a non-dict), and `{}` fell into the changed branch. All of it ran
inside store.transaction(), so run_check was an anonymous traceback (a 500 from POST /regwatch/check). A re-baseline would
erase a change detection, so the damaged URL is left exactly as stored and the run exits 2."""
from __future__ import annotations

import json

import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.mapping import SRC_EU_OFFICIAL, SRC_NIST, SRC_OSFI
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
