"""S12-11: the 'ai' naming rule matches a token, not letters inside a name; a RETIRED agent does not make a match
'registered' (it is surfaced, naming the retired agent); the registered count stays the full count."""

from __future__ import annotations

import pytest

from agent_registry.discover import ACCOUNT_PATTERNS, discover, looks_like_automation, scan_service_accounts
from agent_registry.models import AgentRecord, AgentStatus

HEADER = "account,type,owner,notes\n"


def _rec(agent_id="old-bot", name="Old Bot", owner="Pat Owner", status=AgentStatus.ACTIVE):
    return AgentRecord(agent_id=agent_id, name=name, owner=owner, status=status)


@pytest.mark.parametrize("name", ["gmail.", "mail-relay", "kaitlyn", "maid", "email"])
def test_names_with_ai_inside_a_word_are_not_automation(name):
    assert not looks_like_automation(name)


@pytest.mark.parametrize("name", ["ai-pricing-experiment", "ai_summarizer", "team.ai-helper", "svc-x@ai.example"])
def test_ai_tokens_are_still_flagged(name):
    assert looks_like_automation(name)


@pytest.mark.parametrize("name", ["openai-key", "openai_worker", "bob@openai.com", "mlai_worker", "azure-openai-svc",
                                  "anthropic-prod", "x@ai.example", "x.ai.y", "genai.runner", "xai-key"])
def test_vendor_named_ai_accounts_are_still_flagged(name):
    """don.reviewer B1 on #1024: the ``ai`` anchor must not lose an AI vendor account typed as a user or left blank."""
    assert looks_like_automation(name)


@pytest.mark.parametrize("name", ["claude.martin", "gemini_ross", "mistral.jean", "mikhail-p"])
def test_a_person_whose_name_is_or_holds_a_vendor_word_is_not_flagged(name):
    assert not looks_like_automation(name)


def test_a_vendor_account_with_a_human_type_is_a_candidate():
    csv_text = HEADER + "openai-key,human,o@x.test,\n"
    cands, _ = scan_service_accounts(csv_text, [])
    assert [c.identifier for c in cands] == ["openai-key"]


def test_person_names_ending_in_ai_are_surfaced_for_review_exactly_as_on_main():
    """Known false positives (README, backlog): main flags kai_nakamura and rai-chu and so does the head."""
    csv_text = HEADER + "kai_nakamura,human,k@x.test,\nrai-chu,human,r@x.test,\nai-pricing-experiment,human,p@x.test,\n"
    cands, _ = scan_service_accounts(csv_text, [])
    assert [c.identifier for c in cands] == ["kai_nakamura", "rai-chu", "ai-pricing-experiment"]


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


# --- fail-open fix, strict form (PR 1024 advisory O1; controller rulings 2026-11-23) --------------------------------------
# ACCOUNT_PATTERNS is MAIN's rule. looks_like_automation = that rule on the folded name + whole-token AI vendor names, with
# NO exclusion. The DIFFERENTIAL test below proves it over a corpus: head_flagged is a SUPERSET of main_flagged with ZERO
# exclusions. Person names ending in -ai stay flagged (known false positives, backlog row).

import re  # noqa: E402

from agent_registry.discover import looks_like_automation  # noqa: E402

B = chr(92)            # a backslash, spelt this way so no tool re-escapes it

#: main's rule, copied literally from origin/main (aa7f84c8) discover.py: the reference of the differential test.
MAIN_RULE = re.compile(r"(^svc[-_.]|^bot[-_.]|[-_.]bot$|agent|automation|ai[-_.])", re.I)

#: AI-ish service names (the 1024 advisory's probe, wave2's realm/ARN forms, the Unicode forms).
SERVICE_NAMES = [
    "my-ai-bot", "AI_agent", "agentai", "openai-key", "bob@openai.com", "ai-runner", "svc-llm", "AI-Ops", "x.ai.y",
    "genai.runner", "vertexai-sa", "azureai-svc", "svc@vertexai.example", "h2oai-key", "c3ai-svc", "stabilityai-svc",
    "perplexityai-key", "togetherai-key", "fireworksai_key", "deepai-key", "jasperai-key", "scaleai-x", "metaai_bot",
    "chatai-runner", "myai-helper", "teamai.sync", "llamaai-x", "copilotai-svc", "OPENAI_API", "mistralai-svc",
    "cohereai_x", "langchain-ai-svc", "privateai.worker", "inworldai-key", "ai.example", "my_ai_svc", "bedrock-ai-runner",
    "rag2ai-job", "llm-ai_x", "prod1ai-x", "x@ai.example", "ai-pricing-experiment", "ai_summarizer",
    "team.ai-helper", "svc-x@ai.example", "openai_worker", "mlai_worker", "azure-openai-svc", "anthropic-prod", "xai-key",
    "kaia.ai.fan", "ai.chen", "xai.li",
    # service accounts the person-shaped exclusion of the previous head let through (wave2-engineer, re-measured on main)
    "chatai-prod@proj.iam.gserviceaccount.com", "moonshotai-etl", "teamai-prod", "dataai-etl", "corpai_ingest",
    "svcai-prod", "prodai-1", "CORP|chatai-prod", "CORP%5Cchatai-prod",
    # a vendor name INSIDE a fused token, no service word after it: not person-shaped
    "bedrockopenai-x", "fooperplexityai.q", "barmistralai_y",
    # realm / path / ARN forms (wave2, re-measured against main)
    "CORP" + B + "ai-runner", "arn:aws:iam::123456789012:role/ai-runner", "serviceAccount:ai-runner",
    "system:serviceaccount:prod:ai-runner", "CORP" + B + "kai_nakamura", "a/b/kai-x",
    # a non-ASCII letter before ai
    "\u00e9ai-svc", "\u00e9ai_x",
    # Unicode forms main's case-insensitive search caught
    "a\u0131-x", "A\u0130-x",
    # service words next to a person-looking token: flagged on purpose (a review queue prefers a false positive)
    "mai.job", "kai.sync", "lai_runner", "tsai.worker", "desai-key", "bhai.svc",
]

#: Person-looking names that main flags and the head flags too: KNOWN FALSE POSITIVES, kept flagged because a review queue
#: prefers a false positive; narrowing them is a backlog row (a closed stem list, wave2-engineer's direction).
KNOWN_FALSE_POSITIVES = {
    "kai_nakamura": "ai fused after k, then a surname",
    "rai-chu": "ai fused after r, then a surname",
    "jsmith@thai.example": "thai. in a mail domain, no service word",
    "shanghai.li": "shanghai. then a surname",
    "mai.tran": "mai. then a surname", "lai-x": "lai- then one letter", "tsai.wu": "tsai. then a surname",
    "tsai.ing-wen": "tsai. then a name", "desai-p": "desai- then an initial", "desai.r": "desai. then an initial",
    "bhai.k": "bhai. then an initial", "kai.smith": "kai. then a surname", "kai_s": "kai_ then an initial",
    "lai.wong": "lai. then a surname", "mai-t": "mai- then an initial", "mai.nguyen": "mai. then a surname",
    "tsai_c": "tsai_ then an initial", "desai-k": "desai- then an initial", "bhai_m": "bhai_ then an initial",
    "anjali.desai-nair": "desai- then a surname part", "li.tsai-chen": "tsai- then a surname part",
    "thai-food-co": "thai- then words", "mai.t": "mai. then an initial", "kai.l": "kai. then an initial",
    "p.desai-jones": "desai- then a surname",
    "kai-nguyen.mai-tran": "two person parts", "raj.bhai-patel": "bhai- then a surname",
}

#: Ordinary logins main does not flag either (no ai before a separator): must stay unflagged.
PEOPLE_NEVER_FLAGGED = [
    "kai", "lai", "mai", "tsai", "desai", "bhai", "kaitlyn", "aimee", "aisha", "aidan", "naim_ali", "mikhail-p", "maid",
    "paid", "email", "chair", "said", "gmail.", "mail-relay", "claude.martin", "gemini_ross", "mistral.jean",
    "deepaiyer", "sandeepaiyer", "jasperaiken", "philanthropic.lead", "taiwan.li", "hair.stylist", "hawaii.office",
]

#: Flagged by the head and not by main: whole-token AI vendor names (huggingface_token, Anthropic_Admin ...) and the
#: names the folding reveals. Listed so no new flag appears silently.
GAINS = ["huggingface_token", "Anthropic_Admin", "my-huggingface", "OPENAI", "openai", "vertexai", "anthropic-prod",
         "\uff41\uff49-bot2", "a\u200bi-runner", "\u200bopenai"]

CORPUS = SERVICE_NAMES + list(KNOWN_FALSE_POSITIVES) + PEOPLE_NEVER_FLAGGED + GAINS


def test_the_corpus_is_large():
    assert len(CORPUS) >= 100, len(CORPUS)


def test_the_head_flags_a_superset_of_what_main_flags_with_zero_exclusions():
    """The DIFFERENTIAL, strict form: for every name in the corpus, if main flags it the head flags it."""
    lost = sorted({n for n in CORPUS if MAIN_RULE.search(n) and not looks_like_automation(n)})
    assert lost == [], lost


@pytest.mark.parametrize("name", sorted(set(SERVICE_NAMES)))
def test_every_service_name_is_flagged(name):
    assert looks_like_automation(name), name.encode("unicode_escape")


@pytest.mark.parametrize("name", sorted(KNOWN_FALSE_POSITIVES))
def test_the_known_false_positives_are_flagged_as_on_main(name):
    assert KNOWN_FALSE_POSITIVES[name] and MAIN_RULE.search(name) and looks_like_automation(name), name


@pytest.mark.parametrize("name", PEOPLE_NEVER_FLAGGED)
def test_ordinary_logins_are_not_flagged(name):
    assert not looks_like_automation(name), name


@pytest.mark.parametrize("name", GAINS)
def test_the_listed_gains_are_flagged(name):
    assert looks_like_automation(name), name.encode("unicode_escape")


def test_no_name_outside_the_listed_gains_is_flagged_by_the_head_and_not_by_main():
    new = sorted({n for n in CORPUS if looks_like_automation(n) and not MAIN_RULE.search(n)})
    assert new == sorted(set(GAINS)), set(new) ^ set(GAINS)


@pytest.mark.parametrize("name", ["CORP" + B + "ai-runner", "arn:aws:iam::123456789012:role/ai-runner", "serviceAccount:ai-runner",
                                  "system:serviceaccount:prod:ai-runner", "\u00e9ai-svc", "prod1ai-x", "c3ai-svc", "ai.example"])
def test_a_path_realm_digit_or_non_ascii_prefix_never_hides_an_ai_account(name):
    """The shapes the third advisory re-measured: main flags them and so does the head."""
    assert MAIN_RULE.search(name) and looks_like_automation(name)


@pytest.mark.parametrize("name", ["mai.job", "kai.sync", "lai_runner", "tsai.worker"])
def test_a_person_looking_token_next_to_a_service_word_stays_flagged(name):
    """README: mai.job and kai.sync stay flagged, a review queue prefers a false positive."""
    assert looks_like_automation(name)


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
    csv_text = HEADER + "".join(f"{n},human,o@x.test,\n" for n in ["claude.martin", "aimee", "kaitlyn", "mikhail-p"])
    assert scan_service_accounts(csv_text, [])[0] == []


#: The 21 vendor tokens, spelt out here (not read back from the module, or dropping one would shrink the test too).
VENDORS = ("openai", "anthropic", "huggingface", "geminiai", "mistralai", "cohereai", "vertexai", "azureai", "stabilityai",
           "perplexityai", "togetherai", "fireworksai", "deepai", "jasperai", "scaleai", "llamaai", "copilotai", "xai", "genai",
           "mlai", "metaai")


@pytest.mark.parametrize("vendor", VENDORS)
@pytest.mark.parametrize("form", ["{v}", "{v}-x", "{v}_q", "svc-{v}", "{v}.q", "{V}-Q"])
def test_every_listed_vendor_token_is_flagged_in_every_position(vendor, form):
    """All 21 vendor tokens, not a sample: bare, with a separator and one letter, prefixed, upper-case."""
    assert looks_like_automation(form.format(v=vendor, V=vendor.upper())), form.format(v=vendor, V=vendor.upper())


def test_the_module_lists_at_least_these_vendor_tokens():
    from agent_registry.discover import _AI_VENDOR_TOKENS
    assert set(VENDORS) <= set(_AI_VENDOR_TOKENS)
