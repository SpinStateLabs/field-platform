"""B-PR1098-PERCALL-SIGNAL: phase_g_check's 503 retry and Estate.call's own Retry-After retry (the
probe-retry-after change) must not nest. A 503 WITH Retry-After costs at most 4 requests (never
4 x 4 = 16); a 503 WITHOUT Retry-After still gets this module's 1/2/4 s ladder; 200 is one request;
other errors are not retried. The REAL ep.Estate is used against a loopback fake server (127.0.0.1,
stopped after each test); waits run on a fake clock, nothing really sleeps."""

from __future__ import annotations

import http.server
import json
import sys
import threading
import types
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import estate_probe as ep  # noqa: E402
import phase_g_check as pgc  # noqa: E402


class _Clock:
    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class _Fake:
    """Loopback server: `script` items are (status, retry_after|None); the last item repeats."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def _serve(self):
                outer.requests.append(self.command)
                status, ra = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                body = json.dumps([{"ok": 1}] if status == 200 else {"detail": "busy"}).encode()
                self.send_response(status)
                if ra is not None:
                    self.send_header("Retry-After", str(ra))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _serve

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(5)


@pytest.fixture
def rig(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(pgc, "_sleep", clock.sleep)
    monkeypatch.setattr(pgc, "_clock", clock.now)
    monkeypatch.setattr(ep, "time", types.SimpleNamespace(monotonic=clock.now, sleep=clock.sleep))
    monkeypatch.setattr(ep, "RESULTS", [])
    servers = []

    def make(script):
        fake = _Fake(script)
        servers.append(fake)
        return pgc._make_estate(fake.base, None), fake

    yield make, clock
    for s in servers:
        s.stop()


@pytest.mark.parametrize("ra", [0, 1, 5])
def test_a_503_with_retry_after_costs_at_most_four_requests(rig, ra):
    make, clock = rig
    estate, fake = make([(503, ra)])
    assert estate.call("GET", "/ledger/events")[0] == 503      # fail closed
    assert len(fake.requests) <= 4                             # was 16 when both layers retried
    assert len(fake.requests) == 4                             # and the retry still happens: 1 + 3


def test_a_503_with_retry_after_is_retried_by_exactly_one_layer(rig):
    make, clock = rig
    estate, fake = make([(503, 0), (503, 0), (200, None)])
    assert estate.call("GET", "/ledger/events") == (200, [{"ok": 1}])
    assert len(fake.requests) == 3


def test_a_503_without_retry_after_gets_the_ladder(rig):
    make, clock = rig
    estate, fake = make([(503, None)])
    assert estate.call("GET", "/ledger/events")[0] == 503
    assert len(fake.requests) == 4 and clock.sleeps == [1.0, 2.0, 4.0]


def test_a_bare_503_then_200_is_retried_once(rig):
    make, clock = rig
    estate, fake = make([(503, None), (200, None)])
    assert estate.call("GET", "/ledger/events")[0] == 200
    assert len(fake.requests) == 2 and clock.sleeps == [1.0]


def test_200_is_one_request(rig):
    make, clock = rig
    estate, fake = make([(200, None)])
    assert estate.call("GET", "/ledger/events") == (200, [{"ok": 1}])
    assert len(fake.requests) == 1 and clock.sleeps == []


@pytest.mark.parametrize("status", [500, 502, 504, 404, 429])
def test_non_503_errors_are_not_retried(rig, status):
    make, clock = rig
    estate, fake = make([(status, 0)])
    assert estate.call("GET", "/ledger/events")[0] == status
    assert len(fake.requests) == 1 and clock.sleeps == []


def test_a_write_answered_503_is_never_retried(rig):
    make, clock = rig
    estate, fake = make([(503, 0)])
    assert estate.call("POST", "/killswitch/kill/x", {})[0] == 503
    assert len(fake.requests) == 1


def test_the_cap_holds_over_repeated_calls(rig):
    make, clock = rig
    estate, fake = make([(503, 0)])
    for _ in range(3):
        del fake.requests[:]
        assert estate.call("GET", "/ledger/events")[0] == 503
        assert len(fake.requests) == 4


def test_the_process_wide_estate_marker_does_not_switch_this_layer_off(rig, monkeypatch):
    """The marker on Estate.call is process-wide state, not a per-call signal: with it set, a bare
    503 must still be retried by this module's ladder."""
    monkeypatch.setattr(ep.Estate.call, "_retries_503", True, raising=False)
    make, clock = rig
    estate, fake = make([(503, None)])
    assert estate.call("GET", "/ledger/events")[0] == 503
    assert len(fake.requests) == 4
