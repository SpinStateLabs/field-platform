"""S12-21: manifest text quoted by field-core's validation gaps is bounded before it reaches a crossing verdict and the
hash-chained federation.block ledger row. field_core writes gap texts that quote the manifest's own values with !r and
no cap (schema_version, ledger.seal_algorithm), so a multi-megabyte value was a multi-megabyte audit row on every
refused crossing. The broker shortens each gap to 200 characters with a marker and keeps at most 2."""

from __future__ import annotations

import json

from federation_broker import engine as engine_mod
from field_core.validation import validate_manifest_data
from test_federation_broker import counterparty_manifest
from test_federation_outbound import events, our_manifest, outbound, stack  # noqa: F401 (fixture)

BIG = "x" * 1_000_000


def _inbound(broker, manifest):
    return broker.post("/crossing", json={
        "counterparty_org": "Borealis Example Corp", "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": manifest, "scope": "exchange invoice status", "data_class": "invoice metadata"})


def _blocked(verdict, ledger, *, limit):
    assert verdict["decision"] == "BLOCK" and verdict["clause_id"] == "I.manifest"
    assert all(len(r) < limit for r in verdict["reasons"]), [len(r) for r in verdict["reasons"]]
    rows = events(ledger, "federation.block")
    assert len(rows) == 1
    assert len(json.dumps(rows[0]["payload"])) < 4096
    assert all(len(r) < limit for r in rows[0]["payload"]["reasons"])


def test_an_outbound_megabyte_schema_version_is_bounded(stack):  # noqa: F811
    broker, ledger = stack
    manifest = our_manifest()
    manifest["schema_version"] = BIG
    verdict = outbound(broker, manifest=manifest).json()
    _blocked(verdict, ledger, limit=300)
    assert "...[truncated " in verdict["reasons"][0] and BIG not in verdict["reasons"][0]


def test_an_inbound_megabyte_schema_version_is_bounded(stack):  # noqa: F811
    broker, ledger = stack
    manifest = counterparty_manifest()
    manifest["schema_version"] = BIG
    verdict = _inbound(broker, manifest).json()
    _blocked(verdict, ledger, limit=300)
    assert "...[truncated " in verdict["reasons"][0]


def test_two_huge_gaps_are_each_bounded(stack):  # noqa: F811
    broker, ledger = stack
    manifest = our_manifest()
    manifest["schema_version"] = BIG
    manifest["ledger"]["seal_algorithm"] = BIG
    verdict = outbound(broker, manifest=manifest).json()
    _blocked(verdict, ledger, limit=700)
    assert verdict["reasons"][0].count("...[truncated ") == 2


def test_a_short_gap_text_is_unchanged_byte_for_byte(stack):  # noqa: F811
    broker, _ = stack
    manifest = our_manifest()
    manifest["schema_version"] = "9.9"
    expected = f"our manifest INVALID: {validate_manifest_data(manifest).critical_gaps[:2]}"
    assert "(got '9.9')" in expected and "truncated" not in expected
    assert outbound(broker, manifest=manifest).json()["reasons"][0] == expected


def test_the_helper_keeps_two_gaps_and_cuts_only_past_200_characters():
    bound = engine_mod._bounded_gaps
    assert bound(["a" * 200]) == ["a" * 200]
    assert bound(["a" * 201]) == ["a" * 200 + "...[truncated 1 chars]"]
    assert bound(["a" * 1000]) == ["a" * 200 + "...[truncated 800 chars]"]
    assert bound(["one", "two", "three"]) == ["one", "two"]
    assert bound([]) == []
