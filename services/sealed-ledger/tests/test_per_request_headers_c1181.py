"""C-1181 (Lane 7 C-1150 F2, slice C): the sealed-ledger CLI and witness put the operator pair only on a guarded write.

Before this change the CLI client and the witness's local-ledger client carried ``auth_headers()`` as DEFAULT headers, so the
env operator pair rode every request, ``GET /retention/check`` and ``GET /health`` included. Now the CLI asks field-core's
``request_headers`` per request and the witness client attaches the pair with ``GuardedOperatorAuth`` (only ``POST /events``
among its calls). Values are made up; a MockTransport answers every request.
"""
from __future__ import annotations

import httpx
import pytest

from field_core import authn
from field_core import operator_auth as oa
from sealed_ledger import cli, witness

SECRET = "made-up-perimeter-secret"
OP, KEY = "made-up-operator", "fok_made-up-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)
    monkeypatch.setenv(oa.ENV_OPERATOR, OP)
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, KEY)


def _pair(headers) -> bool:
    return oa.HEADER_OPERATOR in headers or oa.HEADER_KEY in headers


@pytest.fixture()
def served(monkeypatch):
    """Every request the CLI client sends, as the transport saw it (the real Client with a MockTransport)."""
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"ok": True})
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    return seen


@pytest.mark.parametrize("method,route,guarded", [
    ("POST", "/rotate", True),
    ("POST", "/hold", True),
    ("POST", "/hold/release", True),
    ("POST", "/retention/apply", True),
    ("GET", "/retention/check", False),
])
@pytest.mark.parametrize("base", ["http://ledger.invalid", "http://ledger.invalid/ledger"])
def test_the_cli_pair_rides_only_a_guarded_route(served, method, route, guarded, base):
    cli._call_served(base, method, route, {"by": "x"} if method == "POST" else None)
    assert len(served) == 1, served
    h = served[0].headers
    assert h.get(authn.HEADER) == SECRET                                       # the perimeter secret always
    assert _pair(h) is guarded, (method, route, base, sorted(h))               # the pair only on a guarded write
    if guarded:
        assert h[oa.HEADER_OPERATOR] == OP and h[oa.HEADER_KEY] == KEY


def test_the_witness_local_client_sends_the_pair_on_the_event_write_and_not_on_the_health_read():
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={})
    client = witness.build_ledger_client("http://ledger.invalid", transport=httpx.MockTransport(handler))
    client.post("events", json={"event_type": "x"})
    client.get("health")
    by = {(r.method, r.url.path): r.headers for r in seen}
    assert set(by) == {("POST", "/events"), ("GET", "/health")}, sorted(by)
    for headers in by.values():
        assert headers.get(authn.HEADER) == SECRET
    assert by[("POST", "/events")][oa.HEADER_OPERATOR] == OP and by[("POST", "/events")][oa.HEADER_KEY] == KEY
    assert not _pair(by[("GET", "/health")])


def test_the_witness_local_client_with_no_pair_in_the_env_sends_the_secret_alone(monkeypatch):
    monkeypatch.delenv(oa.ENV_OPERATOR)
    monkeypatch.delenv(oa.ENV_OPERATOR_KEY)
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={})
    client = witness.build_ledger_client("http://ledger.invalid", transport=httpx.MockTransport(handler))
    client.post("events", json={})
    assert len(seen) == 1 and seen[0].headers.get(authn.HEADER) == SECRET and not _pair(seen[0].headers)
