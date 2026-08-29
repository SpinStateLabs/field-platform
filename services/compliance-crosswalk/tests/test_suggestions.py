"""suggestions tests — the gates that keep an LLM proposal from becoming a
mapping: precision floor, fail-conservative errors, framework vetting, the
half-mapped-candidate refusal, and CONTROLS immutability."""

import pytest
from pydantic import ValidationError

from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS
from compliance_crosswalk.suggestions import (
    DISCLAIMER,
    SUGGEST_RUBRIC_VERSION,
    MappingSuggestion,
    MockSuggester,
    resolve_suggest_floor,
    resolve_suggester,
    suggest,
    unmapped_paths,
)
from field_core.templates_api import template_data

TINY_MANIFEST = {"agent": {"description": "chases overdue invoices"}}


def test_floor_gate_above_floor_yields_candidate():
    mock = MockSuggester(rules={
        "agent.description": ("nist-ai-rmf", "System purpose is documented.",
                              0.9, "clear purpose statement"),
    })
    out = suggest(TINY_MANIFEST, mock, floor=0.8)
    assert len(out) == 1
    s = out[0]
    assert s.status == "candidate"
    assert s.framework == "nist-ai-rmf"
    assert s.candidate_statement == "System purpose is documented."
    assert s.confidence == 0.9
    assert mock.calls == [{"manifest_path": "agent.description",
                           "value": "chases overdue invoices"}]


def test_floor_gate_below_floor_is_review_required_not_dropped():
    mock = MockSuggester(rules={
        "agent.description": ("nist-ai-rmf", "System purpose is documented.",
                              0.5, "weak match"),
    })
    out = suggest(TINY_MANIFEST, mock, floor=0.8)
    assert len(out) == 1  # below-floor is a first-class output, never dropped
    s = out[0]
    assert s.status == "unmapped — review required"
    assert s.framework is None
    assert s.candidate_statement is None
    assert s.confidence == 0.5  # reported, not zeroed
    assert "below floor" in s.rationale


def test_suggester_exception_never_raises_never_candidate():
    mock = MockSuggester(raise_error=RuntimeError("upstream on fire"))
    out = suggest(TINY_MANIFEST, mock, floor=0.8)
    assert len(out) == 1
    s = out[0]
    assert s.status == "unmapped — review required"
    assert s.framework is None and s.candidate_statement is None
    assert s.confidence == 0.0
    assert "upstream on fire" in s.rationale


def test_unknown_framework_is_review_required():
    mock = MockSuggester(rules={
        "agent.description": ("gdpr", "Purpose limitation.", 0.95,
                              "confident but unvetted framework"),
    })
    out = suggest(TINY_MANIFEST, mock, floor=0.8)
    s = out[0]
    assert s.status == "unmapped — review required"
    assert s.framework is None and s.candidate_statement is None
    assert "'gdpr'" in s.rationale


def test_disclaimer_and_rubric_version_on_every_entry():
    out = suggest(template_data("default"), MockSuggester(), floor=0.8)
    assert out, "default template must yield unmapped paths"
    for s in out:
        assert s.disclaimer == DISCLAIMER
        assert s.rubric_version == SUGGEST_RUBRIC_VERSION
        assert s.model  # which model (or mock) produced it is always recorded


def test_model_refuses_half_mapped_candidate():
    with pytest.raises(ValidationError):
        MappingSuggestion(
            manifest_path="agent.description", framework="nist-ai-rmf",
            candidate_statement=None, confidence=0.99,
            rationale="hand-built half-mapping", status="candidate",
            model="test",
        )
    with pytest.raises(ValidationError):
        MappingSuggestion(
            manifest_path="agent.description", framework="nist-ai-rmf",
            candidate_statement="smuggled statement", confidence=0.1,
            rationale="review entry claiming a framework",
            status="unmapped — review required", model="test",
        )


def test_unmapped_paths_on_default_template():
    paths = unmapped_paths(template_data("default"))
    assert paths == sorted(paths)
    assert "identity.principal" not in paths  # covered by FC-I-01
    assert "agent.description" in paths       # no control covers it
    for control in CONTROLS:
        for p in paths:
            assert p != control.manifest_path
            assert not p.startswith(control.manifest_path + ".")


def test_suggest_never_mutates_controls():
    snapshot = [c.model_dump() for c in CONTROLS]
    suggest(template_data("default"), MockSuggester(rules={
        "agent.description": ("eu-ai-act", "A statement.", 0.99, "r"),
    }), floor=0.5)
    assert [c.model_dump() for c in CONTROLS] == snapshot
    assert len(CONTROLS) == len(snapshot)


def test_resolve_suggester_off_by_default_and_on_typo(monkeypatch):
    monkeypatch.delenv("CROSSWALK_SUGGEST", raising=False)
    assert resolve_suggester() is None
    monkeypatch.setenv("CROSSWALK_SUGGEST", "gpt")  # typo/unvetted ⇒ OFF
    assert resolve_suggester() is None
    monkeypatch.setenv("CROSSWALK_SUGGEST", "mock")
    assert isinstance(resolve_suggester(), MockSuggester)


def test_resolve_suggest_floor_parsing(monkeypatch):
    monkeypatch.delenv("CROSSWALK_SUGGEST_FLOOR", raising=False)
    assert resolve_suggest_floor() == 0.8
    monkeypatch.setenv("CROSSWALK_SUGGEST_FLOOR", "not-a-number")
    assert resolve_suggest_floor() == 0.8
    monkeypatch.setenv("CROSSWALK_SUGGEST_FLOOR", "2.5")
    assert resolve_suggest_floor() == 1.0
    monkeypatch.setenv("CROSSWALK_SUGGEST_FLOOR", "-3")
    assert resolve_suggest_floor() == 0.0
    monkeypatch.setenv("CROSSWALK_SUGGEST_FLOOR", "0.6")
    assert resolve_suggest_floor() == 0.6


def test_mock_token_counts_are_flat_class_attributes():
    assert MockSuggester.input_tokens == 80
    assert MockSuggester.output_tokens == 40
    m = MockSuggester()
    assert m.name == "mock"
    assert (m.input_tokens, m.output_tokens) == (80, 40)


def test_frameworks_known_to_suggestions_match_mapping():
    """The suggestion gate vets against the SAME framework registry the
    curated crosswalk uses — no side-channel framework list."""
    assert set(FRAMEWORKS) == {"osfi-e23", "eu-ai-act", "iso-42001",
                               "nist-ai-rmf"}
