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


def _console(rows, kill_answer=None):
    """rows: what GET /agents answers (JSON). kill_answer(domain) -> (status, json) for POST /kill/domain/<domain>."""
    posts: list[str] = []

    def registry(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    def killswitch(request: httpx.Request) -> httpx.Response:
        domain = request.url.path.rsplit("/", 1)[-1]
        posts.append(domain)
        if kill_answer is not None:
            status, body = kill_answer(domain)
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"domain": domain, "killed": [domain + "-a"], "already_killed": [],
                                         "results": [{"agent_id": domain + "-a", "outcome": "killed"}]})

    wrap = lambda t: ServiceClient(client=httpx.Client(transport=httpx.MockTransport(t), base_url="http://t"),  # noqa: E731
                                   base_url="http://t")
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    app = create_app(registry=wrap(registry), ledger=dead, killswitch=wrap(killswitch), delegation=dead,
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
    c, posts = _console(_good(2) + [{"agent_id": leak, "domain": {leak: 1}, "status": "active"}, leak])
    r = c.post("/api/fleet/halt", json=HALT)
    assert leak not in r.text and r.json()["bad_rows"] == 2


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
