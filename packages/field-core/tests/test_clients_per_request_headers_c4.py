"""Phase G C-4: ``RegistryClient`` and ``LedgerClient`` build their auth headers
per request, never once at construction.

Why it matters (design RT2-2, RT2-5): the kill-switch's ``RegistryClient`` is
the S1 hop (kill-switch -> registry ``PATCH /agents/{id}``). When its headers
were captured at construction, a rotated or revoked ``svc-killswitch`` key only
took effect after a kill-switch restart; until then every kill, revive and
drill went out under the stale key. Each test here drives the client's own
internally built ``httpx.Client`` (only its transport is replaced, so the
requests are recorded instead of sent) and changes the environment between two
calls on the SAME client object.

Keys are generated per test run and never printed; only header presence and
equality are asserted.
"""

from __future__ import annotations

import hashlib
import json
import secrets

import httpx
import pytest

import field_core.clients as clients
from field_core import operator_auth as oa
from field_core.authn import ENV_VAR as SECRET_ENV, HEADER as SECRET_HEADER
from field_core.clients import LedgerClient, RegistryClient

AGENT = {"agent_id": "agent-a1", "status": "active", "domain": "canary"}


@pytest.fixture()
def wire(monkeypatch):
    """Every ``httpx.Client`` built from here on keeps the arguments its caller
    chose but talks to a recording transport. Returns the list of requests."""
    for name in (oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_OPERATOR_KEY_FILE",
                 oa.ENV_REGISTRY, oa.ENV_REQUIRE, SECRET_ENV,
                 clients.CALLER_ID_ENV, clients.CALLER_KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if request.method == "POST" and path.endswith("/events"):
            return httpx.Response(201, json={"event_id": "e1", "hash": "h"})
        if path.endswith("/events"):
            return httpx.Response(200, json=[])
        if path.endswith("/retention/check"):
            return httpx.Response(200, json={"ok": True, "status": "ok"})
        if path.endswith("/agents"):
            return httpx.Response(200, json=[AGENT])
        return httpx.Response(200, json=AGENT)

    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return seen


def _identity(monkeypatch, operator: str | None, key: str | None) -> None:
    for name, value in ((oa.ENV_OPERATOR, operator), (oa.ENV_OPERATOR_KEY, key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def _fp(key: str | None) -> str | None:
    """Fingerprint only: a failing assertion prints this, never a key."""
    return None if key is None else hashlib.sha256(key.encode()).hexdigest()[:8]


def _pair(request: httpx.Request) -> tuple[str | None, str | None]:
    """(operator id, key fingerprint) as sent on the wire."""
    return request.headers.get(oa.HEADER_OPERATOR), _fp(request.headers.get(oa.HEADER_KEY))


def test_registry_client_sends_the_current_key_on_every_call_without_a_restart(wire, monkeypatch):
    k1, k2 = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    _identity(monkeypatch, "svc-killswitch", k1)
    reg = RegistryClient(base_url="http://registry.test")   # built ONCE, like the kill-switch's

    reg.set_status("agent-a1", "killed")
    assert _pair(wire[-1]) == ("svc-killswitch", _fp(k1))

    _identity(monkeypatch, "svc-killswitch", k2)             # rotation: new key, same process
    reg.set_status("agent-a1", "active")
    assert _pair(wire[-1]) == ("svc-killswitch", _fp(k2))
    reg.get_agent("agent-a1")                             # C-511: a READ carries no operator pair
    assert _pair(wire[-1]) == (None, None)

    _identity(monkeypatch, "svc-killswitch-2", k1)           # sibling-id rotation (design 2.6)
    reg.set_status("agent-a1", "killed")
    assert _pair(wire[-1]) == ("svc-killswitch-2", _fp(k1))
    reg.list_agents(domain="canary")
    assert _pair(wire[-1]) == (None, None)


def test_registry_client_stops_sending_an_identity_the_environment_no_longer_has(wire, monkeypatch):
    _identity(monkeypatch, "svc-killswitch", secrets.token_urlsafe(24))
    reg = RegistryClient(base_url="http://registry.test")
    reg.set_status("agent-a1", "active")
    assert _pair(wire[-1])[0] == "svc-killswitch"
    _identity(monkeypatch, None, None)
    reg.set_status("agent-a1", "killed")
    assert _pair(wire[-1]) == (None, None)


def test_ledger_client_sends_the_current_key_on_every_call_without_a_restart(wire, monkeypatch):
    k1, k2 = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    _identity(monkeypatch, "svc-registry", k1)
    led = LedgerClient(base_url="http://ledger.test", caller=None)
    monkeypatch.setattr(led, "_caller", None)               # unsigned appends: headers are the subject

    led.append("probe.note", {"n": 1})
    assert _pair(wire[-1]) == ("svc-registry", _fp(k1))
    _identity(monkeypatch, "svc-registry", k2)
    led.append("probe.note", {"n": 2})
    assert _pair(wire[-1]) == ("svc-registry", _fp(k2))
    led.events("probe.note")                                 # C-511: reads carry no operator pair
    assert _pair(wire[-1]) == (None, None)
    led.retention_check()
    assert _pair(wire[-1]) == (None, None)
    assert [json.loads(r.content)["payload"]["n"] for r in wire if r.method == "POST"] == [1, 2]


@pytest.mark.parametrize("make", [
    lambda: RegistryClient(base_url="http://registry.test"),
    lambda: LedgerClient(base_url="http://ledger.test", caller=None),
])
def test_the_shared_secret_header_is_kept_and_also_read_per_request(wire, monkeypatch, make):
    client = make()
    call = (lambda: client.get_agent("agent-a1")) if isinstance(client, RegistryClient) \
        else (lambda: client.events())

    call()                                                   # secret unset: no header, as before
    assert SECRET_HEADER not in wire[-1].headers
    s1, s2 = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    monkeypatch.setenv(SECRET_ENV, s1)
    call()
    assert _fp(wire[-1].headers.get(SECRET_HEADER)) == _fp(s1)
    assert _pair(wire[-1]) == (None, None)                   # no identity configured: none sent
    monkeypatch.setenv(SECRET_ENV, s2)
    call()
    assert _fp(wire[-1].headers.get(SECRET_HEADER)) == _fp(s2)


@pytest.mark.parametrize("make", [
    lambda: RegistryClient(base_url="http://registry.test"),
    lambda: LedgerClient(base_url="http://ledger.test", caller=None),
])
def test_the_internal_http_client_holds_no_fixed_auth_headers(wire, monkeypatch, make):
    _identity(monkeypatch, "svc-x", secrets.token_urlsafe(24))
    monkeypatch.setenv(SECRET_ENV, secrets.token_urlsafe(16))
    held = {k.lower() for k in make()._client.headers}
    assert not held & {oa.HEADER_OPERATOR, oa.HEADER_KEY, SECRET_HEADER}


def test_a_key_source_read_at_call_time_is_honoured_on_the_next_request(wire, monkeypatch, tmp_path):
    """Whatever ``operator_headers()`` returns at call time is what goes out.
    The file reader below is a stand-in for a key-file source (C-1, another
    change); it only shows the client asks again on every request."""
    key_file = tmp_path / "svc-killswitch.key"
    key_file.write_text(secrets.token_urlsafe(24) + "\n", encoding="utf-8")
    monkeypatch.setattr(oa, "operator_headers", lambda: {
        oa.HEADER_OPERATOR: "svc-killswitch", oa.HEADER_KEY: key_file.read_text(encoding="utf-8").strip()})
    reg = RegistryClient(base_url="http://registry.test")
    reg.set_status("agent-a1", "killed")
    first = _pair(wire[-1])[1]
    key_file.write_text(secrets.token_urlsafe(24) + "\n", encoding="utf-8")   # rotated in place
    reg.set_status("agent-a1", "active")
    second = _pair(wire[-1])[1]
    assert first and second and first != second
    assert second == _fp(key_file.read_text(encoding="utf-8").strip())


class _Bare:
    """An injected client with the pre-C-4 call shapes: no ``headers`` kwarg."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def _resp(self, code, body):
        class R:
            status_code, text = code, ""

            def json(self):
                return body
        return R()

    def get(self, url, params=None):
        self.calls.append(("GET", url, {"params": params}))
        return self._resp(200, [AGENT] if url.endswith("/agents") or url.endswith("/events") else AGENT)

    def patch(self, url, json=None):
        self.calls.append(("PATCH", url, {"json": json}))
        return self._resp(200, AGENT)

    def post(self, url, json=None):
        self.calls.append(("POST", url, {"json": json}))
        return self._resp(201, {"event_id": "e1"})


def test_an_injected_client_is_called_exactly_as_before(monkeypatch):
    """The caller owns an injected client (tests, the provisioning tool): C-4
    adds nothing to its calls, so fakes without a ``headers`` kwarg still work."""
    _identity(monkeypatch, "svc-killswitch", secrets.token_urlsafe(24))
    monkeypatch.setattr(clients, "_caller_key_warned", True)
    http = _Bare()
    reg = RegistryClient(client=http, base_url="http://t")
    reg.get_agent("a1")
    reg.list_agents(domain="d")
    reg.set_status("a1", "killed")
    led = LedgerClient(client=http, base_url="http://t", caller=None)
    monkeypatch.setattr(led, "_caller", None)
    led.append("probe.note", {})
    led.events()
    assert [c[0] for c in http.calls] == ["GET", "GET", "PATCH", "POST", "GET"]
    assert all("headers" not in c[2] for c in http.calls)


@pytest.mark.parametrize("agent_id", ["..", ".", "%2e%2e", "%2E", "a%2fb", "a%25b", "x?y", "x/y"])
def test_registry_set_status_with_a_dot_segment_id_never_carries_the_pair(wire, monkeypatch, agent_id):
    """C-683 F-C683-2: httpx normalises ``/agents/..`` to ``/``; the pair is decided on that wire path, so an id
    that rewrites the route (or, percent-encoded, may be rewritten by a receiver) is not a guarded PATCH and gets the
    perimeter secret only."""
    _identity(monkeypatch, "svc-killswitch", secrets.token_urlsafe(24))
    RegistryClient(base_url="http://registry.test").set_status(agent_id, "killed")
    assert wire[-1].method == "PATCH"
    assert _pair(wire[-1]) == (None, None)
