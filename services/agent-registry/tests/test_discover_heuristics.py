"""S12-11: the 'ai' naming rule matches a token, not letters inside a name; a RETIRED agent does not make a match
'registered' (it is surfaced, naming the retired agent); the registered count stays the full count."""

from __future__ import annotations

import pytest

from agent_registry.discover import ACCOUNT_PATTERNS, discover, scan_service_accounts
from agent_registry.models import AgentRecord, AgentStatus

HEADER = "account,type,owner,notes\n"


def _rec(agent_id="old-bot", name="Old Bot", owner="Pat Owner", status=AgentStatus.ACTIVE):
    return AgentRecord(agent_id=agent_id, name=name, owner=owner, status=status)


@pytest.mark.parametrize("name", ["kai_nakamura", "rai-chu", "jsmith@thai.example", "gmail.", "mail-relay"])
def test_human_names_are_not_automation(name):
    assert not ACCOUNT_PATTERNS.search(name)


@pytest.mark.parametrize("name", ["ai-pricing-experiment", "ai_summarizer", "team.ai-helper", "svc-x@ai.example"])
def test_ai_tokens_are_still_flagged(name):
    assert ACCOUNT_PATTERNS.search(name)


def test_humans_with_ai_inside_the_name_are_not_candidates():
    csv_text = HEADER + "kai_nakamura,human,k@x.test,\nrai-chu,human,r@x.test,\nai-pricing-experiment,human,p@x.test,\n"
    cands, _ = scan_service_accounts(csv_text, [])
    assert [c.identifier for c in cands] == ["ai-pricing-experiment"]


def _by_id(report):
    return {c.identifier: c for c in report.candidates}


def test_a_retired_agent_does_not_hide_a_service_account():
    csv_text = HEADER + "old-bot,service,p@x.test,\n"
    live = discover([_rec()], accounts_csv=csv_text)
    assert live.candidates == []
    gone = discover([_rec(status=AgentStatus.RETIRED)], accounts_csv=csv_text)
    c = _by_id(gone)["old-bot"]
    assert "matches retired agent 'old-bot'" in c.reason
    assert gone.registered_agents == 1


def test_a_retired_agent_does_not_hide_an_n8n_workflow():
    wf = {"id": "wf-1", "name": "Old Bot", "nodes": [{"name": "A", "type": "@n8n/n8n-nodes-langchain.agent"}]}
    assert discover([_rec()], n8n_export=wf).candidates == []
    gone = discover([_rec(status=AgentStatus.RETIRED)], n8n_export=wf)
    assert "matches retired agent 'old-bot'" in _by_id(gone)["wf-1"].reason
    assert gone.registered_agents == 1


def test_a_retired_agents_owner_does_not_make_an_api_key_known():
    keys = "key_name,owner,service,created,last_used\nk1,Pat Owner,s,2026-01-01,2026-02-01\n"
    assert discover([_rec()], api_keys_csv=keys).candidates == []
    gone = discover([_rec(status=AgentStatus.RETIRED)], api_keys_csv=keys)
    c = _by_id(gone)["k1"]
    assert "owner is not a registered agent's owner" in c.reason
    assert "matches retired agent 'old-bot'" in c.reason
    assert gone.registered_agents == 1


def test_a_killed_agent_is_still_registered():
    csv_text = HEADER + "old-bot,service,p@x.test,\n"
    assert discover([_rec(status=AgentStatus.KILLED)], accounts_csv=csv_text).candidates == []
