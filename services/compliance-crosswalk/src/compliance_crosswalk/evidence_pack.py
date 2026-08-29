"""Evidence-pack generation — the signature is the action (ADR 07 §2/§4).

Governance rationale, stated plainly: this module never asserts that any
control satisfies any framework. It assembles what is *declared* in the
manifest, what is *evidenced* by live artifacts, and the source-grounded
citations from the authored matrix — then hands the result to a named
human whose signature is the action. Three rules are enforced in code,
not merely documented:

- No pack ships without a named signer: an empty or whitespace signer is
  a ``ValueError``, not a default.
- Active stale flags on the regulatory corpus block generation outright
  (``StalePackError``). There is deliberately no override parameter — a
  pack generated over a stale corpus is a false assurance waiting for a
  signature, and re-review is the only way forward (ADR 07 §4).
- Word discipline: the strings "compliant"/"compliance" appear in the
  rendered pack only inside the verbatim disclaimer sentence. Gaps and
  not-collected evidence are first-class outputs — over-conservative is
  survivable; false assurance is not.

The staleness service is imported lazily inside functions so this module
loads even while that module is unavailable; the caller's stale store
still speaks for the corpus through its ``active()``/``status()``
contract, and affected controls fall back to the authored matrix (every
control whose entry cites the flagged framework's verified text).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from compliance_crosswalk.engine import EvidenceSources, evaluate
from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, INGESTION_LOG

DISCLAIMER = (
    "Signature is the action — this system never asserts compliance; "
    "a named human signs, or nothing ships."
)


class StalePackError(RuntimeError):
    """Raised when active stale flags block pack generation (no override)."""

    def __init__(self, flags: list[dict], affected: dict[str, list[str]]) -> None:
        self.flags = flags
        self.affected = affected
        details = []
        for flag in flags:
            framework = str(flag.get("framework", "<unknown framework>"))
            control_ids = affected.get(framework) or []
            details.append(
                f"{framework} (flagged_at: {flag.get('flagged_at', 'unknown')}; "
                f"reason: {flag.get('reason', 'unspecified')}; affected controls: "
                f"{', '.join(control_ids) if control_ids else 'none identified'})"
            )
        super().__init__(
            "Evidence-pack generation is blocked — the regulatory corpus has "
            "active stale flag(s): " + "; ".join(details) + ". Re-review the "
            "affected mappings and clear the flags; there is no override."
        )


def _affected_controls(framework: str) -> list[str]:
    """Controls affected by a stale framework, via the staleness service.

    Fallback while that module is unavailable: every control whose
    authored-matrix entry *cites* the framework's verified text is treated
    as affected — conservative by construction.
    """
    try:
        from compliance_crosswalk.staleness import affected_controls
    except Exception:
        return [
            control.control_id
            for control in CONTROLS
            if (citation := control.citations.get(framework)) is not None
            and citation.status == "cited"
        ]
    return affected_controls(framework)


def _corpus_version(status: dict[str, Any]) -> str:
    """Corpus version: the store's status() carries it by contract; the
    staleness module's CORPUS_VERSION is the same value at the source."""
    version = status.get("corpus_version")
    if version:
        return str(version)
    try:
        from compliance_crosswalk.staleness import CORPUS_VERSION
    except Exception:
        return "unknown (staleness service unavailable)"
    return CORPUS_VERSION


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def generate_pack(
    manifest: dict[str, Any],
    *,
    signer: str,
    stale_store: Any,
    agent_id: str | None = None,
    sources: EvidenceSources | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Generate the evidence pack: (markdown, dict). Blocked, never fudged."""
    if signer is None or not str(signer).strip():
        raise ValueError(
            "refusing to generate: no pack ships without a named signer "
            "(signer was empty or whitespace)"
        )
    signer = str(signer).strip()

    flags = list(stale_store.active() or [])
    if flags:
        affected: dict[str, list[str]] = {}
        for flag in flags:
            framework = flag.get("framework")
            if framework and framework not in affected:
                affected[framework] = _affected_controls(framework)
        raise StalePackError(flags, affected)

    status = dict(stale_store.status() or {})
    corpus_version = _corpus_version(status)
    coverage = evaluate(manifest, agent_id=agent_id, sources=sources)
    now = now or datetime.now(timezone.utc)
    generated_at = now.isoformat()

    gaps: list[dict[str, Any]] = []
    for control in coverage.controls:
        if not control.declared:
            gaps.append(
                {
                    "control_id": control.control_id,
                    "kind": "not-declared",
                    "detail": control.declared_detail,
                }
            )
        if control.evidenced is False:
            gaps.append(
                {
                    "control_id": control.control_id,
                    "kind": "not-evidenced",
                    "detail": control.evidence_detail,
                }
            )

    lines: list[str] = []
    add = lines.append
    add("# Evidence Pack — FIELD control coverage")
    add("")
    add(f"- generated_at: {generated_at}")
    add(f"- Regulatory corpus version: {corpus_version}")
    add(f"- agent_id: {agent_id or 'manifest-only'}")
    add(f"- Prepared for signature by: {signer}")
    add("")
    add(DISCLAIMER)
    add("")
    add("## Control coverage")
    add("")
    add(
        f"Manifest valid: {_yes_no(coverage.manifest_valid)}. Declared means "
        "the manifest carries the field; evidenced means a live artifact was "
        "collected and checked; not-collected means no evidence was gathered "
        "on this run — an honest unknown, not a pass."
    )
    add("")
    add("| control_id | manifest_path | declared | evidenced |")
    add("|---|---|---|---|")
    for control in coverage.controls:
        evidenced = (
            "not-collected"
            if control.evidenced is None
            else _yes_no(control.evidenced)
        )
        add(
            f"| {control.control_id} | {control.manifest_path} | "
            f"{_yes_no(control.declared)} | {evidenced} |"
        )
    add("")
    add("### Citations (three-part: manifest_path · control_id · framework reference)")
    add("")
    for control in coverage.controls:
        add(f"- **{control.control_id}** ({control.manifest_path})")
        for framework in FRAMEWORKS:
            citation = control.citations[framework]
            if citation.status == "cited":
                add(
                    f"  - {framework}: {control.manifest_path} · "
                    f"{control.control_id} · {citation.reference} — "
                    f"{citation.source_url} (retrieved {citation.retrieved})"
                )
            elif citation.status == "pending-text":
                add(f"  - {framework}: pending-text — no verified source")
            else:
                add(
                    f"  - {framework}: pending-purchase — paid standard not "
                    "obtained; never cited from memory"
                )
    add("")
    add("## Gaps")
    add("")
    if gaps:
        add(
            "Over-conservative is survivable; false assurance is not. Each "
            "gap below stands until remediated and re-checked:"
        )
        add("")
        for gap in gaps:
            label = (
                "not declared" if gap["kind"] == "not-declared" else "not evidenced"
            )
            add(f"- {gap['control_id']} — {label}: {gap['detail']}")
    else:
        add(
            "No gaps recorded on this run: every control is declared, and no "
            "collected evidence check failed. Controls marked not-collected "
            "above remain unknowns, not passes."
        )
    add("")
    add("## Regulatory corpus staleness")
    add("")
    active = status.get("active") or []
    if not active:
        add("No active stale flags.")
    else:
        # Unreachable when active() and status() agree — rendered honestly
        # rather than hidden if they ever disagree.
        add(
            "WARNING: status() reports active flags although active() "
            "returned none — treat this pack as blocked and investigate:"
        )
        add("")
        for entry in active:
            bits = [f"framework: {entry.get('framework', 'unknown')}"]
            if entry.get("flagged_at"):
                bits.append(f"flagged_at: {entry['flagged_at']}")
            if entry.get("reason"):
                bits.append(f"reason: {entry['reason']}")
            if entry.get("stale_window_seconds") is not None:
                bits.append(
                    f"stale window (seconds): {entry['stale_window_seconds']}"
                )
            add("- " + " — ".join(bits))
    add("")
    add("## Ingestion log")
    add("")
    for entry in INGESTION_LOG:
        parts = [f"{entry['framework']}: {entry['what']}"]
        if entry.get("source"):
            parts.append(f"source: {entry['source']}")
        if entry.get("retrieved"):
            parts.append(f"retrieved: {entry['retrieved']}")
        if entry.get("note"):
            parts.append(f"note: {entry['note']}")
        add("- " + " — ".join(parts))
    add("")
    add("---")
    add("")
    add("## Signature")
    add("")
    add(f"Signer: {signer}")
    add("")
    add("Date: ______________________")
    markdown = "\n".join(lines) + "\n"

    result: dict[str, Any] = {
        "generated_at": generated_at,
        "corpus_version": corpus_version,
        "signer": signer,
        "agent_id": agent_id,
        "controls": [
            {
                "control_id": control.control_id,
                "manifest_path": control.manifest_path,
                "declared": control.declared,
                "declared_detail": control.declared_detail,
                "evidenced": control.evidenced,
                "evidence_detail": control.evidence_detail,
                "citations": {
                    framework: citation.model_dump()
                    for framework, citation in control.citations.items()
                },
            }
            for control in coverage.controls
        ],
        "gaps": gaps,
        "staleness": status,
        "manifest_valid": coverage.manifest_valid,
    }
    return markdown, result
