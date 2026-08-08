"""The control mapping table — citations are source-grounded or absent.

ANTI-FABRICATION RULE (unchanged in spirit, upgraded in mechanism): a
citation exists ONLY if the referenced text was retrieved and verified from
the named source on the named date. Anything not verified stays
``pending-text`` with no reference at all. The guard test enforces the
shape; the INGESTION_LOG records what was actually read.

Ingestion status (2026-08-08):
- EU AI Act — Articles 12 and 14 verified via the AI Act Explorer mirror of
  Regulation (EU) 2024/1689 (artificialintelligenceact.eu). Cross-check
  against EUR-Lex (CELEX:32024R1689) before any external publication.
- NIST AI RMF 1.0 — Core subcategories verified from the official NIST AIRC
  (airc.nist.gov).
- OSFI Guideline E-23 (2027, effective 2027-05-01) — principles verified
  from the official OSFI page.
- ISO/IEC 42001 — PAID STANDARD; text not obtained. Every ISO citation is
  pending-purchase. Do not cite it from memory, ever.

Mappings are deliberately conservative: where no verified text corresponds
to a control, the entry is pending — a sparse honest crosswalk beats a
dense invented one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

RETRIEVED = "2026-08-08"

FRAMEWORKS = {
    "osfi-e23": "OSFI Guideline E-23 — Model Risk Management (2027)",
    "eu-ai-act": "EU AI Act — Regulation (EU) 2024/1689",
    "iso-42001": "ISO/IEC 42001 (AI management systems)",
    "nist-ai-rmf": "NIST AI Risk Management Framework 1.0 (AI 100-1)",
}

SRC_OSFI = "https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027"
SRC_EU_ART12 = "https://artificialintelligenceact.eu/article/12/"
SRC_EU_ART14 = "https://artificialintelligenceact.eu/article/14/"
SRC_NIST = "https://airc.nist.gov/airmf-resources/airmf/5-sec-core/"

INGESTION_LOG = [
    {"framework": "eu-ai-act", "what": "Article 12 (Record-Keeping) ¶1; "
     "Article 14 (Human Oversight) ¶1 and ¶4(e)",
     "source": "AI Act Explorer mirror", "retrieved": RETRIEVED},
    {"framework": "nist-ai-rmf", "what": "Core subcategories GOVERN 1.6, 1.7, "
     "2.1, 2.3, 6.1, 6.2; MANAGE 2.4; MEASURE 3.1",
     "source": "NIST AIRC (official)", "retrieved": RETRIEVED},
    {"framework": "osfi-e23", "what": "Principles 1.1, 1.2, 2.1, 3.1, 3.6; "
     "model inventory and decommission passages",
     "source": "OSFI (official)", "retrieved": RETRIEVED},
    {"framework": "iso-42001", "what": "NOT INGESTED — paid standard",
     "source": None, "retrieved": None},
]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["cited", "pending-text", "pending-purchase"]
    reference: str | None = None
    source_url: str | None = None
    retrieved: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _grounded_or_absent(self) -> "Citation":
        if self.status == "cited":
            if not (self.reference and self.source_url and self.retrieved):
                raise ValueError(
                    "cited entries require reference + source_url + retrieved"
                )
        elif self.reference is not None:
            raise ValueError(
                f"{self.status} entries must carry NO reference — that would "
                "be a citation without a verified source"
            )
        return self


def _pending(note: str | None = None) -> Citation:
    return Citation(status="pending-text", note=note)


def _iso() -> Citation:
    return Citation(
        status="pending-purchase",
        note="ISO/IEC 42001 is a paid standard; cite only after purchasing "
        "and reading the official text",
    )


def _nist(ref: str, note: str | None = None) -> Citation:
    return Citation(status="cited", reference=ref, source_url=SRC_NIST,
                    retrieved=RETRIEVED, note=note)


def _osfi(ref: str, note: str | None = None) -> Citation:
    return Citation(status="cited", reference=ref, source_url=SRC_OSFI,
                    retrieved=RETRIEVED, note=note)


def _eu(ref: str, url: str, note: str | None = None) -> Citation:
    return Citation(status="cited", reference=ref, source_url=url,
                    retrieved=RETRIEVED, note=note)


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: str
    letter: str
    manifest_path: str
    statement: str
    evidence_kind: str
    citations: dict[str, Citation]


CONTROLS: list[Control] = [
    Control(
        control_id="FC-I-01", letter="I", manifest_path="identity.principal",
        statement="Every agent declares a human/organizational principal.",
        evidence_kind="registry record with human owner",
        citations={
            "osfi-e23": _osfi("Principle 1.1 (Organizational Enablement) — "
                              "senior management defines roles; model risk "
                              "reported to the board"),
            "eu-ai-act": _eu("Article 14 (Human Oversight) ¶1 — systems "
                             "effectively overseen by natural persons",
                             SRC_EU_ART14),
            "iso-42001": _iso(),
            "nist-ai-rmf": _nist("GOVERN 2.3 — executive leadership takes "
                                 "responsibility for AI risk decisions"),
        },
    ),
    Control(
        control_id="FC-F-01", letter="F", manifest_path="federated.isolated",
        statement="Federation posture is explicit: isolated, or enumerated "
        "peers with trust basis.",
        evidence_kind="manifest declaration + federation-broker crossing events",
        citations={
            "osfi-e23": _osfi("Principle 1.2 / §B.2 — framework covers models "
                              "or data sourced from third-party vendors"),
            "eu-ai-act": _pending("third-party/value-chain articles not yet "
                                  "ingested"),
            "iso-42001": _iso(),
            "nist-ai-rmf": _nist("GOVERN 6.1 — policies address AI risks from "
                                 "third-party entities"),
        },
    ),
    Control(
        control_id="FC-E-01", letter="E", manifest_path="enforcement.kill_switch",
        statement="A human can halt the agent; the halt path is exercised "
        "(drilled).",
        evidence_kind="kill.drill.complete event in sealed ledger",
        citations={
            "osfi-e23": _pending("no stop-mechanism passage verified in "
                                 "ingested sections"),
            "eu-ai-act": _eu("Article 14 (Human Oversight) ¶4(e) — intervene "
                             "or interrupt through a 'stop' button or similar "
                             "procedure halting in a safe state",
                             SRC_EU_ART14),
            "iso-42001": _iso(),
            "nist-ai-rmf": _nist("MANAGE 2.4 — mechanisms to supersede, "
                                 "disengage, or deactivate AI systems "
                                 "inconsistent with intended use"),
        },
    ),
    Control(
        control_id="FC-E-02", letter="E", manifest_path="enforcement.spend_cap",
        statement="Resource consumption is capped with human escalation "
        "before the cap.",
        evidence_kind="spend-governor cap configured + spend events in ledger",
        citations={
            "osfi-e23": _pending("no resource-cap passage verified"),
            "eu-ai-act": _pending("no resource-cap passage verified"),
            "iso-42001": _iso(),
            "nist-ai-rmf": _pending("no directly corresponding subcategory "
                                    "verified in ingested Core text"),
        },
    ),
    Control(
        control_id="FC-E-03", letter="E",
        manifest_path="enforcement.irreversible_action_policy",
        statement="One-way actions are forbidden, human-gated, or "
        "ledger-logged.",
        evidence_kind="manifest declaration + conformance.escalate events",
        citations={
            "osfi-e23": _pending(),
            "eu-ai-act": _eu("Article 14 (Human Oversight) ¶1 — effective "
                             "oversight during use", SRC_EU_ART14,
                             note="partial mapping: human-gating of one-way "
                             "actions as an oversight measure"),
            "iso-42001": _iso(),
            "nist-ai-rmf": _pending(),
        },
    ),
    Control(
        control_id="FC-L-01", letter="L", manifest_path="ledger.cryptographic_seal",
        statement="The audit trail is tamper-evident (hash-chained, verified).",
        evidence_kind="live sealed-ledger /verify ok=true",
        citations={
            "osfi-e23": _pending("monitoring principle 3.6 is about model "
                                 "performance, not audit logging — not mapped"),
            "eu-ai-act": _eu("Article 12 (Record-Keeping) ¶1 — automatic "
                             "recording of events (logs) over the lifetime of "
                             "the system", SRC_EU_ART12),
            "iso-42001": _iso(),
            "nist-ai-rmf": _pending("no explicit logging subcategory verified "
                                    "in ingested Core text"),
        },
    ),
    Control(
        control_id="FC-L-02", letter="L", manifest_path="ledger.retention_days",
        statement="Audit retention period is declared.",
        evidence_kind="manifest declaration (retention enforcement not built)",
        citations={
            "osfi-e23": _pending(),
            "eu-ai-act": _eu("Article 12 (Record-Keeping) ¶1", SRC_EU_ART12,
                             note="partial: covers log generation; retention "
                             "duration (Art. 19) not yet ingested"),
            "iso-42001": _iso(),
            "nist-ai-rmf": _pending(),
        },
    ),
    Control(
        control_id="FC-D-01", letter="D", manifest_path="delegation.granted_by",
        statement="Authority traces to a named human grantor with scope and "
        "expiry.",
        evidence_kind="delegation tokens bound to the agent",
        citations={
            "osfi-e23": _osfi("Principle 1.1 — senior management defines "
                              "roles and responsibilities"),
            "eu-ai-act": _pending("deployer-obligation articles not yet "
                                  "ingested"),
            "iso-42001": _iso(),
            "nist-ai-rmf": _nist("GOVERN 2.1 — roles, responsibilities, and "
                                 "lines of communication documented and clear"),
        },
    ),
    Control(
        control_id="FC-D-02", letter="D", manifest_path="delegation.revocation",
        statement="Authority is revocable and revocations take effect.",
        evidence_kind="delegation.revoke events / revoked tokens failing "
        "introspection",
        citations={
            "osfi-e23": _osfi("Principle 3.6 — defined standards for model "
                              "monitoring and model decommission",
                              note="partial: decommission is coarser than "
                              "token-level revocation"),
            "eu-ai-act": _pending(),
            "iso-42001": _iso(),
            "nist-ai-rmf": _nist("MANAGE 2.4 — supersede, disengage, or "
                                 "deactivate", note="partial: system-level "
                                 "disengagement vs. token-level revocation"),
        },
    ),
    Control(
        control_id="FC-R-01", letter="R", manifest_path="(registry)",
        statement="The agent is registered — identity precedes operation.",
        evidence_kind="agent-registry record",
        citations={
            "osfi-e23": _osfi("Principle 2.1 — identify and track all models "
                              "in use or recently decommissioned; enterprise "
                              "model inventory"),
            "eu-ai-act": _pending("registration articles not yet ingested"),
            "iso-42001": _iso(),
            "nist-ai-rmf": _nist("GOVERN 1.6 — mechanisms in place to "
                                 "inventory AI systems"),
        },
    ),
]
