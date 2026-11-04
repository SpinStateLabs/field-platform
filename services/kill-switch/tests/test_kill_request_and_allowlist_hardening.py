"""S4-4: three hardening gaps in the kill-switch API.

(a) KillRequest only had min_length=1: operator ' ' or reason a tab passed and reached the kill/revive/drill ledger
    rows, and neither field had a maximum. Now blank (after strip) is a 422 and operator <= 200, reason <= 1000.
(b) _allowlist() stripped but did not lower-case, while the compared urlsplit(...).hostname is always lower-case, so
    FIELD_KILL_ENDPOINT_ALLOWLIST=Agent.Internal never matched and the halt signal was skipped. Entries are lower-cased;
    the EXACT-match rule is kept.
(c) POST /heartbeat/{agent_id} wrote a row per distinct path id with no bound. An id over 128 characters, or with a
    control character, is a 422 on the POST only; a normal unregistered id still surfaces as a shadow agent.
A 422 never repeats what was sent (C-1189)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kill_switch.api import create_app
from kill_switch.store import HeartbeatStore

from test_endpoint_and_liveness import Stack, FakeEndpoint

MARK = "MADE-UP-MARKER-0123456789"
OK = {"operator": "CISO on-call", "reason": "anomalous behavior"}
ROUTES = ["/kill/agent-1", "/kill/domain/dom-1", "/revive/agent-1", "/drill/agent-1"]


@pytest.fixture()
def client():
    return TestClient(create_app())


# ---- (a) blank and unbounded operator / reason -----------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("field", ["operator", "reason"])
@pytest.mark.parametrize("blank", [" ", "   ", "\t", "\n", " \t \n "])
def test_a_blank_operator_or_reason_is_a_422_on_every_route(client, path, field, blank):
    body = {**OK, field: blank}
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text
    assert any(e["loc"] == ["body", field] for e in r.json()["detail"]), r.text


@pytest.mark.parametrize("path", ROUTES)
def test_an_over_long_operator_or_reason_is_a_422(client, path):
    assert client.post(path, json={**OK, "operator": "o" * 201}).status_code == 422
    assert client.post(path, json={**OK, "reason": "r" * 1001}).status_code == 422


def test_the_bounds_themselves_are_accepted(tmp_path):
    stack = Stack(tmp_path)
    stack.register("agent-1")
    r = stack.kill.post("/kill/agent-1", json={"operator": "o" * 200, "reason": "r" * 1000})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("path", ROUTES)
def test_a_422_for_a_blank_or_long_value_never_repeats_it(client, path):
    for body in ({**OK, "reason": MARK * 200}, {**OK, "operator": MARK * 50}):
        r = client.post(path, json=body)
        assert r.status_code == 422 and MARK not in r.text, r.text


def test_a_blank_kill_writes_no_ledger_row_and_changes_nothing(tmp_path):
    stack = Stack(tmp_path)
    stack.register("agent-1")
    before = stack.event_types()
    assert stack.kill.post("/kill/agent-1", json={"operator": " ", "reason": "x"}).status_code == 422
    assert stack.kill.post("/kill/agent-1", json={"operator": "x", "reason": "\t"}).status_code == 422
    assert stack.event_types() == before
    assert stack.registry.get("/agents/agent-1").json()["status"] == "active"


def test_a_normal_kill_still_works_and_keeps_the_text_as_sent(tmp_path):
    stack = Stack(tmp_path)
    stack.register("agent-1")
    assert stack.kill.post("/kill/agent-1", json={"operator": "Don Hagell", "reason": "incident 42"}).status_code == 200


# ---- (b) the allowlist is lower-cased, matching stays exact ---------------------------------------------------------

HOST = "agent.internal"


@pytest.mark.parametrize("entry", ["Agent.Internal", "AGENT.INTERNAL", " Agent.Internal ", "other.host, Agent.Internal"])
def test_a_mixed_case_allowlist_entry_matches_the_lower_case_hostname(tmp_path, monkeypatch, entry):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", entry)
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", f"http://{HOST}/halt")
    result = stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]
    assert result["outcome"] == "called", result
    assert len(stack.endpoint.calls) == 1


def test_the_mixed_case_url_host_matches_too(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "Agent.Internal")
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", "http://AGENT.Internal/halt")
    assert stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]["outcome"] == "called"


@pytest.mark.parametrize("endpoint", [f"http://{HOST}.evil.com/h", f"http://not{HOST}/h", f"http://{HOST}@169.254.169.254/h",
                                      "http://other.internal/h"])
def test_matching_is_still_exact_after_lower_casing(tmp_path, monkeypatch, endpoint):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "Agent.Internal")
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", endpoint)
    result = stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "host_not_allowlisted"
    assert stack.endpoint.calls == []


def test_an_unset_allowlist_still_skips(tmp_path):
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", f"http://{HOST}/halt")
    assert stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]["reason"] == "allowlist_unset"


# ---- (c) the heartbeat POST bounds the id it records -----------------------------------------------------------------


@pytest.fixture()
def hb_stack(tmp_path):
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    yield Stack(tmp_path, heartbeats=store), store
    store.close()


@pytest.mark.parametrize("agent_id", ["a" * 129, "a" * 5000, "bad%00id", "bad%0Aid", "bad%1Fid", "bad%7Fid", "x%0D%0Ay"])
def test_an_over_long_or_control_character_id_is_a_422_and_nothing_is_recorded(hb_stack, agent_id):
    stack, store = hb_stack
    r = stack.kill.post(f"/heartbeat/{agent_id}")
    assert r.status_code == 422, r.text
    assert "a" * 129 not in r.text and "bad" not in r.text
    assert store.all() == {}


def test_the_422_for_a_bad_id_repeats_nothing_it_was_sent(hb_stack):
    stack, _ = hb_stack
    r = stack.kill.post(f"/heartbeat/{MARK * 20}")
    assert r.status_code == 422 and MARK not in r.text, r.text


def test_a_128_character_unregistered_id_still_surfaces_as_a_shadow_agent(hb_stack):
    stack, store = hb_stack
    shadow = "g" * 128
    body = stack.kill.post(f"/heartbeat/{shadow}").json()
    assert body["killed"] is True and body["status"] == "unregistered"
    assert store.get(shadow)["status"] == "unregistered"


def test_a_normal_unregistered_id_still_surfaces_as_a_shadow_agent(hb_stack):
    stack, store = hb_stack
    body = stack.kill.post("/heartbeat/ghost-agent").json()
    assert body["killed"] is True and body["status"] == "unregistered"
    assert store.get("ghost-agent")["status"] == "unregistered"


def test_the_read_only_get_is_not_bounded(hb_stack):
    stack, store = hb_stack
    assert stack.kill.get(f"/heartbeat/{'a' * 300}").status_code == 200       # a GET never writes, so no bound
    assert store.get("a" * 300) is None
