"""POST /api/fleet/halt without explicit domains asks the registry for the fleet. The
registry's answer is checked for shape before any halt is sent (scout S-C3): a dict
({"agents": []}) or a list holding non-objects used to raise (a 500) after nothing was
halted. A shape the console cannot read is a 502 with fixed text, and NO kill-switch call.

The empty-fleet answer is pinned as it behaves TODAY and is an open question for Don: a
registry that lists no non-retired agent gives 200, `all_ok: true`, `domains: []`,
`results: []`, i.e. "nothing to halt" reads as success. These tests do not say that is right."""
from __future__ import annotations

import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import create_app

BODY = {"operator": "Don", "reason": "sc3", "confirm": "HALT"}
MARK = "zz-marker-do-not-echo"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def wire(monkeypatch):
    class Wire:
        seen: list[httpx.Request] = []
        registry_body: object = []
        registry_status = 200

    w = Wire()
    w.seen = []
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        w.seen.append(request)
        if request.method == "GET" and request.url.path.endswith("/agents"):
            return httpx.Response(w.registry_status, json=w.registry_body)
        return httpx.Response(200, json={"results": []})

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return w


def _pair():
    return {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: secrets.token_urlsafe(18)}


def _halt(**extra):
    return TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/fleet/halt", json={**BODY, **extra}, headers=_pair())


def _kills(wire):
    return [r for r in wire.seen if "/kill/" in r.url.path]


@pytest.mark.parametrize("body", [{"agents": []}, "oops", 5, ["x"], [1, 2], [None], [["nested"]], True])
def test_a_registry_answer_of_the_wrong_shape_is_a_502_and_halts_nothing(wire, body):
    wire.registry_body = body
    r = _halt()
    assert r.status_code == 502, r.text
    assert "registry" in r.json()["detail"] and "Traceback" not in r.text
    assert _kills(wire) == []


def test_a_domain_that_is_not_a_string_is_a_502_and_halts_nothing(wire):
    wire.registry_body = [{"agent_id": "a", "domain": "finance", "status": "active"},
                          {"agent_id": "b", "domain": 5, "status": "active"}]
    r = _halt()
    assert r.status_code == 502 and _kills(wire) == []


def test_the_502_text_never_echoes_the_registry_answer(wire):
    wire.registry_body = MARK
    assert MARK not in _halt().text


def test_a_well_formed_fleet_halts_every_domain_once(wire):
    wire.registry_body = [
        {"agent_id": "a", "domain": "finance", "status": "active"},
        {"agent_id": "b", "domain": "finance", "status": "killed"},
        {"agent_id": "c", "domain": "hr", "status": "active"},
        {"agent_id": "d", "domain": None, "status": "active"},
        {"agent_id": "e", "domain": "retired-only", "status": "retired"},
    ]
    r = _halt()
    assert r.status_code == 200, r.text
    assert r.json()["domains"] == ["finance", "general", "hr"]
    assert len(_kills(wire)) == 3


def test_an_empty_fleet_is_pinned_as_it_is_today_all_ok_true_nothing_halted(wire):
    wire.registry_body = []
    r = _halt()
    assert r.status_code == 200
    body = r.json()
    assert body["domains"] == [] and body["results"] == [] and body["all_ok"] is True
    assert _kills(wire) == []


def test_explicit_domains_do_not_consult_the_registry(wire):
    wire.registry_body = "oops"                      # would be a 502 if it were read
    r = _halt(domains=["finance"])
    assert r.status_code == 200
    assert not [q for q in wire.seen if q.method == "GET" and q.url.path.endswith("/agents")]
