"""S10-16: a FIELD_KILL_ENDPOINT_ALLOWLIST entry that can never match is counted on /health instead of failing silently.

`_allowlist()` compares its entries with `urlsplit(endpoint).hostname`, which never carries a port, scheme, path, userinfo or IPv6
brackets. An operator who wrote `canary-agent:8090`, `http://canary-agent` or `[::1]` got `host_not_allowlisted` on every kill and
the agent-side halt signal was never sent, with no sign why. Matching is unchanged (those entries never matched and still do not);
`/health` now reports `allowlist_entries_unusable`, a NUMBER only (never entry text, C-1189)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kill_switch.api import create_app

from test_endpoint_and_liveness import Stack

OK = {"operator": "CISO on-call", "reason": "anomalous behavior"}
HOST = "agent.internal"
MARK = "MADE-UP-MARKER-0123456789"


def unusable(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("FIELD_KILL_ENDPOINT_ALLOWLIST", raising=False)
    else:
        monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", value)
    body = TestClient(create_app()).get("/health").json()
    return body["allowlist_entries_unusable"], body


@pytest.mark.parametrize("value", [None, "", "  ", " , ,"])
def test_an_unset_or_blank_allowlist_has_none_unusable(monkeypatch, value):
    assert unusable(monkeypatch, value)[0] == 0


@pytest.mark.parametrize("value", [
    "agent.internal", "Agent.Internal", " agent.internal , other.host ", "127.0.0.1", "::1", "2001:db8::1",
    "agent_1.internal", "agent-1", "agent.internal.", "a.b.c.d.example.com",
])
def test_bare_hostnames_and_ip_literals_are_usable(monkeypatch, value):
    assert unusable(monkeypatch, value)[0] == 0


@pytest.mark.parametrize("entry", [
    "canary-agent:8090", "agent.internal:443", "http://canary-agent", "https://canary-agent/", "[::1]", "[2001:db8::1]:8080",
    "agent.internal/halt", "user@agent.internal", "*.agent.internal", "agent internal", "agent.internal;x", "127.0.0.1:80",
])
def test_an_entry_that_the_hostname_can_never_equal_is_counted(monkeypatch, entry):
    assert unusable(monkeypatch, entry)[0] == 1


def test_a_good_entry_beside_bad_ones_is_not_counted_and_duplicates_count_once(monkeypatch):
    count, _ = unusable(monkeypatch, "agent.internal, canary:8090, http://x, canary:8090, [::1]")
    assert count == 3


def test_the_value_on_health_is_a_plain_number_and_never_the_entry_text(monkeypatch):
    count, body = unusable(monkeypatch, f"{MARK}:8090, http://{MARK}")
    assert type(count) is int and count == 2
    assert MARK not in repr(body)


def test_an_entry_with_a_port_does_not_weaken_the_match(tmp_path, monkeypatch):
    """The bad entry never matches, and a good entry beside it still does."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", f"{HOST}:80")
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", f"http://{HOST}/halt")
    result = stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "host_not_allowlisted"
    assert stack.endpoint.calls == []
    assert stack.kill.get("/health").json()["allowlist_entries_unusable"] == 1


def test_a_good_entry_beside_a_bad_one_still_sends_the_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", f"{HOST}:80, {HOST}")
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", f"http://{HOST}/halt")
    result = stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]
    assert result["outcome"] == "called", result
    assert len(stack.endpoint.calls) == 1
    assert stack.kill.get("/health").json()["allowlist_entries_unusable"] == 1


def test_all_bad_entries_still_report_host_not_allowlisted_not_allowlist_unset(tmp_path, monkeypatch):
    """The allowlist IS set (wrongly): the reason stays the truthful one, and /health carries the count."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", f"{HOST}:80")
    stack = Stack(tmp_path)
    stack.with_endpoint("invoicing-agent", f"http://{HOST}/halt")
    assert stack.kill.post("/kill/invoicing-agent", json=OK).json()["endpoint_result"]["reason"] == "host_not_allowlisted"


def test_the_count_is_read_per_call_like_the_allowlist(monkeypatch):
    app = TestClient(create_app())
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "a:1")
    assert app.get("/health").json()["allowlist_entries_unusable"] == 1
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "a")
    assert app.get("/health").json()["allowlist_entries_unusable"] == 0
