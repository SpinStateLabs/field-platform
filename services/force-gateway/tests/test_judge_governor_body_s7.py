"""S7-31: a governor 200 whose body is not a JSON object counts judge_bypassed.governor_error, it does not trip bypass.

`_maybe_judge` read `resp.json().get("state")` outside any guard, but inside the request's instrumentation try, so a
governor /status answer that was non-JSON, a list or a string raised, `_enter_bypass("instrumentation_fault")` ran, and
the gateway sent a cooldown of requests uninstrumented while the real cause stayed hidden. Traffic always flowed (fail
open); what was wrong was the miscount and the bypass. The 404, non-200 and transport branches already count their own
reason, and `state == "BLOCK"` (budget) is unchanged."""

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream
from force_gateway.hygiene_judge import MockHygieneJudge
from force_gateway.store import GatewayStore

from test_gateway_delta import FakeLedger


class Resp:
    def __init__(self, status=200, body=None, bad_json=False, with_status=True):
        if with_status:
            self.status_code = status
        self._body, self._bad = body, bad_json

    def json(self):
        if self._bad:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._body


class Governor:
    def __init__(self, resp):
        self.resp, self.posts = resp, []

    def get(self, path):
        return self.resp

    def post(self, path, json=None):
        self.posts.append((path, json))
        return Resp(201, {})


_n = [0]


def run(resp, tmp_path):
    gov = Governor(resp)
    _n[0] += 1
    app = create_app(upstream=mock_upstream, governor_client=gov, hygiene_judge=MockHygieneJudge(),
                     ledger_client=FakeLedger(), sample_every=1, latency_budget_ms=10_000.0,
                     store=GatewayStore(tmp_path / f"gw{_n[0]}.sqlite3"))
    r = TestClient(app).post("/v1/messages", json={"model": "m", "messages": []})
    assert r.status_code == 200, r.text            # the proxied call is never failed
    return app, gov


ODD = {
    "not-json": Resp(200, bad_json=True),
    "list": Resp(200, ["BLOCK"]),
    "string": Resp(200, "BLOCK"),
    "null": Resp(200, None),
    "number": Resp(200, 5),
}


@pytest.mark.parametrize("resp", list(ODD.values()), ids=list(ODD))
def test_a_governor_200_that_is_not_a_json_object_counts_governor_error_and_does_not_bypass(resp, tmp_path):
    app, gov = run(resp, tmp_path)
    cov = app.state.coverage
    assert cov["judge_bypassed"] == {"governor_error": 1}
    assert cov["bypass_entries"] == 0 and cov.get("bypass_reasons", {}) == {}
    assert app.state.bypass_remaining == 0
    assert gov.posts == [] or all(p[0] != "/usage" or p[1].get("note") != "gateway hygiene judgment" for p in gov.posts)
    assert cov.get("judged_samples", 0) == 0


def test_a_response_without_a_status_code_is_a_governor_error_not_a_crash(tmp_path):
    app, _ = run(Resp(with_status=False, body={"state": "OK"}), tmp_path)
    assert app.state.coverage["judge_bypassed"] == {"governor_error": 1}
    assert app.state.coverage["bypass_entries"] == 0


def test_the_existing_branches_are_unchanged(tmp_path):
    app, _ = run(Resp(200, {"state": "BLOCK"}), tmp_path)
    assert app.state.coverage["judge_bypassed"] == {"budget": 1}
    app, _ = run(Resp(404, {}), tmp_path)
    assert app.state.coverage["judge_bypassed"] == {"no_cap": 1}
    app, _ = run(Resp(500, {}), tmp_path)
    assert app.state.coverage["judge_bypassed"] == {"governor_error": 1}
    app, gov = run(Resp(200, {"state": "OK"}), tmp_path)
    assert app.state.coverage["judged_samples"] == 1 and app.state.coverage["judge_bypassed"] == {}
