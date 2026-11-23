"""S11-20: FIELD_LEDGER_READ_CONCURRENCY. A negative or non-integer value falls
back to the default 1 (a negative used to become 0 = no gate), is logged once by
name only, and shows on /health; only an explicit 0 is unlimited."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from sealed_ledger.api import create_app
from sealed_ledger.store import READ_CONCURRENCY_ENV, LedgerStore, read_concurrency

CASES = [
    (None, 1, False),
    ("", 1, False),
    (" 3 ", 3, False),
    ("2", 2, False),
    ("0", 0, False),
    ("-1", 1, True),
    ("abc", 1, True),
    ("1.5", 1, True),
]


@pytest.mark.parametrize("setting,width,invalid", CASES)
def test_width_warning_health_and_lane(tmp_path, monkeypatch, caplog, setting, width, invalid):
    if setting is not None:
        monkeypatch.setenv(READ_CONCURRENCY_ENV, setting)
    caplog.set_level(logging.WARNING, logger="sealed_ledger.store")
    assert read_concurrency() == width
    store = LedgerStore(tmp_path / "events.jsonl")
    assert store.read_concurrency == width
    warned = [r for r in caplog.records if READ_CONCURRENCY_ENV in r.getMessage()]
    assert len(warned) == (1 if invalid else 0)
    if invalid and setting:
        assert setting not in warned[0].getMessage()  # the variable, never the value
    app = create_app(store=store)
    assert app.state.lanes["read"]._max_workers == (width or 32)
    body = TestClient(app).get("/health").json()
    assert body["read_concurrency"] == width
    assert body["read_concurrency_invalid"] is invalid
