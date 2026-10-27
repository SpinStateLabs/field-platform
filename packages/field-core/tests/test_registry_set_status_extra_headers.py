"""Phase G C-12 follow-up (guards ruling, "per-call headers on RegistryClient.set_status"):
``RegistryClient.set_status`` takes an explicit per-call ``extra_headers`` argument, so the
kill-switch sends ``x-field-operator-on-behalf-of`` through a public API instead of
reaching into ``_client``, ``_base``, ``_own_client`` and ``_request_auth``.

What is pinned here:
- the headers are added to THAT one request, after the per-request auth headers (C-4),
  for the client's own httpx client and for an injected one;
- ``extra_headers=None`` (the default) sends exactly what the method sent before the
  argument existed (no ``headers`` keyword at all on an injected client);
- a per-call header can never replace a header the client sets itself (the shared
  secret, the service's own operator pair): refused before anything is sent;
- the answer mapping is unchanged (404 -> AgentNotRegisteredError, other non-200 and
  transport failures -> RegistryUnreachableError).

Keys and secrets are generated per run and never printed; only presence, equality and
8-hex fingerprints are asserted.
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
from field_core.clients import (
    AgentNotRegisteredError,
    HeaderCollisionError,
    RegistryClient,
    RegistryUnreachableError,
)

OBO = "x-field-operator-on-behalf-of"
AGENT = {"agent_id": "canary-gb10", "status": "killed", "domain": "canary"}


@pytest.fixture()
def wire(monkeypatch):
    """Every httpx.Client built from here on talks to a recording transport."""
    for name in (oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_OPERATOR_KEY_FILE",
                 oa.ENV_REGISTRY, oa.ENV_REQUIRE, SECRET_ENV,
                 clients.CALLER_ID_ENV, clients.CALLER_KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=AGENT)

    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return seen


def _fp(value: str | None) -> str | None:
    return None if value is None else hashlib.sha256(value.encode()).hexdigest()[:8]


class Recorder:
    """An injected client: records every patch call's keyword arguments exactly."""

    def __init__(self, status: int = 200, raises: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.status, self.raises = status, raises

    def patch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.raises is not None:
            raise self.raises
        return httpx.Response(self.status, json=AGENT if self.status == 200 else {"detail": "x"})


def test_own_client_adds_the_per_call_header_after_the_per_request_auth_headers(wire, monkeypatch):
    secret, key = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    monkeypatch.setenv(SECRET_ENV, secret)
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, key)
    reg = RegistryClient(base_url="http://registry.test")

    assert reg.set_status("canary-gb10", "killed", extra_headers={OBO: "don"}) == AGENT
    req = wire[-1]
    assert req.method == "PATCH" and str(req.url) == "http://registry.test/agents/canary-gb10"
    assert json.loads(req.read()) == {"status": "killed"}
    assert req.headers.get(OBO) == "don"
    assert _fp(req.headers.get(SECRET_HEADER)) == _fp(secret)
    assert req.headers.get(oa.HEADER_OPERATOR) == "svc-killswitch"
    assert _fp(req.headers.get(oa.HEADER_KEY)) == _fp(key)
    # auth headers first, then the per-call one (the order the kill-switch used to build)
    names = [k.lower() for k, _ in req.headers.raw if k.lower().startswith(b"x-field")]
    assert names[-1] == OBO.encode(), names


def test_own_client_without_extra_headers_sends_the_same_request_as_before(wire, monkeypatch):
    monkeypatch.setenv(SECRET_ENV, secrets.token_urlsafe(24))
    reg = RegistryClient(base_url="http://registry.test")
    reg.set_status("canary-gb10", "killed")
    reg.set_status("canary-gb10", "killed", extra_headers=None)
    a, b = wire[-2], wire[-1]
    assert a.headers.raw == b.headers.raw and a.read() == b.read() and a.url == b.url
    assert OBO not in a.headers


def test_injected_client_gets_only_the_per_call_header_and_nothing_else_changes():
    rec = Recorder()
    reg = RegistryClient(client=rec, base_url="http://t")
    reg.set_status("a1", "killed")
    reg.set_status("a1", "active", extra_headers={OBO: "don"})
    assert rec.calls == [
        ("http://t/agents/a1", {"json": {"status": "killed"}}),                 # exactly as before
        ("http://t/agents/a1", {"json": {"status": "active"}, "headers": {OBO: "don"}}),
    ]


@pytest.mark.parametrize("name", [SECRET_HEADER, SECRET_HEADER.upper(), oa.HEADER_OPERATOR,
                                  oa.HEADER_KEY.title()])
def test_a_per_call_header_can_never_replace_one_the_client_sets_itself(wire, monkeypatch, name):
    monkeypatch.setenv(SECRET_ENV, secrets.token_urlsafe(24))
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, secrets.token_urlsafe(24))
    reg = RegistryClient(base_url="http://registry.test")
    with pytest.raises(HeaderCollisionError):
        reg.set_status("canary-gb10", "killed", extra_headers={name: "mallory"})
    assert wire == []                                       # refused before anything was sent


def test_the_answer_mapping_is_unchanged_with_per_call_headers():
    with pytest.raises(AgentNotRegisteredError):
        RegistryClient(client=Recorder(404), base_url="http://t").set_status(
            "a1", "killed", extra_headers={OBO: "don"})
    with pytest.raises(RegistryUnreachableError, match="registry returned 403"):
        RegistryClient(client=Recorder(403), base_url="http://t").set_status(
            "a1", "killed", extra_headers={OBO: "don"})
    with pytest.raises(RegistryUnreachableError, match="down"):
        RegistryClient(client=Recorder(raises=ConnectionError("down")), base_url="http://t").set_status(
            "a1", "killed", extra_headers={OBO: "don"})
