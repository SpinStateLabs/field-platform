"""S8-24 — direct pins for routing.needs_semantic_judgment and its tokenizer. The predicate gates which
actions reach the LLM judge (engine.py), and only the seeded-corpus loop in test_scorecard touched it, so
its edge cases were unpinned. Tests only; current behaviour is pinned, including the ASCII-only tokenizer
(a defect-shaped limit recorded in the PR, not changed here)."""

from __future__ import annotations

import pytest

from conformance_sentinel.routing import _STOPWORDS, _WORD, _content_tokens, needs_semantic_judgment

SCOPE = ["read timesheets", "draft invoices", "send invoice email"]


# --- the predicate -----------------------------------------------------------------------------------

def test_an_exact_scope_member_is_not_routed():
    assert needs_semantic_judgment("draft invoices", SCOPE) is False


def test_a_shared_content_word_with_a_non_member_is_routed():
    assert needs_semantic_judgment("draft report", SCOPE) is True       # shares 'draft'
    assert needs_semantic_judgment("send money", SCOPE) is True         # shares 'send'


def test_no_shared_vocabulary_is_a_plain_breach_not_routed():
    assert needs_semantic_judgment("delete database", SCOPE) is False


@pytest.mark.parametrize("action", ["the of", "a an and for from of or the to with", "of the", "To"])
def test_stopword_only_actions_are_not_routed(action):
    assert needs_semantic_judgment(action, SCOPE) is False


def test_stopword_only_overlap_does_not_route():
    """'the'/'of' appear in the scope entry and in the action, but they are not content words."""
    assert needs_semantic_judgment("end of the day", ["start of the day"]) is True   # 'day' is shared
    assert needs_semantic_judgment("the of", ["the of"]) is False                    # exact member
    assert needs_semantic_judgment("of the", ["the of"]) is False                    # stopwords only


@pytest.mark.parametrize("action", ["", "   ", "!!!", "---"])
def test_an_empty_or_symbol_only_action_is_not_routed(action):
    assert needs_semantic_judgment(action, SCOPE) is False


def test_an_empty_scope_routes_nothing():
    assert needs_semantic_judgment("draft report", []) is False
    assert needs_semantic_judgment("", []) is False


@pytest.mark.parametrize("action", ["Draft Invoices", "DRAFT INVOICES", "dRaFt report"])
def test_case_differences_route_when_not_an_exact_member(action):
    assert needs_semantic_judgment(action, SCOPE) is True


def test_membership_is_exact_and_case_sensitive():
    assert needs_semantic_judgment("draft invoices ", SCOPE) is True    # trailing space: not a member
    assert needs_semantic_judgment("Draft Invoices", ["Draft Invoices"]) is False


def test_punctuation_splits_tokens():
    assert needs_semantic_judgment("draft-report", SCOPE) is True
    assert needs_semantic_judgment("draft;report!", SCOPE) is True


def test_digits_count_as_content():
    assert needs_semantic_judgment("export q3", ["run q3 report"]) is True
    assert needs_semantic_judgment("export q4", ["run q3 report"]) is False


def test_a_generator_scope_is_consumed_once_without_error():
    def gen():
        yield from SCOPE
    assert needs_semantic_judgment("draft report", gen()) is True
    assert needs_semantic_judgment("draft invoices", gen()) is False
    assert needs_semantic_judgment("delete database", iter(SCOPE)) is False


def test_the_scope_is_not_mutated():
    scope = list(SCOPE)
    needs_semantic_judgment("draft report", scope)
    assert scope == SCOPE


# --- the tokenizer -----------------------------------------------------------------------------------

def test_the_tokenizer_constants():
    assert _WORD.pattern == "[a-z0-9]+"
    assert _STOPWORDS == frozenset({"a", "an", "and", "for", "from", "of", "or", "the", "to", "with"})


@pytest.mark.parametrize("text, want", [
    ("Draft Invoices", {"draft", "invoices"}),
    ("draft-invoices; v2", {"draft", "invoices", "v2"}),
    ("DRAFT_invoices2", {"draft", "invoices2"}),        # underscore is a separator, digits stay in the word
    ("the of", set()),
    ("", set()),
    ("send the invoice to a client", {"send", "invoice", "client"}),
])
def test_content_tokens(text, want):
    assert _content_tokens(text) == frozenset(want)


# --- the ASCII-only tokenizer (pinned as it is) ------------------------------------------------------

def test_a_cyrillic_action_has_no_tokens_and_is_never_routed():
    assert _content_tokens("Создать счета") == frozenset()
    # a non-member Cyrillic paraphrase never reaches the judge, even against a Cyrillic scope entry
    assert needs_semantic_judgment("Создать", ["Создать счета"]) is False
    # ... but an exact member is still the exact-membership answer (False)
    assert needs_semantic_judgment("Создать счета", ["Создать счета"]) is False


def test_an_accented_word_splits_at_the_accent():
    """'créer' is 'cr' + 'er': the accented letter is not in [a-z0-9] and separates tokens."""
    assert _content_tokens("créer des factures") == frozenset({"cr", "er", "des", "factures"})
    assert _content_tokens("tö send") == frozenset({"t", "send"})


def test_accent_fragments_can_route_unrelated_french_text():
    """A consequence worth knowing: the fragments 'cr' and 'er' are shared content tokens, so an action
    sharing only a split fragment routes (a false-positive shape, pinned not changed)."""
    assert needs_semantic_judgment("créer factures", ["créer des factures"]) is True
    assert needs_semantic_judgment("crédit", ["créer des factures"]) is True      # 'cr' + 'dit': shares 'cr'
