"""Phase G S8 (design 9.5 "canary.py"): ``x3-check`` presents the kill-switch
container's own operator identity on the guarded kill-switch calls.

``x3-check`` runs inside the kill-switch container (design D-K: X3 runs under
``svc-killswitch``, which holds ``drill``). Before this change ``urllib_call``
built its headers by hand (Accept, Content-Type, ``x-field-auth``) and never
read ``FIELD_OPERATOR`` / ``FIELD_OPERATOR_KEY``, so under REQUIRE every X3
kill, revive and drill was a 401 that no environment setting could fix.

What is pinned here, over a real socket (a recording HTTP server):

* ``urllib_call(..., operator=True)`` adds ``operator_headers()`` read at call
  time (a rotated key is sent on the next call); nothing when no identity is
  configured; never when ``operator`` is false (the default);
* ``main(["x3-check", ...])`` sends the pair ONLY on the guarded kill-switch
  POSTs (``/kill/``, ``/revive/``, ``/drill/``): never on reads, never to the
  registry or ledger, never to the canary (which gets no perimeter secret
  either, as before).

Keys are generated per run and never printed; assertions compare fingerprints.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from field_agent import canary as canary_mod
from field_core import operator_auth as oa

OP, KEY_HDR, AUTH = oa.HEADER_OPERATOR, oa.HEADER_KEY, "x-field-auth"


def _fp(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:8]


@pytest.fixture()
def server():
    seen: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _answer(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(n)
            seen.append({"method": self.command, "path": self.path,
                         "headers": {k.lower(): v for k, v in self.headers.items()}})
            raw = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = _answer

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", seen
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_OPERATOR_KEY_FILE", oa.ENV_REGISTRY,
              oa.ENV_REQUIRE, "FIELD_SHARED_SECRET", "FIELD_KILLSWITCH_URL", "FIELD_REGISTRY_URL",
              "FIELD_LEDGER_URL"):
        monkeypatch.delenv(n, raising=False)


def _identity(monkeypatch, op: str, key: str) -> None:
    monkeypatch.setenv(oa.ENV_OPERATOR, op)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, key)


def _pair(rec: dict) -> tuple[str | None, str | None]:
    return rec["headers"].get(OP), _fp(rec["headers"].get(KEY_HDR))


def test_operator_true_sends_the_configured_identity_read_at_call_time(server, monkeypatch):
    base, seen = server
    k1, k2 = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    _identity(monkeypatch, "svc-killswitch", k1)
    status, _ = canary_mod.urllib_call("POST", f"{base}/killswitch/kill/canary-gb10", {"reason": "x3-1"},
                                       secret="perimeter", operator=True)
    assert status == 200
    assert _pair(seen[-1]) == ("svc-killswitch", _fp(k1))
    assert seen[-1]["headers"].get(AUTH) == "perimeter"
    _identity(monkeypatch, "svc-killswitch", k2)          # rotated in the same process
    canary_mod.urllib_call("POST", f"{base}/killswitch/revive/canary-gb10", {"reason": "x3-1"},
                           secret="perimeter", operator=True)
    assert _pair(seen[-1]) == ("svc-killswitch", _fp(k2))


def test_operator_true_without_an_identity_sends_none_and_still_calls(server):
    base, seen = server
    status, body = canary_mod.urllib_call("POST", f"{base}/killswitch/drill/canary-gb10", {}, operator=True)
    assert status == 200 and body == {"ok": True}
    assert _pair(seen[-1]) == (None, None)


def test_the_default_never_sends_an_identity(server, monkeypatch):
    base, seen = server
    _identity(monkeypatch, "svc-killswitch", secrets.token_urlsafe(24))
    canary_mod.urllib_call("GET", f"{base}/canary/status")
    canary_mod.urllib_call("POST", f"{base}/killswitch/kill/canary-gb10", {}, secret="perimeter")
    assert [_pair(r) for r in seen] == [(None, None), (None, None)]


@pytest.mark.parametrize("method,url,want", [
    ("POST", "/killswitch/kill/canary-gb10", True),
    ("POST", "/killswitch/kill/domain/canary", True),
    ("POST", "/killswitch/revive/canary-gb10", True),
    ("POST", "/killswitch/drill/canary-gb10", True),
    ("GET", "/killswitch/heartbeat/canary-gb10", False),
    ("POST", "/killswitch/heartbeat/canary-gb10", False),
    ("GET", "/killswitch/kill/canary-gb10", False),
    ("POST", "/registry/agents/canary-gb10", False),
    ("POST", "/killswitchx/kill/canary-gb10", False),
    ("POST", "/ledger/events", False),
])
def test_the_guarded_allowlist(method, url, want):
    assert canary_mod.is_guarded_killswitch_call(method, "http://h" + url, "http://h/killswitch") is want


@pytest.mark.parametrize("url", [
    "http://registry:8001/kill/canary-gb10",          # same length as the base below, other host
    "http://other-host:8005/kill/canary-gb10",
    "http://kswitch:8006/kill/canary-gb10",           # the right name on another port
    "https://kswitch:8005/kill/canary-gb10",          # another scheme
    "http://kswitch:8005.evil/kill/canary-gb10",      # the base as a prefix of a longer host
])
def test_the_guarded_allowlist_checks_the_host_not_only_the_path(url):
    """C-98 (reviewer C-91 F-C91-2, mutant G2): the check that the URL starts with the kill-switch
    base must hold. Without it the code slices ``url[len(base):]`` of ANY URL, so a POST to another
    host whose path lines up as ``/kill/...`` after that slice would carry the operator pair."""
    assert canary_mod.is_guarded_killswitch_call("POST", url, "http://kswitch:8005") is False
    assert canary_mod.is_guarded_killswitch_call("POST", "http://kswitch:8005/kill/canary-gb10",
                                                 "http://kswitch:8005") is True


def test_x3_check_entry_point_sends_the_pair_only_on_guarded_killswitch_posts(server, monkeypatch):
    base, seen = server
    key = secrets.token_urlsafe(24)
    _identity(monkeypatch, "svc-killswitch", key)
    monkeypatch.setenv("FIELD_SHARED_SECRET", "perimeter")
    monkeypatch.setenv("FIELD_KILLSWITCH_URL", f"{base}/killswitch/")
    monkeypatch.setenv("FIELD_REGISTRY_URL", f"{base}/registry")
    monkeypatch.setenv("FIELD_LEDGER_URL", f"{base}/ledger")

    def fake_x3_check(agent, *, killswitch_url, registry_url, ledger_url, canary_url, platform, canary, **kw):
        # every call shape the real x3_check makes, through the callables main() built
        platform("GET", f"{registry_url}/agents/{agent}")
        platform("GET", f"{ledger_url}/events?event_type=kill.revive")
        platform("POST", f"{killswitch_url}/kill/{agent}", {"reason": "x3-n"})
        platform("POST", f"{killswitch_url}/revive/{agent}", {"reason": "x3-n revive"})
        platform("GET", f"{killswitch_url}/heartbeat/{agent}")
        platform("POST", f"{killswitch_url}/drill/{agent}", {"reason": "x3-d"})
        canary("GET", f"{canary_url}/status")
        return 0

    monkeypatch.setattr(canary_mod, "x3_check", fake_x3_check)
    assert canary_mod.main(["x3-check", "--agent", "canary-gb10", "--canary-url", f"{base}/canary"]) == 0

    carried = {(r["method"], r["path"]): _pair(r) for r in seen}
    with_pair = sorted(k for k, v in carried.items() if v != (None, None))
    assert with_pair == [("POST", "/killswitch/drill/canary-gb10"), ("POST", "/killswitch/kill/canary-gb10"),
                         ("POST", "/killswitch/revive/canary-gb10")]
    assert all(v == ("svc-killswitch", _fp(key)) for k, v in carried.items() if k in with_pair)
    canary_calls = [r for r in seen if r["path"].startswith("/canary/")]
    assert canary_calls and all(AUTH not in r["headers"] and OP not in r["headers"]
                                and KEY_HDR not in r["headers"] for r in canary_calls)
    platform_calls = [r for r in seen if not r["path"].startswith("/canary/")]
    assert len(platform_calls) == 6 and all(r["headers"].get(AUTH) == "perimeter" for r in platform_calls)
