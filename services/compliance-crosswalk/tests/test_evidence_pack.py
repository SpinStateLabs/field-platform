"""evidence-pack tests — signer gate, stale-flag block, word discipline.

The stale store is duck-typed here (active()/status()) so these tests pass
independently of the staleness module being built in parallel; one
integration test exercises the real StaleStore and skips when it is not
importable yet.
"""

import inspect

import pytest

from compliance_crosswalk.engine import EvidenceSources
from compliance_crosswalk.evidence_pack import StalePackError, generate_pack
from field_core.templates_api import template_data

DISCLAIMER_SENTENCE = (
    "Signature is the action — this system never asserts compliance; "
    "a named human signs, or nothing ships."
)


def resolved_manifest():
    data = template_data("default")
    data["agent"]["name"] = "evidence-pack-test-agent"
    data["agent"]["description"] = "exercises evidence-pack generation"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = ["generate evidence packs"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


class FakeStaleStore:
    """Duck-typed stand-in matching the staleness contract surface."""

    def __init__(self, flags=None, corpus_version="corpus-test-2026-08-29"):
        self._flags = list(flags or [])
        self.corpus_version = corpus_version

    def active(self):
        return list(self._flags)

    def status(self):
        return {
            "corpus_version": self.corpus_version,
            "active": [
                dict(flag, stale_window_seconds=42) for flag in self._flags
            ],
            "history": list(self._flags),
        }


def test_signer_required_empty_and_whitespace():
    store = FakeStaleStore()
    for bad in ("", "   \t  "):
        with pytest.raises(ValueError, match="no pack ships without a named signer"):
            generate_pack(resolved_manifest(), signer=bad, stale_store=store)


def test_stale_flags_block_generation_hard():
    flag = {
        "framework": "osfi-e23",
        "flagged_at": "2026-08-29T12:00:00+00:00",
        "reason": "OSFI E-23 guidance page revision detected",
    }
    store = FakeStaleStore(flags=[flag])
    with pytest.raises(StalePackError) as excinfo:
        generate_pack(
            resolved_manifest(), signer="Controller", stale_store=store
        )
    err = excinfo.value
    assert isinstance(err, RuntimeError)
    assert err.flags == [flag]
    assert "osfi-e23" in str(err)
    # message names at least one affected control id (FC-I-01 cites OSFI)
    assert "FC-I-01" in str(err)
    assert "FC-I-01" in err.affected["osfi-e23"]


def test_no_override_parameter_exists():
    """ADR 07 §4: blocked until re-reviewed — there is no bypass."""
    params = inspect.signature(generate_pack).parameters
    assert set(params) == {
        "manifest", "signer", "stale_store", "agent_id", "sources", "now",
    }
    assert not any("override" in name or "force" in name for name in params)


def test_pack_markdown_contents():
    store = FakeStaleStore()
    md, _ = generate_pack(
        resolved_manifest(),
        signer="Controller, Spin State Labs",
        stale_store=store,
    )
    assert "# Evidence Pack — FIELD control coverage" in md
    assert "FC-I-01" in md
    assert "identity.principal" in md
    assert "Principle 1.1" in md                      # verified OSFI reference
    assert "2026-08-08" in md                          # retrieval date
    assert store.corpus_version in md                  # corpus version line
    assert DISCLAIMER_SENTENCE in md
    assert "pending-purchase — paid standard not obtained; never cited from memory" in md
    assert "pending-text — no verified source" in md
    assert "No active stale flags." in md
    assert "Prepared for signature by: Controller, Spin State Labs" in md
    assert "Date: _" in md                             # blank signature date line


def test_word_discipline_complian_only_in_disclaimer():
    md, _ = generate_pack(
        resolved_manifest(),
        signer="Controller, Spin State Labs",
        stale_store=FakeStaleStore(),
    )
    offending = [line for line in md.splitlines() if "complian" in line.lower()]
    assert offending, "the verbatim disclaimer sentence must be present"
    # Allow-list is exactly the disclaimer line — nothing else in the pack
    # may use assurance language.
    for line in offending:
        assert DISCLAIMER_SENTENCE in line, (
            f"assurance language outside the disclaimer: {line!r}"
        )


def test_dict_result_fields():
    store = FakeStaleStore()
    _, result = generate_pack(
        resolved_manifest(),
        signer="Controller, Spin State Labs",
        stale_store=store,
        agent_id="agent-1",
    )
    assert result["signer"] == "Controller, Spin State Labs"
    assert result["corpus_version"] == store.corpus_version
    assert result["manifest_valid"] is True
    assert result["agent_id"] == "agent-1"
    assert result["staleness"]["active"] == []
    assert result["generated_at"]
    row = next(r for r in result["controls"] if r["control_id"] == "FC-I-01")
    assert row["manifest_path"] == "identity.principal"
    citation = row["citations"]["osfi-e23"]
    assert citation["status"] == "cited"
    assert "Principle 1.1" in citation["reference"]
    assert citation["retrieved"] == "2026-08-08"


def test_gaps_listed_for_undeclared_and_failed_evidence():
    sources = EvidenceSources(
        ledger_verify={"ok": False, "reason": "hash mismatch at index 2"},
    )
    md, result = generate_pack(
        resolved_manifest(),
        signer="Controller",
        stale_store=FakeStaleStore(),
        agent_id="a",
        sources=sources,
    )
    kinds = {(g["control_id"], g["kind"]) for g in result["gaps"]}
    # default template carries no spend_cap — an honest declared gap
    assert ("FC-E-02", "not-declared") in kinds
    assert ("FC-L-01", "not-evidenced") in kinds
    assert "## Gaps" in md
    assert "enforcement.spend_cap absent" in md         # declared_detail
    assert "hash mismatch at index 2" in md             # evidence_detail


def test_real_staleness_roundtrip(tmp_path):
    """Integration with the real staleness module (built in parallel);
    skips when it is not importable yet."""
    try:
        staleness = pytest.importorskip("compliance_crosswalk.staleness")
    except Exception as exc:  # mid-write sibling file (e.g. SyntaxError)
        pytest.skip(f"staleness module not importable yet: {exc}")
    store = staleness.StaleStore(tmp_path / "stale_flags.json")

    store.mark("osfi-e23", "integration test: simulated corpus revision")
    assert store.active(), "mark() should leave an active flag"

    with pytest.raises(StalePackError) as excinfo:
        generate_pack(
            resolved_manifest(), signer="Controller", stale_store=store
        )
    assert "osfi-e23" in str(excinfo.value)

    store.clear("osfi-e23", reviewed_by="Controller, Spin State Labs")
    assert store.active() == []

    md, result = generate_pack(
        resolved_manifest(), signer="Controller", stale_store=store
    )
    assert DISCLAIMER_SENTENCE in md
    assert staleness.CORPUS_VERSION in md
    assert result["corpus_version"] == staleness.CORPUS_VERSION
    assert result["manifest_valid"] is True
