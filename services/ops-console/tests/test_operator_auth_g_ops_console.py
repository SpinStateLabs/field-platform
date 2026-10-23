"""Phase G: the console forwards the HUMAN's operator headers; under REQUIRE it
never falls back to its own service identity for a human action."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import ServiceClient, create_app


class Rec:
    def __init__(self):
        self.calls = []

    def post(self, path, **kw):
        self.calls.append((path, kw))

        class R:
            status_code = 200

            def json(self):
                return {"ok": True}

        return R()

    def get(self, path, **kw):
        raise ConnectionError("n/a")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def console():
    ks, dg, other = Rec(), Rec(), Rec()
    sc = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    app = create_app(registry=sc(other), ledger=sc(other), delegation=sc(dg),
                     governor=sc(other), killswitch=sc(ks), sentinel=sc(other))
    return TestClient(app), ks, dg


BODY = {"operator": "Don", "reason": "r"}
H = {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: "fok_don_key_0123456789"}

ROUTES = [("/api/agents/a1/kill", BODY), ("/api/agents/a1/revive", BODY),
          ("/api/agents/a1/drill", BODY),
          ("/api/agents/bulk", {"agent_ids": ["a1"], "action": "kill", **BODY}),
          ("/api/fleet/halt", {"domains": ["finance"], "confirm": "HALT", **BODY})]


@pytest.mark.parametrize("path,body", ROUTES)
def test_human_headers_are_forwarded(console, path, body):
    c, ks, _ = console
    assert c.post(path, json=body, headers=H).status_code == 200
    sent = ks.calls[-1][1]["headers"]
    assert sent == {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: H[oa.HEADER_KEY]}


def test_token_revoke_forwards_the_human(console):
    c, _, dg = console
    c.post("/api/tokens/t1/revoke", headers=H)
    assert dg.calls[-1][1]["headers"][oa.HEADER_OPERATOR] == "don"


@pytest.mark.parametrize("path,body", ROUTES + [("/api/tokens/t1/revoke", None)])
def test_enforce_without_human_headers_is_401_and_nothing_is_proxied(console, monkeypatch, path, body):
    c, ks, dg = console
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    r = c.post(path, json=body) if body is not None else c.post(path)
    assert r.status_code == 401
    assert ks.calls == [] and dg.calls == []


def test_off_mode_sends_no_extra_headers(console):
    c, ks, _ = console
    c.post("/api/agents/a1/kill", json=BODY)
    assert "headers" not in ks.calls[-1][1]


def test_malformed_headers_are_400(console):
    c, ks, _ = console
    r = c.post("/api/agents/a1/kill", json=BODY,
               headers={oa.HEADER_OPERATOR: "don, evil", oa.HEADER_KEY: "k"})
    assert r.status_code == 400 and ks.calls == []


def test_escalation_resolve_forwards_the_human(console):
    c, _, _ = console
    # governor shares the "other" recorder in the fixture; just prove 401 under REQUIRE
    import os

    os.environ[oa.ENV_REQUIRE] = "1"
    try:
        assert c.post("/api/escalations/e1/resolve", json={"resolved_by": "Don"}).status_code == 401
    finally:
        del os.environ[oa.ENV_REQUIRE]


def test_console_page_has_an_operator_sign_in_that_never_uses_a_url():
    from pathlib import Path

    import ops_console

    html = (Path(ops_console.__file__).parent / "static" / "console.html").read_text(encoding="utf-8")
    assert "x-field-operator-key" in html and "sessionStorage" in html
    assert "localStorage" not in html.split("saveOperator")[1][:400]
    assert "console.log" not in html


def test_startup_warns_when_the_console_has_its_own_operator_identity(monkeypatch, caplog):
    import logging

    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-console")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY, "fok_x")
    caplog.set_level(logging.WARNING, logger="ops_console")
    sc = lambda: ServiceClient(client=Rec(), base_url="http://t")  # noqa: E731
    create_app(registry=sc(), ledger=sc(), delegation=sc(), governor=sc(),
               killswitch=sc(), sentinel=sc())
    assert any("FIELD_OPERATOR is set on the ops-console" in r.getMessage() for r in caplog.records)
    caplog.clear()
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    create_app(registry=sc(), ledger=sc(), delegation=sc(), governor=sc(),
               killswitch=sc(), sentinel=sc())
    assert not caplog.records
