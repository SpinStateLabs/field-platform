"""S10-25, reduced rebuild of PR 958: the two stale-flag fields main's StaleStore._load does not check.

A flag whose ``flagged_at`` is missing, unparseable, naive or not text, or that has no usable ``framework``, is a named
``StaleStoreError`` from ``status()`` / ``active()`` (the 503 and exit-2 handlers main already has then apply), never an
unhandled TypeError/ValueError/KeyError (a 500 or a traceback). The message never carries the file's text. Every value is
made up. (The rest of PR 958's tests are main's already: the damaged-file shapes, 503 routes and CLI verbs.)"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app
from compliance_crosswalk.staleness import StaleStore, StaleStoreError

MARK = "MARKER-7a52"
GOOD_FLAG = {"framework": "osfi-e23", "reason": "r", "flagged_at": "2026-11-01T00:00:00+00:00"}


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    return tmp_path


def write(data_dir, content: bytes):
    path = data_dir / "crosswalk_stale_flags.json"
    path.write_bytes(content)
    return path


BAD_FLAGGED_AT = [
    {"framework": "osfi-e23", "reason": "r"},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": "not-a-date"},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": "2026-11-01T00:00:00"},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": 12345},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": None},
    {"framework": "osfi-e23", "reason": "r", "flagged_at": [MARK]},
]
BAD_IDS = ["missing", "unparseable", "naive", "int", "null", "list"]


@pytest.mark.parametrize("flag", BAD_FLAGGED_AT, ids=BAD_IDS)
def test_a_flag_with_a_bad_flagged_at_is_a_named_error_from_status(data_dir, flag):
    store = StaleStore(write(data_dir, json.dumps({"active": {"osfi-e23": flag}}).encode()))
    with pytest.raises(StaleStoreError, match="flagged_at") as exc:
        store.status()
    assert MARK not in str(exc.value)


@pytest.mark.parametrize("flag", [{"flagged_at": GOOD_FLAG["flagged_at"]}, {**GOOD_FLAG, "framework": None}],
                         ids=["missing", "null"])
def test_a_flag_without_a_usable_framework_is_a_named_error(data_dir, flag):
    two = {"active": {"x": flag, "osfi-e23": GOOD_FLAG}}       # two flags, so the sort really compares a key
    store = StaleStore(write(data_dir, json.dumps(two).encode()))
    with pytest.raises(StaleStoreError, match="framework"):
        store.active()
    with pytest.raises(StaleStoreError, match="framework"):
        store.status()


def test_a_good_flag_reports_its_window(data_dir):
    store = StaleStore(write(data_dir, json.dumps({"active": {"osfi-e23": GOOD_FLAG}}).encode()))
    (flag,) = store.status()["active"]
    assert flag["stale_window_seconds"] > 0


@pytest.mark.parametrize("flag", BAD_FLAGGED_AT, ids=BAD_IDS)
def test_get_staleness_answers_the_existing_503_for_a_bad_flagged_at(data_dir, flag):
    write(data_dir, json.dumps({"active": {"osfi-e23": flag}}).encode())
    r = TestClient(create_app(), raise_server_exceptions=False).get("/staleness")
    assert r.status_code == 503 and "flagged_at" in r.json()["detail"]
    assert MARK not in r.text and str(data_dir) not in r.text


def test_get_staleness_still_serves_a_valid_store(data_dir):
    write(data_dir, json.dumps({"active": {"osfi-e23": GOOD_FLAG}}).encode())
    r = TestClient(create_app()).get("/staleness")
    assert r.status_code == 200 and [f["framework"] for f in r.json()["active"]] == ["osfi-e23"]
