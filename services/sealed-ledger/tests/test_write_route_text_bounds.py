"""S5-10: the write routes cap the free text that lands in the hash chain, refuse a blank event_type, and never put an
OSError's text (a server path) in a response. Every value is a made-up marker."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from field_core.signing import generate_keypair

from sealed_ledger.api import NAME_MAX, REASON_MAX, create_app
from sealed_ledger.store import LedgerStore

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    priv, _ = generate_keypair()
    (tmp_path / "k.pem").write_text(priv)
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(tmp_path / "k.pem"))
    store = LedgerStore(tmp_path / "events.jsonl")
    return TestClient(create_app(store=store)), store


def length(store):
    return store.snapshot().global_length


def over(n):
    return MARK + "x" * (n - len(MARK) + 1)


def at(n):
    return "y" * n


# ---- append -------------------------------------------------------------------------------------------------------

def test_limits_are_the_card_numbers():
    assert (NAME_MAX, REASON_MAX) == (200, 2000)


@pytest.mark.parametrize("field", ["event_type", "agent_id"])
def test_append_at_limit_is_accepted(env, field):
    c, s = env
    body = {"event_type": "t.e", "agent_id": "a"}
    body[field] = at(NAME_MAX)
    assert c.post("/events", json=body).status_code in (200, 201)
    assert length(s) == 1


@pytest.mark.parametrize("field", ["event_type", "agent_id"])
def test_append_over_limit_is_422_not_echoed_and_not_written(env, field):
    c, s = env
    body = {"event_type": "t.e", "agent_id": "a"}
    body[field] = over(NAME_MAX)
    r = c.post("/events", json=body)
    assert r.status_code == 422 and MARK not in r.text
    assert length(s) == 0


@pytest.mark.parametrize("blank", ["   ", "\t\n", " "])
def test_append_blank_event_type_is_422_and_not_written(env, blank):
    c, s = env
    r = c.post("/events", json={"event_type": blank})
    assert r.status_code == 422 and length(s) == 0


def test_append_payload_stays_unbounded(env):
    c, s = env
    assert c.post("/events", json={"event_type": "t.e", "payload": {"big": "z" * 500_000}}).status_code in (200, 201)


# ---- rotate / hold / release / retention ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,field,limit", [
    ("/rotate", "operator", NAME_MAX), ("/rotate", "reason", REASON_MAX),
    ("/hold", "by", NAME_MAX), ("/hold", "reason", REASON_MAX),
])
def test_write_routes_over_limit_422_no_echo_nothing_written(env, path, field, limit):
    c, s = env
    s.append("seed", {})
    before = length(s)
    body = {"operator": "o", "reason": "r"} if path == "/rotate" else {"by": "b", "reason": "r"}
    body[field] = over(limit)
    r = c.post(path, json=body)
    assert r.status_code == 422 and MARK not in r.text
    assert length(s) == before


@pytest.mark.parametrize("field,limit", [("by", NAME_MAX), ("reason", REASON_MAX)])
def test_hold_at_limit_is_accepted(env, field, limit):
    c, s = env
    body = {"by": "b", "reason": "r"}
    body[field] = at(limit)
    assert c.post("/hold", json=body).status_code == 201


def test_rotate_at_limit_is_not_a_422(env):
    c, s = env
    s.append("seed", {})
    r = c.post("/rotate", json={"operator": at(NAME_MAX), "reason": at(REASON_MAX)})
    assert r.status_code != 422, r.text


def test_hold_release_by_over_limit(env):
    c, s = env
    r = c.post("/hold/release", json={"by": over(NAME_MAX)})
    assert r.status_code == 422 and MARK not in r.text


def test_retention_operator_over_limit(env):
    c, s = env
    r = c.post("/retention/apply", json={"days": 1, "operator": over(NAME_MAX)})
    assert r.status_code == 422 and MARK not in r.text


# ---- OSError text -------------------------------------------------------------------------------------------------

def test_hold_status_oserror_answers_without_the_path_and_keeps_the_busy_prefix(env, monkeypatch):
    c, s = env
    def boom():
        raise PermissionError(13, "denied", "/srv/secret-path/hold.marker")
    monkeypatch.setattr(s, "hold_status", boom)
    r = c.get("/hold")
    assert r.status_code == 503
    assert "secret-path" not in r.text and r.json()["detail"].startswith("ledger busy")
    assert "PermissionError" in r.text


def test_retention_apply_oserror_answers_without_the_path(env, monkeypatch):
    c, s = env
    def boom(**k):
        raise OSError(5, "io", "/srv/secret-path/archive")
    monkeypatch.setattr(s, "archive_closed_segments", boom)
    r = c.post("/retention/apply", json={"days": 1, "operator": "o"})
    assert r.status_code == 500 and "secret-path" not in r.text and "OSError" in r.text
