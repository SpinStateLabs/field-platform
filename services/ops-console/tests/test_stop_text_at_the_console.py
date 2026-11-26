"""The console holds a stop action's reason and operator to the kill-switch's character rules: a refused value is one
422 and the kill-switch is never called; an ordinary one is sent on as typed."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import ServiceClient, create_app

ROUTES = {
    "kill": ("/api/agents/a1/kill", {}, "/kill/a1"),
    "revive": ("/api/agents/a1/revive", {}, "/revive/a1"),
    "drill": ("/api/agents/a1/drill", {}, "/drill/a1"),
    "bulk": ("/api/agents/bulk", {"action": "kill", "agent_ids": ["a1"]}, "/kill/a1"),
    "fleet-halt": ("/api/fleet/halt", {"confirm": "HALT", "domains": ["d1"]}, "/kill/domain/d1"),
}
REFUSED = {"line-feed": "two" + chr(10) + "lines", "tab": "a" + chr(9) + "tab",
           "zero-width-joiner": "zero" + chr(0x200D) + "width", "line-separator": "a" + chr(0x2028) + "b",
           "lone-surrogate": "lone" + chr(0xD800), "blank": "   "}


class Rec:
    def __init__(self):
        self.calls, self.reads = [], []

    def post(self, path, **kw):
        self.calls.append((path, kw))

        class R:
            status_code = 200

            def json(self):
                return {"ok": True}

        return R()

    def get(self, path, **kw):
        self.reads.append(path)
        raise ConnectionError("n/a")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def console():
    ks, other = Rec(), Rec()
    sc = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    app = create_app(registry=sc(other), ledger=sc(other), delegation=sc(other),
                     governor=sc(other), killswitch=sc(ks), sentinel=sc(other))
    return TestClient(app), ks, other


def send(client, path, body):
    # raw JSON: a lone surrogate travels as the \uXXXX escape the server's parser accepts
    return client.post(path, content=json.dumps(body, ensure_ascii=True), headers={"content-type": "application/json"})


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("name", REFUSED)
def test_a_refused_reason_never_reaches_the_kill_switch(console, route, name):
    client, ks, _ = console
    path, extra, _sent = ROUTES[route]
    r = send(client, path, {**extra, "operator": "CISO", "reason": REFUSED[name]})
    assert r.status_code == 422, r.text
    assert ks.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_operator_text_with_an_unpaired_surrogate_never_reaches_the_kill_switch(console, route):
    client, ks, _ = console
    path, extra, _sent = ROUTES[route]
    r = send(client, path, {**extra, "operator": "CISO" + chr(0xD800), "reason": "incident"})
    assert r.status_code == 422, r.text
    assert ks.calls == []


@pytest.mark.parametrize("route", ROUTES)
def test_an_ordinary_reason_is_sent_on_as_typed(console, route):
    client, ks, _ = console
    path, extra, sent = ROUTES[route]
    send(client, path, {**extra, "operator": "CISO", "reason": " incident 42 "})
    assert [c[0] for c in ks.calls] == [sent]
    assert ks.calls[0][1]["json"] == {"operator": "CISO", "reason": " incident 42 "}


def test_a_refused_fleet_halt_without_named_domains_does_not_read_the_registry(console):
    client, ks, other = console
    r = send(client, "/api/fleet/halt", {"operator": "CISO", "reason": "a" + chr(9) + "b", "confirm": "HALT"})
    assert r.status_code == 422, r.text
    assert ks.calls == [] and other.reads == []
