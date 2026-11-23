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


@pytest.mark.parametrize("name", ["openai-key", "openai_worker", "bob@openai.com", "mlai_worker", "azure-openai-svc",
                                  "anthropic-prod", "x@ai.example", "x.ai.y", "genai.runner", "xai-key"])
def test_vendor_named_ai_accounts_are_still_flagged(name):
    """don.reviewer B1 on #1024: the ``ai`` anchor must not lose an AI vendor account typed as a user or left blank."""
    assert ACCOUNT_PATTERNS.search(name)


@pytest.mark.parametrize("name", ["claude.martin", "gemini_ross", "mistral.jean", "shanghai.li", "mikhail-p"])
def test_a_person_whose_name_is_or_holds_a_vendor_word_is_not_flagged(name):
    assert not ACCOUNT_PATTERNS.search(name)


def test_a_vendor_account_with_a_human_type_is_a_candidate():
    csv_text = HEADER + "openai-key,human,o@x.test,\n"
    cands, _ = scan_service_accounts(csv_text, [])
    assert [c.identifier for c in cands] == ["openai-key"]


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


# --- fail-open fix (PR 1024 advisory O1; controller ruling 2026-11-23) -----------------------------------------------------
# The scanner must not flag FEWER names than main. Every name below is one main's unanchored ``ai[-_.]`` flagged (plus the
# Unicode forms main's case-insensitive search caught); each must still be flagged, except the names in LEFT_UNFLAGGED,
# which are left out on purpose and listed with the reason. Source: 50 hand-picked names probed by the 1024 advisory.

from agent_registry.discover import looks_like_automation  # noqa: E402

FLAGGED_ON_MAIN = [
    "my-ai-bot", "AI_agent", "agentai", "openai-key", "bob@openai.com", "ai-runner", "svc-llm", "AI-Ops", "x.ai.y",
    "genai.runner", "vertexai-sa", "azureai-svc", "svc@vertexai.example", "h2oai-key", "c3ai-svc", "stabilityai-svc",
    "perplexityai-key", "togetherai-key", "fireworksai_key", "deepai-key", "jasperai-key", "scaleai-x", "metaai_bot",
    "chatai-runner", "myai-helper", "teamai.sync", "llamaai-x", "copilotai-svc", "OPENAI_API", "mistralai-svc",
    "cohereai_x", "langchain-ai-svc", "privateai.worker", "inworldai-key", "ai.example", "my_ai_svc", "bedrock-ai-runner",
    "rag2ai-job", "llm-ai_x",
    "a\u0131-x",              # dotless i: the case-insensitive search folds it to i
    "A\u0130-x",              # capital I with dot above
    "open\u200bai-key",       # a zero-width space inside "openai": the format character is stripped before matching
]

#: Flagged on main, deliberately NOT flagged now. A fused ``ai`` followed only by the single letter x is
#: indistinguishable from a person's name (lai-x, kai-x), and ``prod1ai`` is not a vendor word.
LEFT_UNFLAGGED = {"prod1ai-x": "fused 'ai' + a one-letter suffix: the same shape as the person lai-x"}

PEOPLE_NOT_FLAGGED = ["kai_nakamura", "rai-chu", "jsmith@thai.example", "shanghai.li", "mai.tran", "lai-x", "claude.martin",
                      "gemini_ross", "mistral.jean", "mikhail-p", "aimee", "naim_ali", "maid", "paid", "email", "chair",
                      "said", "gmail.", "mail-relay"]


@pytest.mark.parametrize("name", [n for n in FLAGGED_ON_MAIN])
def test_every_name_main_flagged_is_still_flagged(name):
    assert looks_like_automation(name), name


@pytest.mark.parametrize("name,why", sorted(LEFT_UNFLAGGED.items()))
def test_the_deliberately_unflagged_names_are_exactly_the_listed_ones(name, why):
    assert why and not looks_like_automation(name)
    assert name not in FLAGGED_ON_MAIN


@pytest.mark.parametrize("name", PEOPLE_NOT_FLAGGED)
def test_people_stay_unflagged(name):
    assert not looks_like_automation(name), name


@pytest.mark.parametrize("name", ["\uff41\uff49-bot2", "\uff4f\uff50\uff45\uff4e\uff41\uff49-key", "a\u200bi-runner",
                                  "\u212aai-svc", "open\u00adai-key", "\u200bopenai"])
def test_nfkc_and_format_characters_are_folded_before_matching(name):
    """Full-width letters, the Kelvin sign, a zero-width space and a soft hyphen (category Cf) cannot hide a name."""
    assert looks_like_automation(name), name.encode("unicode_escape")


@pytest.mark.parametrize("name", ["aimee", "aisha", "aidan", "aiden", "ainsley_k", "aileen.o", "aiko-s"])
def test_ai_followed_directly_by_letters_is_a_name_not_a_token(name):
    """Pins the mutant that makes the separator after ``ai`` optional (aimee, aisha ... would become automation)."""
    assert not looks_like_automation(name) and not ACCOUNT_PATTERNS.search(name)


@pytest.mark.parametrize("name", ["OPENAI_API", "Anthropic_Admin", "VERTEXAI-SA", "HuggingFace-sa", "Svc-Bot", "KAI-KEY"])
def test_the_match_is_case_insensitive(name):
    """Pins the mutant that drops re.I: an upper-case vendor name would escape (fail-open)."""
    assert looks_like_automation(name)


@pytest.mark.parametrize("name", ["huggingface_token", "huggingface-hub", "my-huggingface", "HuggingFace"])
def test_huggingface_is_a_vendor_word(name):
    """Pins the mutant that removes ``huggingface`` from the vendor words."""
    assert looks_like_automation(name)


def test_the_reason_and_evidence_carry_no_scanned_text_and_no_secret():
    fake = "ghp_" + "A1b2C3d4E5" * 3 + "A1b2C3"                       # made up, token-shaped
    csv_text = HEADER + f"svc-{fake},service,owner-{fake}@x.test,note {fake}\n"
    live = scan_service_accounts(csv_text, [])[0]
    retired = discover([_rec(agent_id="svc-other", name="Other", status=AgentStatus.RETIRED)], accounts_csv=csv_text).candidates
    for c in list(live) + list(retired):
        assert fake not in c.reason and "A1b2C3d4" not in c.reason, c.reason
        assert "A1b2C3d4" not in repr(c.model_dump()), c.model_dump()
    assert live[0].reason == "automation-pattern account matches no registered agent"


@pytest.mark.parametrize("account", ["open\u200bai-key", "\uff41\uff49-bot2", "vertexai-sa", "OPENAI_API"])
def test_the_scanner_itself_surfaces_the_folded_and_fused_names(account):
    """Through scan_service_accounts, not only the helper: a human-typed (or blank-typed) account with a hidden vendor name
    is a candidate and keeps its raw identifier."""
    cands, _ = scan_service_accounts(HEADER + f"{account},human,o@x.test,\n", [])
    assert [c.identifier for c in cands] == [account]


def test_the_scanner_does_not_surface_people():
    csv_text = HEADER + "".join(f"{n},human,o@x.test,\n" for n in ["kai_nakamura", "lai-x", "claude.martin", "aimee"])
    assert scan_service_accounts(csv_text, [])[0] == []
