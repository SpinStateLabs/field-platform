"""estate_probe --timeout / FIELD_PROBE_TIMEOUT (T5, 2026-11-20).

Whole-ledger routes on the Fly estate take 5-18 s against estate_probe's fixed 20 s client timeout, so pin,
collateral and health failed intermittently. The timeout is now a flag with an env default; 20 s stays the
default; a request that outlasts it still fails closed. These run the probe against the real harness estate
of test_estate_probe, behind a proxy that holds every answer for a fixed time (the slow route), so a timeout
below that time fails and one above passes, on the same estate.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import estate_probe as ep  # noqa: E402

from test_estate_probe import _open_estate, _run, estate  # noqa: E402,F401

DELAY = 1.5   # seconds every proxied answer is held
SHORT = "0.5"  # below DELAY: every request times out
LONG = "15"    # far above DELAY


class SlowProxy:
    """Forwards every request to the estate after holding it DELAY seconds; the answer (status and body) is the
    estate's own, so only the time differs from talking to the estate directly."""

    def __init__(self, upstream: str, delay: float):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _go(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else None
                time.sleep(delay)
                outer.requests += 1
                req = urllib.request.Request(upstream + self.path, data=body, method=self.command,
                                             headers={k: v for k, v in self.headers.items()
                                                      if k.lower() not in ("host", "content-length")})
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        raw, status = resp.read(), resp.status
                except urllib.error.HTTPError as exc:
                    raw, status = exc.read(), exc.code
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:  # the probe gave up and closed the socket
                    pass

            do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _go

            def log_message(self, *a):
                pass

        self.requests = 0
        self.upstream = upstream
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def slow(estate):
    p = SlowProxy(estate.base, DELAY)
    try:
        yield p
    finally:
        p.close()


def _probe(slow: SlowProxy, *rest: str) -> tuple[int, str]:
    return _run(["--base", slow.base, *rest])


# --- the default ------------------------------------------------------------------------------------------


def test_the_default_timeout_is_still_20_seconds(monkeypatch):
    monkeypatch.delenv("FIELD_PROBE_TIMEOUT", raising=False)
    assert ep.DEFAULT_TIMEOUT == 20.0
    assert ep.probe_timeout(None) == 20.0
    assert ep.Estate("http://127.0.0.1:1", None).timeout == 20.0


# --- the flag reaches the three subcommands that failed on Fly -----------------------------------------------


@pytest.mark.parametrize("cmd", [("pin",), ("collateral", "--since", "@END"), ("health", "--only", "ledger")])
def test_a_raised_timeout_passes_a_slow_route_where_a_short_one_fails_closed(slow, cmd):
    if "@END" in cmd:  # the real flow: collateral from the pinned end of the ledger (since 0 sees setup events)
        end = json.loads(_run(["--base", slow.upstream, "pin"])[1].strip().splitlines()[-1])["event_count"]
        cmd = tuple(str(end) if c == "@END" else c for c in cmd)
    code, out = _probe(slow, "--timeout", SHORT, *cmd)
    assert code != 0, out
    if cmd[0] == "pin":
        assert not out.strip().startswith("{") and '"event_count"' not in out, out  # no partial pin
    before = slow.requests
    code, out = _probe(slow, "--timeout", LONG, *cmd)
    assert code == 0, out
    assert slow.requests > before, "the probe never reached the estate through the proxy"


def test_the_env_default_applies_and_the_flag_overrides_it(slow, monkeypatch):
    monkeypatch.setenv("FIELD_PROBE_TIMEOUT", SHORT)
    code, out = _probe(slow, "pin")
    assert code != 0, out
    code, out = _probe(slow, "--timeout", LONG, "pin")
    assert code == 0, out
    monkeypatch.setenv("FIELD_PROBE_TIMEOUT", LONG)
    code, out = _probe(slow, "pin")
    assert code == 0, out
    code, out = _probe(slow, "--timeout", SHORT, "pin")
    assert code != 0, out


def test_a_timeout_still_fails_closed_with_no_partial_pin(slow):
    code, out = _probe(slow, "--timeout", SHORT, "pin")
    assert code != 0
    assert '"event_count"' not in out


# --- a bad value is refused, never turned into "no timeout" -----------------------------------------------------


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "abc", "", "1e9", "3601"])
def test_a_bad_timeout_flag_is_refused_before_anything_is_sent(bad):
    code, out = _run(["--base", "http://127.0.0.1:1", "--timeout", bad, "pin"])
    assert code == 2, out
    assert "timeout" in out


@pytest.mark.parametrize("bad", ["0", "-5", "nan", "inf", "abc", "1e9"])
def test_a_bad_env_timeout_is_refused(monkeypatch, bad):
    monkeypatch.setenv("FIELD_PROBE_TIMEOUT", bad)
    code, out = _run(["--base", "http://127.0.0.1:1", "pin"])
    assert code == 2, out
    assert "FIELD_PROBE_TIMEOUT" in out


def test_an_empty_env_timeout_means_the_default(monkeypatch):
    monkeypatch.setenv("FIELD_PROBE_TIMEOUT", "")
    assert ep.probe_timeout(None) == 20.0


# --- 180 / 600 reach every request of health, including the authenticated attest pack ------------------------------


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return b"{}"


class _RecordingOpener:
    def __init__(self):
        self.calls: list[tuple[str, str, float, bool]] = []

    def open(self, req, timeout=None):
        self.calls.append((req.get_method(), urllib.parse.urlsplit(req.full_url).path, timeout,
                           req.get_header("X-field-auth") is not None))
        return _Resp()


@pytest.mark.parametrize("value", ["180", "600"])
def test_the_timeout_reaches_every_request_of_health_including_the_authenticated_attest_pack(
        monkeypatch, tmp_path, value):
    rec = _RecordingOpener()
    monkeypatch.setattr(ep, "_OPENER", rec)
    secret = tmp_path / "perimeter.secret"
    secret.write_text("test-only-secret-value-0000\n")
    _run(["--base", "http://127.0.0.1:1", "--secret-file", str(secret), "--timeout", value, "health"])
    assert len(rec.calls) > 10, rec.calls
    assert {t for _, _, t, _ in rec.calls} == {float(value)}, rec.calls
    attest = [c for c in rec.calls if c[0] == "GET" and c[1] == "/attest/pack"]
    assert attest and all(auth for *_, auth in attest), "the authenticated GET /attest/pack was not sent with the secret"


def test_the_timeout_applies_per_request_not_per_command(monkeypatch):
    rec = _RecordingOpener()
    monkeypatch.setattr(ep, "_OPENER", rec)
    e = ep.Estate("http://127.0.0.1:1", None, 180.0)
    for _ in range(3):
        e.call("GET", "/ledger/events")
    assert [t for _, _, t, _ in rec.calls] == [180.0, 180.0, 180.0]
