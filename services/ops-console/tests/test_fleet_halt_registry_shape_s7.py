"""S7-27 — POST /api/fleet/halt (no domains given): a registry answer of the wrong shape is a fixed
502 and no kill is sent, never a 500 mid-halt. Retired agents, the 'general' fallback and the C-19
ok/counts logic keep their behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ops_console.api import ServiceClient, create_app

BODY = {"operator": "don", "reason": "drill", "confirm": "HALT"}
LEAK = "REGISTRY-TEXT-MUST-NOT-LEAK"


class Stub:
    def __init__(self, status=200, body=None):
        self.status, self.body, self.calls = status, {} if body is None else body, []

    def _answer(self, path, kw):
        self.calls.append((path, kw))

        class R:
            status_code = self.status

            def json(_):  # noqa: N805
                return self.body

        return R()

    def get(self, path, **kw):
        return self._answer(path, kw)

    def post(self, path, **kw):
        return self._answer(path, kw)


def build(registry_body, registry_status=200):
    reg, kill = Stub(registry_status, registry_body), Stub(200, {"results": []})
    other = ServiceClient(client=Stub(), base_url="http://t")
    args = {k: other for k in ("ledger", "delegation", "governor", "sentinel", "lifecycle", "attest",
                               "crosswalk", "federation", "replay", "gateway")}
    app = create_app(registry=ServiceClient(client=reg, base_url="http://t"),
                     killswitch=ServiceClient(client=kill, base_url="http://t"), **args)
    return TestClient(app, raise_server_exceptions=False), kill


@pytest.mark.parametrize("registry_body", [
    {LEAK: 1},                                # a dict iterates its keys
    LEAK,                                     # a bare string
    None,                                     # a JSON null
    [LEAK],                                   # a row that is not an object
    [None],
    [[1, 2]],
    [{"domain": 5, "status": "active"}],      # a non-string domain
    [{"domain": ["x"], "status": "active"}],
    [{"domain": "ok", "status": "active"}, {"domain": 5}],
], ids=["dict", "str", "null", "str-row", "null-row", "list-row", "int-domain", "list-domain", "mixed"])
def test_a_registry_answer_of_the_wrong_shape_is_a_fixed_502_and_kills_nothing(registry_body):
    client, kill = build(registry_body)
    r = client.post("/api/fleet/halt", json=BODY)
    assert r.status_code == 502, r.text
    assert "unexpected shape" in r.json()["detail"]
    assert LEAK not in r.text
    assert kill.calls == []                    # nothing was halted


def test_a_good_registry_still_halts_each_domain_once_and_skips_retired():
    rows = [{"domain": "finance", "status": "active"}, {"domain": "finance", "status": "active"},
            {"domain": "ops", "status": "active"}, {"domain": "old", "status": "retired"},
            {"status": "active"}, {"domain": "", "status": "active"}]
    client, kill = build(rows)
    r = client.post("/api/fleet/halt", json=BODY)
    assert r.status_code == 200, r.text
    assert r.json()["domains"] == ["finance", "general", "ops"]
    assert [c[0] for c in kill.calls] == ["/kill/domain/finance", "/kill/domain/general", "/kill/domain/ops"]
    assert r.json()["all_ok"] is True


def test_a_retired_row_with_a_bad_domain_is_still_ignored():
    client, kill = build([{"domain": 5, "status": "retired"}, {"domain": "ops", "status": "active"}])
    assert client.post("/api/fleet/halt", json=BODY).json()["domains"] == ["ops"]


def test_an_unavailable_registry_keeps_its_existing_502():
    client, kill = build({"detail": "down"}, registry_status=503)
    r = client.post("/api/fleet/halt", json=BODY)
    assert r.status_code == 502 and "registry unavailable" in r.json()["detail"]
    assert kill.calls == []


def test_explicit_domains_do_not_consult_the_registry():
    client, kill = build("garbage")
    r = client.post("/api/fleet/halt", json={**BODY, "domains": ["ops"]})
    assert r.status_code == 200 and [c[0] for c in kill.calls] == ["/kill/domain/ops"]
