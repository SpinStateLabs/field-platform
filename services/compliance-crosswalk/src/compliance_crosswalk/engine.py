"""Coverage evaluation: declared (manifest) vs. evidenced (live artifacts)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, Control
from field_core.validation import validate_manifest_data


class EvidenceSources(BaseModel):
    """Optional live artifacts, gathered by the caller/CLI. None = not collected."""

    model_config = ConfigDict(extra="forbid")

    registry_record: dict[str, Any] | None = None
    ledger_verify: dict[str, Any] | None = None
    ledger_event_types: dict[str, int] | None = None  # event_type -> count (agent)
    tokens: list[dict[str, Any]] | None = None
    governor_cap: dict[str, Any] | None = None


class ControlCoverage(BaseModel):
    control_id: str
    letter: str
    manifest_path: str
    statement: str
    declared: bool
    declared_detail: str
    evidenced: bool | None  # None = evidence not collected
    evidence_detail: str
    citations: dict[str, str]


class CoverageReport(BaseModel):
    agent_id: str | None
    generated_at: str
    manifest_valid: bool
    frameworks: dict[str, str]
    controls: list[ControlCoverage]
    declared_count: int
    evidenced_count: int
    evidence_collected: bool
    citation_status: str = (
        "All framework citations are TODO stubs. Official texts (OSFI E-23, "
        "EU AI Act, ISO/IEC 42001, NIST AI RMF) have not been ingested; no "
        "article or clause numbers are asserted. Populate via ingestion, "
        "never from memory."
    )


def _get_path(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "REPLACE-ME" in value
    if isinstance(value, dict):
        return any(_has_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(v) for v in value)
    return False


def _declared(control: Control, manifest: dict[str, Any]) -> tuple[bool, str]:
    if control.manifest_path == "(registry)":
        return True, "not a manifest field — see evidence"
    value = _get_path(manifest, control.manifest_path)
    if value is None:
        return False, f"{control.manifest_path} absent"
    if _has_placeholder(value):
        return False, f"{control.manifest_path} contains unresolved placeholder(s)"
    return True, f"{control.manifest_path} = {value!r}"[:120]


def _evidenced(
    control: Control, sources: EvidenceSources, agent_id: str | None
) -> tuple[bool | None, str]:
    collected = any(
        getattr(sources, f) is not None for f in EvidenceSources.model_fields
    )
    if not collected:
        return None, "evidence not collected (offline run)"
    events = sources.ledger_event_types or {}
    if control.control_id == "FC-R-01":
        ok = sources.registry_record is not None
        return ok, "registry record found" if ok else "agent not in registry"
    if control.control_id == "FC-I-01":
        ok = bool(sources.registry_record and sources.registry_record.get("owner"))
        return ok, "human owner on registry record" if ok else "no owner on record"
    if control.control_id == "FC-L-01":
        ok = bool(sources.ledger_verify and sources.ledger_verify.get("ok"))
        return ok, (
            "ledger chain verified"
            if ok
            else f"ledger verify failed: {(sources.ledger_verify or {}).get('reason')}"
        )
    if control.control_id == "FC-E-01":
        n = events.get("kill.drill.complete", 0) + events.get("kill.agent", 0)
        return n > 0, f"{n} kill/drill event(s) in ledger"
    if control.control_id == "FC-E-02":
        ok = sources.governor_cap is not None
        return ok, "governor cap configured" if ok else "no cap in spend-governor"
    if control.control_id == "FC-D-01":
        n = len(sources.tokens or [])
        return n > 0, f"{n} delegation token(s) for agent"
    if control.control_id == "FC-D-02":
        n = events.get("delegation.revoke", 0)
        revoked = sum(1 for t in (sources.tokens or []) if t.get("revoked"))
        ok = n > 0 or revoked > 0
        return ok, f"{n} revoke event(s), {revoked} revoked token(s)"
    if control.control_id == "FC-E-03":
        n = events.get("conformance.escalate", 0)
        return True, f"declared policy; {n} escalation event(s) observed"
    # FC-F-01, FC-L-02: declaration-only controls in v0.1
    return True, "declaration-only control in v0.1"


def evaluate(
    manifest: dict[str, Any],
    agent_id: str | None = None,
    sources: EvidenceSources | None = None,
) -> CoverageReport:
    sources = sources or EvidenceSources()
    validation = validate_manifest_data(manifest)
    coverages: list[ControlCoverage] = []
    for control in CONTROLS:
        declared, declared_detail = _declared(control, manifest)
        evidenced, evidence_detail = _evidenced(control, sources, agent_id)
        coverages.append(
            ControlCoverage(
                control_id=control.control_id,
                letter=control.letter,
                manifest_path=control.manifest_path,
                statement=control.statement,
                declared=declared,
                declared_detail=declared_detail,
                evidenced=evidenced,
                evidence_detail=evidence_detail,
                citations=control.citations,
            )
        )
    evidence_collected = any(c.evidenced is not None for c in coverages)
    return CoverageReport(
        agent_id=agent_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        manifest_valid=validation.ok,
        frameworks=FRAMEWORKS,
        controls=coverages,
        declared_count=sum(1 for c in coverages if c.declared),
        evidenced_count=sum(1 for c in coverages if c.evidenced),
        evidence_collected=evidence_collected,
    )


def render_markdown(report: CoverageReport) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# Compliance crosswalk — {report.agent_id or '<manifest only>'}")
    add("")
    add(f"*Generated:* {report.generated_at} · *Manifest valid:* "
        f"{'yes' if report.manifest_valid else 'NO'}")
    add(f"*Coverage:* {report.declared_count}/{len(report.controls)} declared · "
        f"{report.evidenced_count}/{len(report.controls)} evidenced"
        + ("" if report.evidence_collected else " (evidence not collected)"))
    add("")
    add(f"> **Citation status:** {report.citation_status}")
    add("")
    add("| Control | L | Statement | Declared | Evidenced | Evidence |")
    add("|---|---|---|---|---|---|")
    for c in report.controls:
        evidenced = "—" if c.evidenced is None else ("✓" if c.evidenced else "✗")
        add(
            f"| {c.control_id} | {c.letter} | {c.statement} | "
            f"{'✓' if c.declared else '✗'} | {evidenced} | {c.evidence_detail} |"
        )
    add("")
    add("## Framework mapping (citations pending ingestion)")
    add("")
    add("| Control | " + " | ".join(report.frameworks) + " |")
    add("|---|" + "---|" * len(report.frameworks))
    for c in report.controls:
        row = " | ".join(c.citations[f] for f in report.frameworks)
        add(f"| {c.control_id} | {row} |")
    return "\n".join(lines)
