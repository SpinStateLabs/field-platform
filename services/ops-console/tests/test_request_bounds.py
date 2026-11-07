"""S9-31: the console's action models mirror the kill-switch's own bounds, so a bad value is ONE 422 before any upstream call.

`OperatorAction`, `BulkAction` and `FleetHalt` took `operator` and `reason` with `min_length=1` only, while the kill-switch's `KillRequest`
allows operator at most 200 and reason at most 1000. `POST /api/agents/bulk` loops over up to 100 agents and `/api/fleet/halt` over every
domain, sending the same refused body each time, so a 201-character operator made 100 failing kill-switch calls and a table of 100
identical errors. Now an over-long or whitespace-only operator or reason is a single 422 and the (fake) kill-switch sees zero calls.
`ResolveAction.resolved_by` gets 200 (spend-governor's own `resolved_by` has `min_length=1` only on main, so 200 is the console's choice,
matching the kill-switch operator bound; open PR #661 adds the same 200 to the governor)."""

import pytest
from fastapi.testclient import TestClient

from ops_console.api import create_app

OP, REASON = 200, 1000


class Recorder:
    """An upstream that records every call and answers 200 with an empty object."""

    def __init__(self):
        self.calls = []

    def get(self, path, **kw):
        self.calls.append(("get", path))
        return 200, [] if path in ("/agents", "/tokens", "/escalations") else {}

    def post(self, path, json=None, **kw):
        self.calls.append(("post", path, json))
        return 200, {}


@pytest.fixture(scope="module")
def _built():
    kill, gov = Recorder(), Recorder()
    other = Recorder()
    app = create_app(registry=other, ledger=other, delegation=other, governor=gov, killswitch=kill, sentinel=other)
    return TestClient(app, raise_server_exceptions=False), kill, gov


@pytest.fixture()
def console(_built):
    client, kill, gov = _built          # one app for the module (building it is the slow part); calls cleared per test
    kill.calls.clear()
    gov.calls.clear()
    return client, kill, gov


ROUTES = [
    ("/api/agents/a1/kill", {}),
    ("/api/agents/a1/revive", {}),
    ("/api/agents/a1/drill", {}),
    ("/api/agents/bulk", {"action": "kill", "agent_ids": ["a1", "a2"]}),
    ("/api/fleet/halt", {"confirm": "HALT", "domains": ["finance"]}),
]


def payload(extra, **kw):
    base = {"operator": "Don H", "reason": "because"}
    return {**base, **extra, **kw}


@pytest.mark.parametrize("path, extra", ROUTES, ids=[r[0] for r in ROUTES])
@pytest.mark.parametrize("field, limit", [("operator", OP), ("reason", REASON)])
def test_the_boundary_is_accepted_and_one_over_is_one_422_with_zero_upstream_calls(console, path, extra, field, limit):
    client, kill, _ = console
    ok = client.post(path, json=payload(extra, **{field: "x" * limit}))
    assert ok.status_code != 422, ok.text
    assert kill.calls, "the boundary value must reach the kill-switch"
    kill.calls.clear()
    over = client.post(path, json=payload(extra, **{field: "x" * (limit + 1)}))
    assert over.status_code == 422
    assert kill.calls == []
    assert "x" * 20 not in over.text


@pytest.mark.parametrize("path, extra", ROUTES, ids=[r[0] for r in ROUTES])
@pytest.mark.parametrize("field", ["operator", "reason"])
@pytest.mark.parametrize("blank", ["   ", " ", "\t", "\n", " \t\n ", " ", "　"],
                         ids=["3sp", "1sp", "tab", "nl", "mixed", "nbsp", "ideographic"])
def test_a_whitespace_only_operator_or_reason_is_one_422_with_zero_upstream_calls(console, path, extra, field, blank):
    client, kill, _ = console
    r = client.post(path, json=payload(extra, **{field: blank}))
    assert r.status_code == 422
    assert kill.calls == []


def test_a_201_character_operator_on_a_bulk_of_100_agents_is_one_422_not_100_calls(console):
    client, kill, _ = console
    ids = [f"agent-{i}" for i in range(100)]
    r = client.post("/api/agents/bulk", json={"action": "kill", "agent_ids": ids, "operator": "o" * 201, "reason": "why"})
    assert r.status_code == 422
    assert kill.calls == []


def test_the_resolver_name_is_bounded_and_not_blank(console):
    client, _, gov = console
    path = "/api/escalations/esc-1/resolve"
    assert client.post(path, json={"resolved_by": "r" * 200}).status_code != 422
    assert gov.calls
    gov.calls.clear()
    for bad in ("r" * 201, "   ", "\t\n", ""):
        assert client.post(path, json={"resolved_by": bad}).status_code == 422, repr(bad)
    assert gov.calls == []


def test_a_normal_action_is_unchanged_and_the_default_reason_still_works(console):
    client, kill, _ = console
    r = client.post("/api/agents/a1/kill", json={"operator": "Don H"})
    assert r.status_code == 200
    assert kill.calls[-1][1] == "/kill/a1" and kill.calls[-1][2]["reason"] == "via ops-console"
    assert kill.calls[-1][2]["operator"] == "Don H"
