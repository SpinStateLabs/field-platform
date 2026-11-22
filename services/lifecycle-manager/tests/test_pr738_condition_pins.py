"""PR 738 reviewer-6 conditions (V1, V6, V9, V11-V13, V20): pin the roster cap, the interval floor,
the ASCII-digit rule, the floor warning and the empty-roster refusal with literal values."""

import logging

import pytest
from fastapi.testclient import TestClient

from lifecycle_manager import api as lm_api
from lifecycle_manager.api import create_app

from test_roster_aliases import FakeRegistry, NoTokens, RecordingLedger, agent


def build(**kw):
    return create_app(registry=FakeRegistry([agent("a", "Verifier")]), delegation=NoTokens(),
                      ledger=RecordingLedger(), **kw)


def _many_short_rows(total):
    """A roster of exactly `total` characters made of short rows (no field near the csv field limit)."""
    head = "owner\n"
    k, r = divmod(total - len(head), 4)
    text = head + "Don\n" * k + "D" * r   # the last row carries the remainder
    assert len(text) == total
    return text


def test_the_literal_limits_are_pinned():
    assert lm_api.ROSTER_CSV_MAX_CHARS == 1048576
    assert lm_api.MIN_ENV_EVERY_S == 60


def test_the_cap_is_enforced_for_short_rows_exactly_at_one_mebibyte(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(build(every=0), raise_server_exceptions=False)
    at_cap = client.post("/sweep", json={"roster_csv": _many_short_rows(1048576)})
    assert at_cap.status_code != 422, at_cap.text[:200]
    over = client.post("/sweep", json={"roster_csv": _many_short_rows(1048577)})
    assert over.status_code == 422


@pytest.mark.parametrize("raw, expected", [("59", 60), ("30", 60), ("60", 60), ("61", 61)])
def test_the_floor_is_the_literal_sixty_seconds(raw, expected, monkeypatch):
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", raw)
    assert TestClient(build()).get("/health").json()["every"] == expected


def test_a_raised_interval_logs_a_warning_naming_the_variable(monkeypatch, caplog):
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", "30")
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        build()
    assert "FIELD_LIFECYCLE_EVERY" in caplog.text and "floor" in caplog.text


# Arabic-Indic and fullwidth decimal digits: str.isdecimal() is true and int() accepts them.
@pytest.mark.parametrize("raw", ["".join(chr(c) for c in (0x663, 0x666, 0x660, 0x660)),
                                 "".join(chr(c) for c in (0xFF13, 0xFF16, 0xFF10, 0xFF10))])
def test_non_ascii_decimal_digits_leave_the_scheduler_off(raw, monkeypatch, caplog):
    assert int(raw) == 3600 and raw.isdecimal() and not raw.isascii()
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", raw)
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        served = build()
    assert TestClient(served).get("/health").json()["every"] == 0
    assert "FIELD_LIFECYCLE_EVERY" in caplog.text and raw not in caplog.text


@pytest.mark.parametrize("text", ["owner\n", "owner\n\n\n"])
def test_an_owner_less_roster_in_the_body_is_refused_not_an_empty_sweep(text, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    r = TestClient(build(every=0), raise_server_exceptions=False).post("/sweep", json={"roster_csv": text})
    assert r.status_code == 503 and "no owners" in r.json()["detail"]
