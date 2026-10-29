"""C-168 (reviewer C-157 F-C157-1/-2): the fail-closed branches that keep an upstream error from
becoming ALLOW, the irreversible `forbid` and `allow_with_ledger` policies, and the judge floor
boundary.

Every error answer below carries a JSON body that WOULD pass if the status were ignored (an active
agent, an active in-scope token, a cap in state OK), so a client that stops checking the status
turns the verdict to ALLOW and the test red."""

from __future__ import annotations

import pytest
import yaml

from tests.conftest import AGENT_ID, SCOPE
from tests.test_judge import _arm

ERROR_STATUSES = [400, 401, 403, 500, 502, 503]
OK_SPEND = {"state": "OK", "detail": "", "period": "daily"}
PARAPHRASE = "draft the march invoices"


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class Http:
    """An httpx-like client: ``routes`` maps (METHOD, path prefix) to ``(status, body)``."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _answer(self, method, url):
        self.calls.append((method, url))
        for (m, prefix), (status, body) in self.routes.items():
            if m == method and prefix in url:
                return Resp(status, body)
        return Resp(404, {"detail": "no route"})

    def get(self, url, params=None, **kw):
        return self._answer("GET", url)

    def post(self, url, json=None, **kw):
        return self._answer("POST", url)


def engine(stack):
    return stack.sentinel.app.state.engine


def use_governor(stack, routes):
    http = Http(routes)
    engine(stack).governor._client = http
    return http


def check(stack, token="tok", action="draft invoices", **kw):
    return stack.check(action, token_id=token, **kw)


def intro(**over):
    body = {"active": True, "status": "active", "agent_id": AGENT_ID, "scope": list(SCOPE)}
    body.update(over)
    return body


# --- F-C157-1: governor errors ------------------------------------------------------------


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_a_governor_error_answer_on_status_is_block_spend_cap(stack, status):
    token = stack.mint_token()
    use_governor(stack, {("GET", "/status/"): (status, OK_SPEND)})
    v = check(stack, token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert f"governor returned {status}" in " ".join(v["reasons"])


def test_a_healthy_governor_answer_still_allows(stack):
    token = stack.mint_token()
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/spend"): (201, {})})
    assert check(stack, token)["decision"] == "ALLOW"


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_a_governor_error_on_totals_blocks_a_token_with_a_ceiling(stack, status):
    stack.mint_token()
    engine(stack).delegation._client = Http({("POST", "/introspect"): (200, intro(
        max_spend_usd=100, issued_at="2026-01-01T00:00:00+00:00"))})
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND),
                         ("GET", "/totals/"): (status, {"currency": "USD", "spent_cents": 0})})
    v = check(stack)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert f"governor /totals returned {status}" in " ".join(v["reasons"])


def test_a_totals_answer_that_is_fine_lets_a_token_with_a_ceiling_through(stack):
    stack.mint_token()
    engine(stack).delegation._client = Http({("POST", "/introspect"): (200, intro(
        max_spend_usd=100, issued_at="2026-01-01T00:00:00+00:00"))})
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/spend"): (201, {}),
                         ("GET", "/totals/"): (200, {"currency": "USD", "spent_cents": 0})})
    assert check(stack)["decision"] == "ALLOW"


@pytest.mark.parametrize("status", [200, 400, 401, 403, 500, 503])
def test_a_metering_post_that_is_not_201_is_a_gap_and_never_changes_the_verdict(stack, status):
    token = stack.mint_token()
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND),
                         ("POST", "/spend"): (status, {"state": "OK"})})
    v = check(stack, token)
    assert v["decision"] == "ALLOW"
    assert v["context"]["metered"] is False and v["context"]["reason"] == "metering_gap"
    [gap] = stack.ledger.get("/events", params={"event_type": "sentinel.metering_gap"}).json()
    assert f"governor /spend returned {status}" in gap["payload"]["error"]


def test_a_201_metering_post_is_metered_and_a_404_is_no_cap(stack):
    token = stack.mint_token()
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/spend"): (201, {})})
    assert check(stack, token)["context"]["metered"] is True
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/spend"): (404, {})})
    v = check(stack, token)
    assert v["context"]["metered"] is False and v["context"]["reason"] == "no_cap"


@pytest.mark.parametrize("status", [200, 400, 401, 403, 500, 503])
def test_an_unmeterable_judgment_escalates(stack, status):
    token = stack.mint_token()
    _arm(stack, rules={PARAPHRASE: (True, 0.95, "paraphrase of 'draft invoices'")})
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND),
                         ("POST", "/usage"): (status, {"ok": True})})
    v = check(stack, token, action=PARAPHRASE)
    assert v["decision"] == "ESCALATE" and v["clause_id"] == "D.semantic"
    assert f"governor /usage returned {status}" in " ".join(v["reasons"])


def test_a_metered_judgment_goes_through(stack):
    token = stack.mint_token()
    _arm(stack, rules={PARAPHRASE: (True, 0.95, "paraphrase of 'draft invoices'")})
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/usage"): (201, {}),
                         ("POST", "/spend"): (201, {})})
    assert check(stack, token, action=PARAPHRASE)["decision"] == "ALLOW"


# --- delegation and registry errors -------------------------------------------------------


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_a_delegation_error_answer_is_block_d_token(stack, status):
    stack.mint_token()
    stack.set_cap()
    engine(stack).delegation._client = Http({("POST", "/introspect"): (status, intro())})
    v = check(stack)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.token"
    assert f"delegation returned {status}" in " ".join(v["reasons"])


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_a_registry_error_answer_is_a_block_never_an_allow(stack, status):
    token = stack.mint_token()
    stack.set_cap()
    active = {"agent_id": AGENT_ID, "status": "active", "manifest_ref": str(stack.manifest_path)}
    engine(stack).registry._client = Http({("GET", "/agents/"): (status, active)})
    v = check(stack, token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.unregistered"
    assert f"registry returned {status}" in " ".join(v["reasons"])


# --- F-C157-2: irreversible policies ------------------------------------------------------


def set_policy(stack, policy):
    data = yaml.safe_load(stack.manifest_path.read_text(encoding="utf-8"))
    data["enforcement"]["irreversible_action_policy"] = policy
    stack.manifest_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize(("policy", "decision", "clause"), [
    ("forbid", "BLOCK", "E.irreversible"),
    ("require_human_approval", "ESCALATE", "E.irreversible"),
    ("allow_with_ledger", "ALLOW", None)])
def test_an_irreversible_action_follows_the_manifest_policy(stack, policy, decision, clause):
    stack.set_cap()
    token = stack.mint_token()
    set_policy(stack, policy)
    v = stack.check("draft invoices", token_id=token, irreversible=True)
    assert (v["decision"], v["clause_id"]) == (decision, clause)
    assert v["context"]["irreversible"] is True


@pytest.mark.parametrize("policy", ["forbid", "require_human_approval", "allow_with_ledger"])
def test_a_reversible_action_ignores_the_policy(stack, policy):
    stack.set_cap()
    token = stack.mint_token()
    set_policy(stack, policy)
    assert stack.check("draft invoices", token_id=token)["decision"] == "ALLOW"


def test_forbid_blocks_before_a_trigger_or_spend_check_can_escalate(stack):
    """The irreversible step sits before the trigger match: `send invoice email` is a trigger
    (ESCALATE) but under `forbid` an irreversible one is a BLOCK."""
    stack.set_cap()
    token = stack.mint_token()
    set_policy(stack, "forbid")
    v = stack.check("send invoice email", token_id=token, irreversible=True)
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "E.irreversible")


# --- judge floor boundary -----------------------------------------------------------------


def test_a_conforming_judgment_exactly_at_the_floor_allows(stack):
    floor = engine(stack).judge_floor
    _arm(stack, rules={PARAPHRASE: (True, floor, "at the floor")})
    assert stack.check(PARAPHRASE, token_id=stack.mint_token())["decision"] == "ALLOW"


def test_a_non_conforming_judgment_exactly_at_the_floor_blocks(stack):
    floor = engine(stack).judge_floor
    _arm(stack, rules={PARAPHRASE: (False, floor, "at the floor")})
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert (v["decision"], v["clause_id"]) == ("BLOCK", "D.scope")


@pytest.mark.parametrize("conforming", [True, False])
def test_a_judgment_just_below_the_floor_escalates(stack, conforming):
    floor = engine(stack).judge_floor
    _arm(stack, rules={PARAPHRASE: (conforming, floor - 0.01, "just below")})
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert (v["decision"], v["clause_id"]) == ("ESCALATE", "D.semantic")
