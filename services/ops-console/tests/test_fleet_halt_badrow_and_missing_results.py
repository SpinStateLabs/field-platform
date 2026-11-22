"""Fleet-halt hardening (roley.reviewer URGENT, current main; kill path):

* F2 (HIGH, fail-open): one malformed registry row made a default FLEET HALT answer 500 and send ZERO kills. A bad
  row is skipped and reported as errored; every other agent's domain is still halted; the banner (all_ok) is not green.
* F1 (MEDIUM): a 2xx from the kill-switch whose body has no (or an invalid) ``results`` list is not a halt.

The registry and the kill-switch are stubs behind httpx.MockTransport: the kill-switch stub records every
POST /kill/domain/<d> it receives.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from ops_console.api import ServiceClient, create_app

HALT = {"operator": "CISO", "reason": "badrow", "confirm": "HALT"}


class _Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


class Posts(list):
    """Domain halts received (domain names); ``.agents`` = per-agent kills received; ``.events`` = ledger appends."""

    def __init__(self):
        super().__init__()
        self.agents: list[str] = []
        self.events: list[dict] = []


def _console(rows, kill_answer=None, kill_status=200):
    """rows: what GET /agents answers (JSON). kill_answer(domain) -> (status, json) for POST /kill/domain/<domain>."""
    posts = Posts()

    def registry(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    def ids_in(domain):
        if not isinstance(rows, list):
            return []
        return [r["agent_id"] for r in rows if isinstance(r, dict) and isinstance(r.get("agent_id"), str)
                and r.get("domain") == domain and r.get("status") != "retired"]

    def killswitch(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/kill/domain/"):
            domain = path.rsplit("/", 1)[-1]
            posts.append(domain)
            if kill_answer is not None:
                status, body = kill_answer(domain)
                return httpx.Response(status, json=body)
            ids = ids_in(domain) or [domain + "-a"]
            return httpx.Response(kill_status, json={"domain": domain, "killed": ids, "already_killed": [],
                                                     "results": [{"agent_id": i, "outcome": "killed"} for i in ids]})
        agent = path.rsplit("/", 1)[-1]
        posts.agents.append(agent)
        return httpx.Response(200, json={"agent_id": agent, "previous_status": "active"})

    def ledger(request: httpx.Request) -> httpx.Response:
        import json as _json
        posts.events.append(_json.loads(request.content))
        return httpx.Response(201, json={"ok": True})

    wrap = lambda t: ServiceClient(client=httpx.Client(transport=httpx.MockTransport(t), base_url="http://t"),  # noqa: E731
                                   base_url="http://t")
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    app = create_app(registry=wrap(registry), ledger=wrap(ledger), killswitch=wrap(killswitch), delegation=dead,
                     governor=dead, sentinel=dead, lifecycle=dead, attest=dead, crosswalk=dead, federation=dead,
                     replay=dead, gateway=dead)
    return TestClient(app), posts


def _good(n):
    return [{"agent_id": f"g{i}", "name": f"g{i}", "owner": "O", "domain": f"d{i}", "status": "active"}
            for i in range(n)]


@pytest.mark.parametrize("bad", [
    "not-an-object",
    None,
    42,
    {"agent_id": "bad", "domain": ["a", "list"], "status": "active"},          # unhashable domain
    {"agent_id": "bad", "domain": {"x": 1}, "status": "active"},
    {"agent_id": "bad", "domain": 7, "status": "active"},
    {"agent_id": "bad", "domain": "has/slash", "status": "active"},
], ids=["string", "null", "int", "list-domain", "dict-domain", "int-domain", "slash-domain"])
def test_one_bad_row_among_good_rows_halts_every_good_domain_and_reports_one_error(bad):
    c, posts = _console(_good(5)[:2] + [bad] + _good(5)[2:])
    r = c.post("/api/fleet/halt", json=HALT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(posts) == ["d0", "d1", "d2", "d3", "d4"], "a bad row stopped the halt of the good agents"
    assert body["all_ok"] is False, "the banner must not be green"
    assert body["bad_rows"] == 1 and body["agent_errors"] >= 1
    assert sum(1 for x in body["results"] if x["ok"]) == 5


def test_a_registry_answer_that_is_not_a_list_is_a_clean_502_not_a_500():
    c, posts = _console({"agents": []})
    r = c.post("/api/fleet/halt", json=HALT)
    assert r.status_code == 502 and posts == []


def test_all_good_rows_still_give_all_ok():
    c, posts = _console(_good(3))
    r = c.post("/api/fleet/halt", json=HALT)
    assert r.status_code == 200 and r.json()["all_ok"] is True and r.json()["bad_rows"] == 0
    assert sorted(posts) == ["d0", "d1", "d2"]


def test_a_retired_agent_is_still_skipped_and_is_not_an_error():
    rows = _good(2) + [{"agent_id": "old", "domain": "gone", "status": "retired"}]
    c, posts = _console(rows)
    r = c.post("/api/fleet/halt", json=HALT)
    assert r.json()["all_ok"] is True and "gone" not in posts


@pytest.mark.parametrize("body", [
    {"domain": "d0", "killed": ["x"]},                 # no results key
    {"results": "nope"},                               # results not a list
    {"results": None},
    [],                                                # not even an object
    "ok",
    {},
], ids=["no-results", "results-str", "results-null", "list-body", "str-body", "empty-obj"])
def test_a_2xx_without_a_valid_results_list_is_a_failure_never_a_green_halt(body):
    c, posts = _console(_good(2), kill_answer=lambda d: (200, body))
    r = c.post("/api/fleet/halt", json=HALT)
    assert r.status_code == 200
    out = r.json()
    assert out["all_ok"] is False
    assert out["domains_failed"] == 2
    assert all(x["ok"] is False for x in out["results"])


def test_a_domain_whose_report_lists_an_error_is_still_not_ok():
    c, _ = _console(_good(1), kill_answer=lambda d: (200, {"results": [{"agent_id": "a", "outcome": "error", "error": "x"}]}))
    assert c.post("/api/fleet/halt", json=HALT).json()["all_ok"] is False


# --- what old PR 872 wanted to pin, inverted from "refuse everything" to "skip the bad row and report it" ------------


def test_a_retired_row_with_a_bad_domain_is_still_ignored_and_is_not_an_error():
    rows = _good(2) + [{"agent_id": "old", "domain": ["x"], "status": "retired"}]
    c, posts = _console(rows)
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert out["bad_rows"] == 0 and out["all_ok"] is True and sorted(posts) == ["d0", "d1"]


def test_bad_row_content_never_reaches_the_response():
    leak = "SECRET-DOMAIN-TEXT-123"
    c, posts = _console(_good(2) + [{"agent_id": "odd-id", "domain": {leak: 1}, "status": "active"}, leak])
    r = c.post("/api/fleet/halt", json=HALT)
    assert leak not in r.text and r.json()["bad_rows"] == 2          # the id is reported (N3), the row's content is not


def test_a_wrong_shape_registry_answer_is_a_fixed_502_that_leaks_nothing():
    c, posts = _console({"secret": "SECRET-BODY-123"})
    r = c.post("/api/fleet/halt", json=HALT)
    assert r.status_code == 502 and "SECRET-BODY-123" not in r.text and posts == []


def test_explicit_domains_do_not_consult_the_registry_at_all():
    c, posts = _console("not a list at all")
    r = c.post("/api/fleet/halt", json={**HALT, "domains": ["ops"]})
    assert r.status_code == 200 and posts == ["ops"] and r.json()["bad_rows"] == 0


def test_each_domain_is_halted_once_even_with_many_agents_in_it():
    rows = [{"agent_id": f"a{i}", "domain": "ops", "status": "active"} for i in range(5)] + _good(1)
    c, posts = _console(rows)
    assert c.post("/api/fleet/halt", json=HALT).status_code == 200
    assert sorted(posts) == ["d0", "ops"]


# --- review round 2 on PR 1144 (don.reviewer C1, N2, N3) -------------------------------------------------------------


def _agents(domain, ids):
    return [{"agent_id": i, "name": i, "owner": "O", "domain": domain, "status": "active"} for i in ids]


@pytest.mark.parametrize("results", [
    [],                                                        # empty
    [{"agent_id": "p1", "outcome": "killed"}],                 # shorter than the three the registry listed
    [{"agent_id": "x1", "outcome": "killed"}, {"agent_id": "x2", "outcome": "killed"},
     {"agent_id": "x3", "outcome": "killed"}],                 # three, but other agent ids
    [{"outcome": "killed"}, {"outcome": "killed"}, {"outcome": "killed"}],     # no ids at all
], ids=["empty", "short", "other-ids", "no-ids"])
def test_C1_a_2xx_report_that_does_not_account_for_every_listed_agent_is_a_failure(results):
    c, posts = _console(_agents("prod", ["p1", "p2", "p3"]), kill_answer=lambda d: (200, {"results": results}))
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert out["all_ok"] is False and out["domains_failed"] == 1 and out["results"][0]["ok"] is False


def test_C1_a_report_naming_every_listed_agent_is_ok_and_extra_ids_do_not_hurt():
    rows = _agents("prod", ["p1", "p2"])
    c, _ = _console(rows, kill_answer=lambda d: (200, {"results": [
        {"agent_id": "p1", "outcome": "killed"}, {"agent_id": "p2", "outcome": "already_killed"},
        {"agent_id": "p9", "outcome": "killed"}]}))
    assert c.post("/api/fleet/halt", json=HALT).json()["all_ok"] is True


def test_C1_a_dict_shaped_results_is_a_failure():
    c, _ = _console(_good(1), kill_answer=lambda d: (200, {"results": {"g0": {"outcome": "killed"}}}))
    assert c.post("/api/fleet/halt", json=HALT).json()["all_ok"] is False


def test_C1_a_202_is_not_a_halt_even_with_a_complete_report():
    c, _ = _console(_good(2), kill_status=202)
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert out["all_ok"] is False and out["domains_failed"] == 2


@pytest.mark.parametrize("domain", ["   ", "\t"], ids=["spaces", "tab"])
def test_C1_a_blank_domain_is_a_skipped_row_not_a_domain_named_blank(domain):
    rows = _good(2) + [{"agent_id": "blank", "domain": domain, "status": "active"}]
    c, posts = _console(rows)
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert sorted(posts) == ["d0", "d1"]                      # no halt was sent for a blank domain
    assert out["bad_rows"] == 1 and out["skipped_rows"][0]["agent_id"] == "blank" and out["all_ok"] is False
    assert posts.agents == ["blank"]                           # but the agent itself was killed on its own


def test_N2_a_skipped_row_with_a_valid_agent_id_is_killed_on_its_own_and_reported_separately():
    rows = _good(2) + [{"agent_id": "odd1", "name": "o", "owner": "O", "domain": 5, "status": "active"},
                       {"agent_id": "odd2", "name": "o", "owner": "O", "domain": ["x"], "status": "active"},
                       {"name": "no id", "domain": 5, "status": "active"}]
    c, posts = _console(rows)
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert sorted(posts) == ["d0", "d1"] and sorted(posts.agents) == ["odd1", "odd2"]
    assert [k["agent_id"] for k in out["agent_kills"]] == ["odd1", "odd2"] and all(k["ok"] for k in out["agent_kills"])
    assert out["all_ok"] is False and out["bad_rows"] == 3          # a malformed row is still an anomaly
    assert [x["agent_id"] for x in out["skipped_rows"]] == ["odd1", "odd2", None]


def test_N2_a_failed_individual_kill_is_reported_and_not_ok():
    rows = _good(1) + [{"agent_id": "odd1", "domain": 5, "status": "active"}]
    seen = []

    def kill(request):
        seen.append(request.url.path)
        if request.url.path.startswith("/kill/domain/"):
            return httpx.Response(200, json={"results": [{"agent_id": "g0", "outcome": "killed"}]})
        return httpx.Response(500, json={"detail": "boom"})
    c, _ = _console(rows)
    c.app.state.killswitch = ServiceClient(client=httpx.Client(transport=httpx.MockTransport(kill), base_url="http://t"),
                                           base_url="http://t")
    out = c.post("/api/fleet/halt", json=HALT).json()
    assert out["agent_kills"] == [{"agent_id": "odd1", "ok": False, "status": 500}] and out["all_ok"] is False
    assert "/kill/odd1" in seen


def test_N3_skipped_rows_are_written_to_the_ledger_by_id():
    rows = _good(1) + [{"agent_id": "odd1", "domain": 5, "status": "active"}, "junk"]
    c, posts = _console(rows)
    c.post("/api/fleet/halt", json=HALT)
    [ev] = [e for e in posts.events if e["event_type"] == "fleet.halt.skipped_rows"]
    assert ev["payload"]["count"] == 2
    assert [x["agent_id"] for x in ev["payload"]["skipped"]] == ["odd1", None]
    assert ev["payload"]["fallback_kills"] == [{"agent_id": "odd1", "ok": True}]


def test_N3_no_skipped_rows_writes_no_ledger_row_and_a_failing_ledger_never_stops_the_halt():
    c, posts = _console(_good(2))
    c.post("/api/fleet/halt", json=HALT)
    assert posts.events == []
    c2, posts2 = _console(_good(2) + ["junk"])
    c2.app.state.ledger = ServiceClient(client=_Dead(), base_url="http://dead")
    out = c2.post("/api/fleet/halt", json=HALT).json()
    assert sorted(posts2) == ["d0", "d1"] and out["bad_rows"] == 1
