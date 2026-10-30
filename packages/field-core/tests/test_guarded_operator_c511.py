"""C-511: the operator pair rides only a guarded write of the target; the perimeter secret rides every request.

Made-up values only. The route tables are compared with each receiver's own routes in the receivers' tests
(test_guarded_routes_c511.py in sealed-ledger, agent-registry, delegation-authority and kill-switch).
"""
from __future__ import annotations

import re

import httpx
import pytest

from field_core import guarded_operator as go
from field_core.clients import LedgerClient, RegistryClient

OP, KEY, SECRET = "x-field-operator", "x-field-operator-key", "x-field-auth"
TABLES = {"ledger": (go.LEDGER_TEMPLATES, go.LEDGER_GUARDED), "registry": (go.REGISTRY_TEMPLATES, go.REGISTRY_GUARDED),
          "delegation": (go.DELEGATION_TEMPLATES, go.DELEGATION_GUARDED),
          "killswitch": (go.KILLSWITCH_TEMPLATES, go.KILLSWITCH_GUARDED)}


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "made-up-shared")
    monkeypatch.setenv("FIELD_OPERATOR", "svc-made-up")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", "made-up-key")
    monkeypatch.delenv("FIELD_OPERATOR_KEY_FILE", raising=False)


def concrete(template: str) -> str:
    return re.sub(r"\{[^/}]+\}", "x1", template)


@pytest.mark.parametrize("name", sorted(TABLES))
def test_every_table_route_is_guarded_and_other_routes_are_not(name):
    templates, routes = TABLES[name]
    for method, template in templates:
        assert go.is_guarded_path(method, concrete(template), routes), (method, template)
        other = "GET" if method != "GET" else "POST"
        assert not go.is_guarded_path(other, concrete(template), routes), (other, template)
        assert not go.is_guarded_path(method, concrete(template) + "/extra/segment", routes)
    assert not go.is_guarded_path("GET", "/health", routes)
    assert not go.is_guarded_path("POST", "/introspect", routes)


def test_a_template_parameter_is_one_path_segment():
    routes = go.compile_routes([("POST", "/kill/{agent_id}"), ("POST", "/kill/domain/{domain}")])
    assert go.is_guarded_path("POST", "/kill/a1", routes) and go.is_guarded_path("POST", "/kill/domain/d1", routes)
    assert not go.is_guarded_path("POST", "/kill/a1/more", routes) and not go.is_guarded_path("POST", "/kill/", routes)


def test_is_guarded_strips_the_base_prefix_and_refuses_a_path_outside_it():
    routes = go.KILLSWITCH_GUARDED
    assert go.is_guarded("POST", "/ks/kill/a1", "http://host/ks", routes)
    assert not go.is_guarded("POST", "/kill/a1", "http://host/ks", routes)
    assert not go.is_guarded("POST", "/other/kill/a1", "http://host/ks", routes)
    assert not go.is_guarded("POST", "/zz/kill/a1", "http://host/ks", routes)   # same length as the prefix (C-683 F-C683-5)
    assert go.is_guarded("POST", "/kill/a1", "http://host", routes)


def test_request_headers_carry_the_pair_on_a_guarded_route_only():
    guarded = go.request_headers("POST", "/tokens/t1/revoke", go.DELEGATION_GUARDED)
    read = go.request_headers("GET", "/tokens", go.DELEGATION_GUARDED)
    assert guarded[SECRET] == "made-up-shared" and guarded[OP] == "svc-made-up" and guarded[KEY] == "made-up-key"
    assert read == {SECRET: "made-up-shared"}


def test_no_secret_and_no_identity_send_nothing(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET")
    monkeypatch.delenv("FIELD_OPERATOR")
    monkeypatch.delenv("FIELD_OPERATOR_KEY")
    assert go.request_headers("POST", "/tokens", go.DELEGATION_GUARDED) == {}
    assert go.perimeter_headers() == {}


def test_the_moved_auth_flow_adds_the_pair_only_on_a_guarded_route():
    seen = []

    def handler(req):
        seen.append(dict(req.headers))
        return httpx.Response(200, json={})

    c = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ks.invalid",
                     auth=go.GuardedOperatorAuth("http://ks.invalid", ("svc", "made-up-key"), go.KILLSWITCH_GUARDED))
    c.get("/agents")
    c.post("/kill/a1")
    assert OP not in seen[0] and KEY not in seen[0]
    assert seen[1][OP] == "svc" and seen[1][KEY] == "made-up-key"
    none = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ks.invalid",
                        auth=go.GuardedOperatorAuth("http://ks.invalid", None, go.KILLSWITCH_GUARDED))
    none.post("/kill/a1")
    assert OP not in seen[2]


# --- the field-core clients ---------------------------------------------------------------------------------------

def _own(client_cls, **kw):
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        body: object = [] if req.url.path.endswith(("s", "check")) else {"agent_id": "a1", "status": "active"}
        if req.url.path.endswith("/retention/check"):
            body = {"ok": True, "held": False, "oldest_event": None, "policy": None, "findings": []}
        return httpx.Response(200 if req.method != "POST" else 201, json=body)

    c = client_cls(base_url="http://t.invalid", **kw)
    c._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://t.invalid")
    c._own_client = True
    return c, seen


def _pair(req):
    return req.headers.get(OP), req.headers.get(KEY)


def test_the_registry_client_reads_carry_no_pair_and_the_status_write_does():
    reg, seen = _own(RegistryClient)
    reg.get_agent("a1")
    reg.list_agents()
    reg.set_status("a1", "killed")
    assert [_pair(r) for r in seen[:2]] == [(None, None), (None, None)]
    assert seen[2].method == "PATCH" and _pair(seen[2]) == ("svc-made-up", "made-up-key")
    assert all(r.headers[SECRET] == "made-up-shared" for r in seen)


def test_the_ledger_client_reads_carry_no_pair_and_the_append_does():
    led, seen = _own(LedgerClient, caller=None)
    led.events("probe.note")
    led.retention_check()
    led.append("probe.note", {"n": 1})
    assert [_pair(r) for r in seen[:2]] == [(None, None), (None, None)]
    assert seen[2].method == "POST" and seen[2].url.path == "/events" and _pair(seen[2]) == ("svc-made-up", "made-up-key")
    assert all(r.headers[SECRET] == "made-up-shared" for r in seen)


# --- the drift helper the receivers' tests use --------------------------------------------------------------------

def _fake_app():
    from fastapi import Depends, FastAPI

    async def _guard():                       # the name the helper looks for (operator_health.guard's inner function)
        return None

    app = FastAPI()

    @app.post("/w/{item}", dependencies=[Depends(_guard)])
    def write(item: str):
        return {}

    @app.get("/r/{item}")
    def read(item: str):
        return {}

    @app.patch("/p/{item}")
    def patch(item: str):
        return {}

    return app


def test_the_drift_helper_reports_every_direction():
    app = _fake_app()
    ok = [("POST", "/w/{item}"), ("PATCH", "/p/{item}")]
    extras = [("PATCH", "/p/{item}")]
    assert go.guard_dependent_routes(app) == {("POST", "/w/{item}")}
    assert go.drift_problems(app, ok, extras) == []
    assert any("missing from the table: POST /w/{item}" in p for p in go.drift_problems(app, [("PATCH", "/p/{item}")], extras))
    assert any("not a route" in p and "/ghost" in p for p in go.drift_problems(app, ok + [("POST", "/ghost")], extras))
    assert any("neither guards nor declares: GET /r/{item}" in p for p in go.drift_problems(app, ok + [("GET", "/r/{item}")], extras))
    assert any("declared extra that is not a route" in p for p in go.drift_problems(app, ok, extras + [("PUT", "/nope")]))
    assert any("missing from the table: PATCH /p/{item}" in p for p in go.drift_problems(app, [("POST", "/w/{item}")], extras))


def test_the_method_is_compared_without_case():
    # C-586 F-C586-2 / C-624: a lower-case method is the same route
    for method in ("post", "Post", "POST"):
        assert go.is_guarded_path(method, "/tokens/t1/revoke", go.DELEGATION_GUARDED), method
        assert go.is_guarded(method, "/da/tokens/t1/revoke", "http://h/da", go.DELEGATION_GUARDED), method
    assert go.request_headers("post", "/tokens", go.DELEGATION_GUARDED)["x-field-operator"] == "svc-made-up"
    assert not go.is_guarded_path("get", "/tokens", go.DELEGATION_GUARDED)
