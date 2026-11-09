"""S12-27: an odd per-agent 'outcome' in ONE domain-kill answer must not stop the fleet halt for the later domains.

_domain_outcomes did `outcome in counts` (a dict), which raises TypeError for an unhashable outcome (a list or an
object), and fleet_halt called it with no guard inside the sequential per-domain loop: the HTTP answer was a 500 and every
later domain was never sent its kill. A non-string outcome now counts as an error with a fixed text, and anything else
unexpected in one domain's answer records that domain as ok=false and the loop continues."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ops_console import api as api_mod
from ops_console.api import ServiceClient, create_app

HALT = {"operator": "CISO", "reason": "s12-27", "confirm": "HALT", "domains": ["alpha", "beta", "gamma"]}
GOOD = {"killed": ["a"], "results": [{"agent_id": "a", "outcome": "killed"}]}


class _Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


class _Kill:
    """The kill-switch: domain -> (status, body). Records every domain it was sent."""

    def __init__(self, answers):
        self.answers, self.sent = answers, []

    def post(self, path, json=None, **kw):
        domain = path.rsplit("/", 1)[-1]
        self.sent.append(domain)
        return self.answers[domain]


def _console(kill):
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    app = create_app(registry=dead, ledger=dead, killswitch=kill, delegation=dead, governor=dead, sentinel=dead,
                     lifecycle=dead, attest=dead, crosswalk=dead, federation=dead, replay=dead, gateway=dead)
    return TestClient(app)


@pytest.mark.parametrize("outcome", [["x"], {}, {"k": "v"}, [], 7, None, 1.5, True],
                         ids=["list", "dict", "dict-kv", "empty-list", "int", "null", "float", "bool"])
def test_an_odd_outcome_is_an_error_and_every_later_domain_is_still_killed(outcome):
    kill = _Kill({"alpha": (200, {"results": [{"agent_id": "a", "outcome": outcome}]}),
                  "beta": (200, GOOD), "gamma": (200, GOOD)})
    r = _console(kill).post("/api/fleet/halt", json=HALT)
    assert r.status_code == 200
    assert kill.sent == ["alpha", "beta", "gamma"]
    body = r.json()
    by = {d["domain"]: d for d in body["results"]}
    assert by["alpha"]["ok"] is False and by["alpha"]["counts"]["error"] == 1
    assert by["beta"]["ok"] is True and by["gamma"]["ok"] is True
    assert body["all_ok"] is False and body["domains_failed"] == 1 and body["agent_errors"] == 1


def test_a_non_string_outcome_is_listed_with_fixed_text_that_does_not_echo_it():
    counts, errors = api_mod._domain_outcomes({"results": [{"agent_id": "a", "outcome": ["SECRET-NESTED"]}]})
    assert counts["error"] == 1
    assert errors == [{"agent_id": "a", "error": "outcome is not a string"}]


def test_an_error_text_from_the_kill_switch_is_still_preferred():
    _, errors = api_mod._domain_outcomes({"results": [{"agent_id": "a", "outcome": ["x"], "error": "registry 401"}]})
    assert errors == [{"agent_id": "a", "error": "registry 401"}]


def test_known_and_unknown_string_outcomes_are_unchanged():
    counts, errors = api_mod._domain_outcomes({"results": [
        {"agent_id": "a", "outcome": "killed"}, {"agent_id": "b", "outcome": "mystery"},
        {"agent_id": "c", "outcome": "error", "error": "boom"}, "not-a-dict"]})
    assert counts["killed"] == 1 and counts["error"] == 3
    assert [e["agent_id"] for e in errors] == ["b", "c", None]
    assert errors[0]["error"] == "outcome 'mystery'"


def test_an_unexpected_failure_in_one_domains_answer_is_that_domain_failed_and_the_loop_continues(monkeypatch):
    real = api_mod._domain_outcomes

    def flaky(data):
        if data == {"boom": 1}:
            raise RuntimeError("unexpected SECRET-INTERNAL")
        return real(data)

    monkeypatch.setattr(api_mod, "_domain_outcomes", flaky)
    kill = _Kill({"alpha": (200, {"boom": 1}), "beta": (200, GOOD), "gamma": (200, GOOD)})
    r = _console(kill).post("/api/fleet/halt", json=HALT)
    assert r.status_code == 200 and kill.sent == ["alpha", "beta", "gamma"]
    by = {d["domain"]: d for d in r.json()["results"]}
    assert by["alpha"]["ok"] is False and by["beta"]["ok"] is True and by["gamma"]["ok"] is True
    assert by["alpha"]["error"] == "the kill-switch answer for this domain could not be read"
    assert "SECRET-INTERNAL" not in r.text
    assert r.json()["all_ok"] is False


def test_a_normal_halt_is_unchanged():
    kill = _Kill({d: (200, GOOD) for d in ("alpha", "beta", "gamma")})
    body = _console(kill).post("/api/fleet/halt", json=HALT).json()
    assert body["all_ok"] is True and body["domains_failed"] == 0 and body["agent_errors"] == 0
