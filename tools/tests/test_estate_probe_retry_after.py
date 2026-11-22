"""estate_probe retries a busy answer (503 + Retry-After) inside its --timeout budget (go-live card
B-GL-probe-retry-after). With sealed-ledger PR 1089 a busy ledger answers 503 + Retry-After; pin, continuity,
collateral and health must wait and retry rather than fail on the first 503, bounded by --timeout, and fail
closed (non-zero, no partial pin) once the budget is spent.

Offline: the fake estate is a stdlib server bound to 127.0.0.1 only and stopped after every test; no other
host is contacted. No secret is involved (the fake estate is open)."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import estate_probe as ep  # noqa: E402

N = 3
HASHES = [f"{i:02x}" * 32 for i in range(1, N + 1)]
EVENTS = [{"index": i, "hash": h, "event_type": "agent.registered", "agent_id": "canary-gb10"}
          for i, h in enumerate(HASHES)]


class FakeEstate:
    """A healthy ledger that answers the first `busy` requests to every path 503 (+ Retry-After: `retry_after`)
    and then answers normally. busy=None: busy forever."""

    def __init__(self, busy: int | None, retry_after: str | None = "0", status: int = 503):
        outer = self
        self.hits: dict[str, int] = {}
        self.busy, self.retry_after, self.status = busy, retry_after, status
        self.methods: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def _go(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                path = self.path.split("?")[0]
                outer.hits[path] = outer.hits.get(path, 0) + 1
                outer.methods.append(self.command)
                if outer.busy is None or outer.hits[path] <= outer.busy:
                    self._send(outer.status, {"error": "busy"}, outer.retry_after)
                    return
                if path == "/ledger/health":
                    self._send(200, {"service": "sealed-ledger", "event_count": N, "head_hash": HASHES[-1]})
                elif path == "/ledger/events":
                    self._send(200, EVENTS)
                elif path == "/ledger/verify":
                    self._send(200, {"ok": True, "length": N})
                elif path == "/":
                    self._send(200, {"shell": True})
                else:
                    self._send(404, {})

            def _send(self, status, body, retry_after=None):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                if retry_after is not None and status in (503, 429):
                    self.send_header("Retry-After", retry_after)
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = _go

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def total(self) -> int:
        return sum(self.hits.values())

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake():
    made: list[FakeEstate] = []

    def make(*a, **k):
        f = FakeEstate(*a, **k)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv(ep.TIMEOUT_ENV, raising=False)
    ep.RESULTS.clear()


def _run(argv, capsys):
    try:
        code = ep.main(argv)
    except SystemExit as exc:
        code = exc.code
    ep.RESULTS.clear()
    return code, capsys.readouterr().out


PIN = ("pin",)
CONT = ("continuity", "--count", str(N), "--hash", HASHES[-1][:16])
COLL = ("collateral", "--since", str(N))
HEALTH = ("health", "--only", "ledger")
CMDS = [PIN, CONT, COLL, HEALTH]
IDS = ["pin", "continuity", "collateral", "health"]


# --- retry within the budget ---------------------------------------------------------------------------------


@pytest.mark.parametrize("cmd", CMDS, ids=IDS)
def test_a_busy_ledger_is_retried_until_it_answers(fake, capsys, cmd):
    f = fake(busy=2)
    code, out = _run(["--base", f.base, "--timeout", "20", *cmd], capsys)
    assert code == 0, out
    assert f.hits["/ledger/health"] == 3 or cmd is HEALTH, f.hits   # 2 busy answers, then the real one
    if cmd is PIN:
        assert json.loads(out.strip().splitlines()[-1])["event_count"] == N


def test_retry_after_seconds_is_honoured(fake):
    f = fake(busy=1, retry_after="1")
    t0 = time.monotonic()
    status, _ = ep.Estate(f.base, None, 20).call("GET", "/ledger/health", auth=False)
    elapsed = time.monotonic() - t0
    assert status == 200 and f.hits["/ledger/health"] == 2
    assert 0.9 <= elapsed < 5, elapsed


def test_a_retry_after_larger_than_the_budget_fails_closed_without_sleeping_past_it(fake):
    f = fake(busy=None, retry_after="3600")
    t0 = time.monotonic()
    status, _ = ep.Estate(f.base, None, 2).call("GET", "/ledger/health", auth=False)
    assert status == 503
    assert time.monotonic() - t0 < 2.5
    assert f.hits["/ledger/health"] == 1   # waiting would overrun the budget, so it did not wait or resend


# --- bounded, fail closed -------------------------------------------------------------------------------------


@pytest.mark.parametrize("cmd", CMDS, ids=IDS)
def test_a_ledger_busy_for_the_whole_budget_fails_closed_inside_it(fake, capsys, cmd):
    f = fake(busy=None, retry_after="0")
    t0 = time.monotonic()
    code, out = _run(["--base", f.base, "--timeout", "2", *cmd], capsys)
    elapsed = time.monotonic() - t0
    assert code != 0, out
    assert '"event_count"' not in out, out        # no partial pin
    assert elapsed < 2 * 3 + 2, elapsed             # three ledger reads, each bounded by the 2 s budget
    assert f.total < 200, f.total                   # a Retry-After of 0 is not a hot loop


def test_the_budget_is_the_timeout_not_a_fixed_number_of_tries(fake):
    f = fake(busy=None, retry_after="0")
    ep.Estate(f.base, None, 1).call("GET", "/ledger/health", auth=False)
    few = f.total
    ep.Estate(f.base, None, 3).call("GET", "/ledger/health", auth=False)
    assert f.total - few > few, (few, f.total)


# --- only a busy answer is retried ------------------------------------------------------------------------------


def test_a_503_without_retry_after_is_not_retried(fake):
    f = fake(busy=None, retry_after=None)
    status, _ = ep.Estate(f.base, None, 5).call("GET", "/ledger/health", auth=False)
    assert status == 503 and f.hits["/ledger/health"] == 1


@pytest.mark.parametrize("status", [500, 502, 504, 429])
def test_other_failures_are_not_retried(fake, status):
    f = fake(busy=None, retry_after="0", status=status)
    got, _ = ep.Estate(f.base, None, 5).call("GET", "/ledger/health", auth=False)
    assert got == status and f.hits["/ledger/health"] == 1


@pytest.mark.parametrize("bad", ["", "abc", "-5", "nan", "inf", "Wed, 21 Oct 2015 07:28:00 GMT"])
def test_an_unusable_retry_after_still_retries_boundedly(fake, bad):
    f = fake(busy=1, retry_after=bad)
    t0 = time.monotonic()
    status, _ = ep.Estate(f.base, None, 10).call("GET", "/ledger/health", auth=False)
    assert status == 200 and f.hits["/ledger/health"] == 2
    assert time.monotonic() - t0 < 5


def test_a_write_is_never_resent(fake):
    f = fake(busy=1, retry_after="0")
    status, _ = ep.Estate(f.base, None, 5).call("POST", "/ledger/health", {"x": 1}, auth=False)
    assert status == 503 and f.hits["/ledger/health"] == 1 and f.methods == ["POST"]


def test_a_transport_error_is_not_retried():
    status, body = ep.Estate("http://127.0.0.1:1", None, 5).call("GET", "/ledger/health", auth=False)
    assert status == 0 and "transport_error" in body
