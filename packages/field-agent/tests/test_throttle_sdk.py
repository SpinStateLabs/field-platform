"""D1 SDK half: ``ActionBlocked.retry_after``, ``report_spend(action=...)``
feeding the governor's per-action window, THROTTLED surfaced on
``SpendStatusLite``, and ``fieldagent check`` on a rate-limited BLOCK."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import field_agent.cli as cli_mod
from conformance_sentinel.engine import SpendStatusClient
from field_agent import ActionBlocked
from field_agent._transport import AuthedClient
from field_agent.usage import UsageClient
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore
from tests.conftest import AGENT_ID

T0 = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def fstack(stack, tmp_path):
    """The SDK stack with a frozen-clock governor (exact retry_after)."""
    store = GovernorStore(tmp_path / "spend-frozen.sqlite3")
    stack.governor = TestClient(create_governor_app(store=store, clock=lambda: T0))
    stack.sentinel.app.state.engine.governor = SpendStatusClient(
        client=AuthedClient(stack.governor), base_url="http://t")
    yield stack
    store.close()


def _limit(stack, action="draft invoices", max_=2, period="hourly"):
    r = stack.governor.put(f"/rate-limits/{AGENT_ID}", json={
        "agent_id": AGENT_ID, "rate_limits": [{"action": action, "max": max_, "period": period}]})
    assert r.status_code == 200, r.text


def test_action_blocked_retry_after_equals_the_governors_value(fstack):
    fstack.set_cap()
    _limit(fstack)
    agent = fstack.make_agent(token_id=fstack.mint_token())
    ran = []

    @agent.governed("draft invoices")
    def draft():
        ran.append(1)

    draft()
    draft()
    with pytest.raises(ActionBlocked) as caught:
        draft()
    assert ran == [1, 1]  # the rate-limited body never ran
    governor = fstack.governor.get(f"/status/{AGENT_ID}",
                                   params={"action": "draft invoices"}).json()
    assert governor["state"] == "THROTTLED"
    assert caught.value.verdict["clause_id"] == "E.rate_limit"
    assert caught.value.retry_after == governor["retry_after_seconds"] == 3600


def test_report_spend_action_feeds_the_window_and_surfaces_throttled(fstack):
    fstack.set_cap()
    _limit(fstack, max_=3)
    agent = fstack.make_agent()
    first = agent.report_spend(cents=10, actions=2, action="draft invoices")
    assert first.state == "OK" and first.retry_after_seconds is None
    second = agent.report_spend(cents=10, actions=1, action="draft invoices")
    assert second.state == "THROTTLED"
    assert second.retry_after_seconds == 3600
    # an unattributed self-report never feeds the per-action window
    other = fstack.make_agent()
    assert other.report_spend(cents=1, actions=9).retry_after_seconds is None


def test_self_reported_action_window_blocks_the_next_check(fstack):
    fstack.set_cap()
    _limit(fstack, max_=1)
    agent = fstack.make_agent(token_id=fstack.mint_token())
    agent.report_spend(actions=1, action="draft invoices")
    with pytest.raises(ActionBlocked) as caught:
        agent.check("draft invoices")
    assert caught.value.retry_after == 3600


class _Spy:
    def __init__(self):
        self.bodies = []

    def post(self, url, json=None, headers=None):
        self.bodies.append(json)

        class R:
            status_code = 201

            @staticmethod
            def json():
                return {"agent_id": AGENT_ID, "state": "OK"}

        return R()


def test_report_spend_omits_action_when_unset_for_pre_d1_governors():
    spy = _Spy()
    client = UsageClient(client=spy, base_url="http://t")
    client.spend(AGENT_ID, cents=5)
    client.spend(AGENT_ID, cents=5, action="draft invoices")
    assert "action" not in spy.bodies[0]
    assert spy.bodies[1]["action"] == "draft invoices"


def test_cli_check_rate_limited_block_prints_retry_after_and_exits_1(fstack, monkeypatch):
    fstack.set_cap()
    _limit(fstack, max_=1)
    token = fstack.mint_token()
    monkeypatch.setattr(cli_mod, "FieldAgent",
                        lambda agent_id, token_id=None: fstack.make_agent(token_id=token_id))
    runner = CliRunner()
    ok = runner.invoke(cli_mod.app, ["check", AGENT_ID, "draft invoices", "--token-id", token])
    assert ok.exit_code == 0, ok.output
    assert "retry_after_seconds:" not in ok.stderr
    blocked = runner.invoke(cli_mod.app, ["check", AGENT_ID, "draft invoices",
                                          "--token-id", token])
    assert blocked.exit_code == 1
    assert '"E.rate_limit"' in blocked.stdout
    assert "retry_after_seconds: 3600" in blocked.stderr
    scope = runner.invoke(cli_mod.app, ["check", AGENT_ID, "transfer funds", "--token-id", token])
    assert scope.exit_code == 1 and "retry_after_seconds:" not in scope.stderr
