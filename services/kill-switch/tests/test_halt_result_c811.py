"""C-811 (reviewer C-745 F-C745-1..4): a redirect is not a delivered halt signal, the gap counter's unit is stated and
its increment is locked, and the client's no-redirect setting is pinned against a real redirect."""

from __future__ import annotations

import http.server
import threading

import pytest

from kill_switch.api import new_endpoint_client
from test_endpoint_and_liveness import ALLOWED, OP, Stack


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 399])
def test_a_redirect_answer_is_a_failed_signal_not_a_delivered_one(tmp_path, monkeypatch, status):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack = Stack(tmp_path)
    stack.endpoint._handler = lambda m, u: status
    stack.with_endpoint("victim", f"http://{ALLOWED}/hooks/halt")
    r = stack.kill.post("/kill/victim", json=OP)
    assert r.status_code == 200                                       # the kill itself still happened
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "failed" and result["reason"] == "http_redirect", result
    assert result["http_status"] == status
    assert len(stack.events("kill.endpoint_failed")) == 1 and not stack.events("kill.endpoint_called")


@pytest.mark.parametrize("status,outcome,reason", [
    (200, "called", None), (204, "called", None), (299, "called", None),
    (400, "failed", "http_error"), (404, "failed", "http_error"), (503, "failed", "http_error"),
])
def test_the_other_statuses_keep_their_classification(tmp_path, monkeypatch, status, outcome, reason):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", ALLOWED)
    stack = Stack(tmp_path)
    stack.endpoint._handler = lambda m, u: status
    stack.with_endpoint("victim", f"http://{ALLOWED}/hooks/halt")
    result = stack.kill.post("/kill/victim", json=OP).json()["endpoint_result"]
    assert result["outcome"] == outcome and result["reason"] == reason, result


def test_the_readme_states_the_counters_unit_and_scope():
    """C-811 F-C745-2: notes, not actions; per process; zero after a restart. A pinned wording."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    for phrase in ("failed ledger RECORDS (notes), not failed actions", "per PROCESS", "zero after a restart"):
        assert phrase in flat, phrase


def test_the_gap_counter_loses_no_increment_under_contention():
    """C-811 F-C745-3: many threads add at once with the interpreter forced to switch as often as it can."""
    import sys
    import threading

    from kill_switch.api import _GapCounter

    counter = _GapCounter()
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        def work():
            for _ in range(2000):
                counter.add()

        threads = [threading.Thread(target=work) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert counter.value == 16 * 2000


def test_the_counter_is_the_locked_one_and_health_reads_it(tmp_path):
    from kill_switch.api import _GapCounter

    stack = Stack(tmp_path)
    assert isinstance(stack.kill.app.state.ledger_note_failures, _GapCounter)
    assert stack.kill.get("/health").json()["ledger_note_failures"] == 0


class _RedirectingServer(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_POST(self):                                     # noqa: N802 - http.server's name
        type(self).hits.append(self.path)
        if self.path == "/final":
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/final")
        self.end_headers()

    do_GET = do_POST

    def log_message(self, *args):
        pass


def test_the_halt_client_does_not_follow_a_real_redirect():
    """C-811 F-C745-4: pins the no-redirect behaviour against a real listener, so it holds whether the setting is
    explicit or a library default (the reviewer's survivor removed the explicit argument and changed nothing)."""
    _RedirectingServer.hits = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RedirectingServer)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    client = new_endpoint_client()
    try:
        resp = client.request("POST", f"http://127.0.0.1:{server.server_address[1]}/hooks/halt")
    finally:
        client.close()
        server.shutdown()
        server.server_close()
    assert resp.status_code == 302                          # returned, not followed
    assert _RedirectingServer.hits == ["/hooks/halt"]       # the redirect target was never requested


def test_the_counter_takes_its_lock_for_every_add():
    """The contention test above can pass on a build whose interpreter lock hides the race; this one pins the lock."""
    from kill_switch.api import _GapCounter

    class SpyLock:
        entered = 0

        def __enter__(self):
            type(self).entered += 1

        def __exit__(self, *exc):
            return False

    counter = _GapCounter()
    counter._lock = SpyLock()
    for _ in range(5):
        counter.add()
    assert SpyLock.entered == 5                      # one acquisition per add
    assert counter.value == 5
