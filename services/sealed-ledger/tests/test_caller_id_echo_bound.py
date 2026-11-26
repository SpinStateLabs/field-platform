"""S12-19: an unbounded caller_id is not echoed whole into the 403 detail or the server log.

AppendRequest bounds the three caller fields (422), and the refusal texts show at most the first 64 characters of a
caller_id with its length, so a store reached directly (or a value under the field cap) cannot grow a response body or a
log line without bound. Refusal semantics and status codes are unchanged."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from sealed_ledger.api import create_app
from sealed_ledger.store import CallerPolicy, CallerRefused
from test_caller_signing_f2b import STOP_TYPES, _body, _store, callers  # noqa: F401 (fixture)

BIG = "A" * 1_000_000


def _client(tmp_path, callers, **kw):  # noqa: F811
    s = _store(tmp_path, callers, **kw)
    return s, TestClient(create_app(store=s))


@pytest.mark.parametrize("field,limit", [("caller_id", 200), ("caller_ts", 64), ("caller_signature", 200)])
def test_an_oversized_caller_field_is_the_fixed_422(tmp_path, callers, field, limit):  # noqa: F811
    _, client = _client(tmp_path, callers)
    claim = {"caller_id": "svc", "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"}
    ok = client.post("/events", json=_body("action", "a", {}, {**claim, field: "x" * limit}))
    assert ok.status_code != 422, ok.text  # exactly at the limit is not a size refusal
    big = client.post("/events", json=_body("action", "a", {}, {**claim, field: "x" * (limit + 1)}))
    assert big.status_code == 422
    assert len(big.text) < 1000


def test_a_long_invalid_caller_id_is_shown_truncated_in_the_403_detail(tmp_path, callers):  # noqa: F811
    _, client = _client(tmp_path, callers)
    cid = "B" * 150  # under the field cap, over the 63-character id rule
    r = client.post("/events", json=_body("action", "a", {}, {
        "caller_id": cid, "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"}))
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert cid not in detail and "B" * 64 in detail and "B" * 65 not in detail and "(150 characters)" in detail
    assert len(detail) < 300


def test_the_store_refusal_text_is_bounded_for_a_megabyte_caller_id(tmp_path, callers):  # noqa: F811
    policy = CallerPolicy(callers["keyring"])
    with pytest.raises(CallerRefused) as exc:
        policy.check("action", {}, "a", {
            "caller_id": BIG, "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"})
    assert BIG not in str(exc.value) and len(str(exc.value)) < 300 and "(1000000 characters)" in str(exc.value)


def test_the_stop_type_warning_line_is_bounded_under_the_require_switch(tmp_path, callers, caplog):  # noqa: F811
    caplog.set_level(logging.WARNING, logger="sealed_ledger.store")
    policy = CallerPolicy(callers["keyring"], require_caller_signature=True)
    got = policy.check(STOP_TYPES[0], {}, "a", {
        "caller_id": BIG, "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"})
    assert got == {"caller_unsigned": True}
    lines = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert lines and all(len(m) < 500 and BIG not in m for m in lines)


def test_the_under_limit_unknown_caller_message_is_unchanged(tmp_path, callers):  # noqa: F811
    _, client = _client(tmp_path, callers)
    r = client.post("/events", json=_body("action", "a", {}, {
        "caller_id": "stranger", "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"}))
    assert r.status_code == 403
    assert r.json()["detail"].startswith("unknown caller 'stranger': no stranger.pub.pem in the keyring (")


def test_a_short_invalid_caller_id_is_shown_whole(tmp_path, callers):  # noqa: F811
    _, client = _client(tmp_path, callers)
    r = client.post("/events", json=_body("action", "a", {}, {
        "caller_id": "Bad_Id", "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"}))
    assert r.json()["detail"] == "unknown caller 'Bad_Id': not a valid caller id"


def test_the_no_keyring_refusal_text_is_bounded_for_a_megabyte_caller_id():
    with pytest.raises(CallerRefused) as exc:
        CallerPolicy(None).check("action", {}, "a", {
            "caller_id": BIG, "caller_ts": "2026-01-01T00:00:00+00:00", "caller_signature": "sig"})
    assert "keyring not configured" in str(exc.value)
    assert BIG not in str(exc.value) and len(str(exc.value)) < 400
