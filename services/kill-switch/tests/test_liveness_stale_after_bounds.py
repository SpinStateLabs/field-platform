"""`GET /liveness?stale_after=` accepts only a finite window of 1 second up to one year (scout P-7, reviewer K-3).

Before: only `stale_after <= 0` was refused. `nan` passes `nan <= 0` (False) and `timedelta(seconds=nan)` raises
ValueError; `inf` and `1e12` overflow `now - timedelta(...)`: a 500 for a query-string value. Now every non-finite or
out-of-range value is the same 422 as 0, and the 422 never repeats the value (C-1189's field-core handler)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

ONE_YEAR = 365 * 24 * 3600


@pytest.fixture()
def kill(tmp_path):
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    return TestClient(create_kill_app(
        registry=RegistryClient(client=registry, base_url="http://t"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
    ))


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "Infinity", "1e12", "1e308", str(ONE_YEAR + 1), "0", "-5"])
def test_a_non_finite_or_out_of_range_window_is_422(kill, value):
    r = kill.get("/liveness", params={"stale_after": value})
    assert r.status_code == 422, (value, r.status_code)


@pytest.mark.parametrize("value", ["1", "0.5", "60", "3600", str(ONE_YEAR)])
def test_a_sane_window_is_200(kill, value):
    r = kill.get("/liveness", params={"stale_after": value})
    assert r.status_code == 200, (value, r.status_code, r.text)


def test_the_default_window_is_200(kill):
    assert kill.get("/liveness").status_code == 200


def test_the_422_never_repeats_the_value(kill):
    r = kill.get("/liveness", params={"stale_after": "1e12"})
    assert r.status_code == 422 and "1e12" not in r.text
