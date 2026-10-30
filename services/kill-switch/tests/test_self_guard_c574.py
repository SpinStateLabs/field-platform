"""C-574 (reviewer C-525 F-C525-1..4): the halt-signal recursion guard sees the path the router sees; the over-block is
pinned; a ledger gap is counted and logged; the outbound client ignores the proxy environment."""

from __future__ import annotations

import logging
import socket
import threading

import pytest

from kill_switch.api import _canonical_path, _is_self_endpoint, new_endpoint_client
from test_endpoint_and_liveness import OP, Stack

ENCODED_SELF_ROUTES = [
    "/%68eartbeat/victim",      # the report's probes, each a route the app serves
    "/heart%62eat/victim",
    "/%6Bill/victim",
    "/%6Civeness",
    "/%68ealth",
    "/%64rill/victim",
    "/%6bill/victim",           # lower-case hex
    "/%2Fkill/victim",          # an encoded slash that decodes to a segment boundary
    "/ok/%6Bill/victim",
]

UNTRUSTWORTHY = [
    "/%256Bill/victim",         # double-encoded: decodes to /%6Bill/victim
    "/a/../kill/victim",
    "/./hooks/halt",
    "/hooks/%2e%2e/kill/victim",
    "/hooks\\kill\\victim",
    "/hooks/%5Ckill",
    "/hooks/halt%00",
    "/hooks/halt%0a",
    "/hooks/%2e",
]


@pytest.mark.parametrize("path", ENCODED_SELF_ROUTES)
def test_an_encoded_self_route_is_skipped_as_self_and_never_called(tmp_path, monkeypatch, path):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "self.host")
    stack = Stack(tmp_path)
    stack.with_endpoint("victim", f"http://self.host{path}")
    result = stack.kill.post("/kill/victim", json=OP).json()["endpoint_result"]
    assert result["outcome"] == "skipped" and result["reason"] == "self_endpoint", result
    assert stack.endpoint.calls == []


@pytest.mark.parametrize("path", UNTRUSTWORTHY)
def test_an_untrustworthy_spelling_is_refused_as_self(path):
    assert _canonical_path(path) is None and _is_self_endpoint(path, "victim") is True


@pytest.mark.parametrize("path,want", [
    ("/hooks/h%61lt", "/hooks/halt"),
    ("//hooks///halt", "/hooks/halt"),
    ("/hooks/halt/", "/hooks/halt/"),
    ("/", "/"),
    ("", "/"),
    ("/%7Eagent/halt", "/~agent/halt"),
])
def test_the_canonical_path_is_decoded_once_and_collapsed(path, want):
    assert _canonical_path(path) == want


def test_a_harmless_encoded_endpoint_is_still_called(tmp_path, monkeypatch):
    """The guard is not a ban on percent-encoding: the decoded path names no self route."""
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "agent.host")
    stack = Stack(tmp_path)
    stack.with_endpoint("victim", "http://agent.host/hooks/h%61lt")
    result = stack.kill.post("/kill/victim", json=OP).json()["endpoint_result"]
    assert result["outcome"] == "called", result
    assert len(stack.endpoint.calls) == 1


@pytest.mark.parametrize("path", ["/kill", "/v1/kill", "/api/health", "/v1/liveness", "/x/heartbeat/y", "/drill/z"])
def test_the_guard_is_by_path_alone_so_these_are_refused_on_any_host(path):
    """F-C525-2, pinned as the decision: a reverse proxy can mount this service under any prefix on any host, so a
    path that holds a self shape is refused whatever the host. The price is that an agent whose own endpoint is
    `/v1/kill` or `/api/health` gets no halt signal (it is reported skipped, self_endpoint, never silently)."""
    assert _is_self_endpoint(path, "victim") is True


@pytest.mark.parametrize("path", ["/hooks/halt", "/killswitchy", "/api/stop", "/healthy", "/liveness-probe"])
def test_other_paths_are_not_self(path):
    assert _is_self_endpoint(path, "victim") is False


class _BoomLedger:
    def append(self, *a, **k):
        raise RuntimeError("secret-token-123 http://user:pw@ledger.internal/x")


def test_a_failed_ledger_write_is_counted_and_logged_without_its_message(tmp_path, caplog):
    stack = Stack(tmp_path)
    stack.register("victim")
    assert stack.kill.get("/health").json()["ledger_note_failures"] == 0
    stack.kill.app.state.ledger = _BoomLedger()
    with caplog.at_level(logging.WARNING, logger="kill_switch.api"):
        r = stack.kill.post("/kill/victim", json=OP)
    assert r.status_code == 200                                  # act-first: the kill still happened
    assert stack.registry.get("/agents/victim").json()["status"] == "killed"
    assert stack.kill.get("/health").json()["ledger_note_failures"] >= 1
    assert "ledger record not written" in caplog.text and "RuntimeError" in caplog.text
    assert "secret-token" not in caplog.text and "ledger.internal" not in caplog.text


def test_the_outbound_client_ignores_the_proxy_environment(monkeypatch):
    """F-C525-4: a proxy variable naming a local listener gets zero connections."""
    hits = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(0.2)
    port = listener.getsockname()[1]

    def accept_loop():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            hits.append(1)
            conn.close()

    stop = threading.Event()
    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    for var in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(var, f"http://127.0.0.1:{port}")
    client = new_endpoint_client()
    try:
        with pytest.raises(Exception):
            client.get("http://agent-endpoint.invalid/halt", timeout=2)
    finally:
        client.close()
        stop.set()
        t.join(1)
        listener.close()
    assert hits == []
