"""S2-19: a malformed roster is a 4xx/503, not a 500; a junk FIELD_LIFECYCLE_EVERY is loud, never a crash."""

import logging

import pytest
from fastapi.testclient import TestClient

from lifecycle_manager.api import MIN_ENV_EVERY_S, create_app, scheduled_tick

from test_roster_aliases import FakeRegistry, NoTokens, RecordingLedger, agent

BAD = "owner,aliases\nDon Hagell,Don Hagell, Spin State Labs\n"


def build(**kw):
    return create_app(registry=FakeRegistry([agent("a", "Verifier")]), delegation=NoTokens(),
                      ledger=RecordingLedger(), **kw)


def test_a_malformed_roster_in_the_request_body_is_422_with_the_parse_message(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    r = TestClient(build(every=0), raise_server_exceptions=False).post("/sweep", json={"roster_csv": BAD})
    assert r.status_code == 422 and "more fields than the header" in r.json()["detail"]
    assert "Spin State Labs" not in r.text   # a line number, never the content


def test_a_malformed_configured_roster_file_is_503_and_the_tick_still_reports_not_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    bad = tmp_path / "owners.csv"
    bad.write_text(BAD, encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(bad))
    served = build(every=0)
    r = TestClient(served, raise_server_exceptions=False).post("/sweep", json={})
    assert r.status_code == 503 and "more fields than the header" in r.json()["detail"]
    tick = scheduled_tick(served)
    assert tick["ok"] is False and "more fields than the header" in tick["error"]


@pytest.mark.parametrize("raw", ["1h", "3600s", "-5", "²", "①", "1²", "3600.0", " "])
def test_a_junk_interval_leaves_the_scheduler_off_with_a_warning_and_never_raises(raw, monkeypatch, caplog):
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", raw)
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        served = build()
    assert TestClient(served).get("/health").json()["every"] == 0
    assert ("FIELD_LIFECYCLE_EVERY" in caplog.text) is (raw.strip() != "")
    assert raw not in caplog.text or raw.strip() == ""   # the value is never echoed


@pytest.mark.parametrize("raw, expected", [("3600", 3600), ("60", 60), ("1", MIN_ENV_EVERY_S), ("59", MIN_ENV_EVERY_S),
                                           ("0", 0), ("", 0)])
def test_a_small_interval_from_the_environment_is_raised_to_the_floor(raw, expected, monkeypatch):
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", raw)
    assert TestClient(build()).get("/health").json()["every"] == expected
