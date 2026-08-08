"""The control mapping table.

ANTI-FABRICATION RULE (non-negotiable, tested): v0.1 has NOT ingested the
official texts of OSFI E-23, the EU AI Act, ISO/IEC 42001, or the NIST AI
RMF. Every framework citation below is therefore the literal string
"TODO-CITE-AFTER-INGESTION" — never an invented article/clause number. A
test fails the build if a non-TODO citation appears before ingestion is
done. Control ids and statements are Spin State's own words.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

TODO_CITATION = "TODO-CITE-AFTER-INGESTION"

FRAMEWORKS = {
    "osfi-e23": "OSFI Guideline E-23 (model risk management, Canada)",
    "eu-ai-act": "EU Artificial Intelligence Act",
    "iso-42001": "ISO/IEC 42001 (AI management systems)",
    "nist-ai-rmf": "NIST AI Risk Management Framework",
}


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: str
    letter: str  # F/I/E/L/D/R
    manifest_path: str
    statement: str  # our words, not regulation text
    evidence_kind: str  # what live artifact can prove it enforced
    citations: dict[str, str]  # framework key -> citation (all TODO in v0.1)


def _todo_citations() -> dict[str, str]:
    return {key: TODO_CITATION for key in FRAMEWORKS}


CONTROLS: list[Control] = [
    Control(
        control_id="FC-I-01", letter="I", manifest_path="identity.principal",
        statement="Every agent declares a human/organizational principal.",
        evidence_kind="registry record with human owner",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-F-01", letter="F", manifest_path="federated.isolated",
        statement="Federation posture is explicit: isolated, or enumerated peers "
        "with trust basis.",
        evidence_kind="manifest declaration (federation-broker events in Phase 4)",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-E-01", letter="E", manifest_path="enforcement.kill_switch",
        statement="A human can halt the agent; the halt path is exercised (drilled).",
        evidence_kind="kill.drill.complete event in sealed ledger",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-E-02", letter="E", manifest_path="enforcement.spend_cap",
        statement="Resource consumption is capped with human escalation before "
        "the cap.",
        evidence_kind="spend-governor cap configured + spend events in ledger",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-E-03", letter="E",
        manifest_path="enforcement.irreversible_action_policy",
        statement="One-way actions are forbidden, human-gated, or ledger-logged.",
        evidence_kind="manifest declaration + conformance.escalate events",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-L-01", letter="L", manifest_path="ledger.cryptographic_seal",
        statement="The audit trail is tamper-evident (hash-chained, verified).",
        evidence_kind="live sealed-ledger /verify ok=true",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-L-02", letter="L", manifest_path="ledger.retention_days",
        statement="Audit retention period is declared.",
        evidence_kind="manifest declaration (retention enforcement not built)",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-D-01", letter="D", manifest_path="delegation.granted_by",
        statement="Authority traces to a named human grantor with scope and expiry.",
        evidence_kind="delegation tokens bound to the agent",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-D-02", letter="D", manifest_path="delegation.revocation",
        statement="Authority is revocable and revocations take effect.",
        evidence_kind="delegation.revoke events / revoked tokens failing introspection",
        citations=_todo_citations(),
    ),
    Control(
        control_id="FC-R-01", letter="R", manifest_path="(registry)",
        statement="The agent is registered — identity precedes operation.",
        evidence_kind="agent-registry record",
        citations=_todo_citations(),
    ),
]
