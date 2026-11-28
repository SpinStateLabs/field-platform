"""Evidence-pack generation — the signature is the action (ADR 07 §2/§4).

Governance rationale, stated plainly: this module never asserts that any
control satisfies any framework. It assembles what is *declared* in the
manifest, what is *evidenced* by live artifacts, and the source-grounded
citations from the authored matrix — then hands the result to a named
human whose signature is the action. Three rules are enforced in code,
not merely documented:

- No pack ships without a named signer: an empty or whitespace signer is
  a ``ValueError``, not a default. The signer is written into the pack text, so it is a NAME and nothing else:
  a control, invisible-format (zero-width, mark, bidirectional) or line-break character in it, or more than 200
  characters, or no letter or digit at all ('...', '-'), is a ``ValueError`` too (a signer containing newlines would otherwise forge headings and lines in the pack).
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

import unicodedata
from datetime import datetime, timezone
from typing import Any

from compliance_crosswalk.engine import (
    GAP_LABELS,
    LEDGER_NOT_CHECKED_GAP,  # moved to engine (B7); still importable from here, and used for the B2 outage gap
    declared_only_note,
    LEDGER_VERIFY_NOT_CHECKED,
    REFUSED_CATEGORIES,
    EvidenceSources,
    coverage_gaps,
    evaluate,
    one_line,
)

#: B2: the pack's gap labels: the shared ones (engine.GAP_LABELS, B7) plus the caller-asserted kind only a pack has
PACK_GAP_LABELS = {**GAP_LABELS, "caller-asserted": "caller-asserted, not verified"}
#: B2: prefix of a control's evidence detail when its positive verdict rests only on caller-supplied sources
CALLER_ASSERTED_PREFIX = "caller-asserted, not verified against the live ledger and services: "
#: B2: the "caller-asserted" gap detail: fixed text, so Markdown and JSON say the same
CALLER_ASSERTED_GAP = (
    "the caller supplied this evidence and a live collection on this run did not confirm it; "
    "this is not a pass: re-run the pack with agent_id and the platform reachable"
)
#: B2: the headline when live collection was requested and no platform service answered (a full outage)
EVIDENCE_UNKNOWN_HEADLINE = (
    "Evidence status UNKNOWN: live collection was requested for this agent but no platform service answered "
    "(ledger, registry, delegation, spend-governor), so no control was checked on this run; this is not a pass: "
    "re-run the pack"
)
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


class InvalidSigner(ValueError):
    """The signer is blank, too long, or holds a character that would break the pack text."""


#: Longest signer string accepted (a name and a role fit comfortably).
MAX_SIGNER_CHARS = 200
#: Unicode categories a signer may not contain: control (Cc), invisible format (Cf: left/right marks, Arabic letter
#: mark, zero-width space/joiner, word joiner, byte-order mark, and the bidirectional overrides and isolates) and
#: line or paragraph separator (Zl, Zp). A signer is a name you can SEE on one line (C-389): the format characters
#: reorder the text around them or make two different signers look identical.
_REFUSED_CATEGORIES = REFUSED_CATEGORIES


def _checked_signer(signer: Any) -> str:
    """The stripped signer, or ``InvalidSigner``: not text, blank, over ``MAX_SIGNER_CHARS``, or holding a control
    character (Unicode category Cc: newline, carriage return, tab, NUL, DEL, C1), an invisible format character (Cf:
    marks, zero-width characters, byte-order mark, bidirectional overrides), a line or paragraph separator (Zl, Zp) or
    an unpaired surrogate (Cs, PR 563). The message names the code point and its position, never the signer."""
    if signer is not None and not isinstance(signer, str):
        raise InvalidSigner(f"refusing to generate: the signer must be text, not {type(signer).__name__}")
    if signer is None or not str(signer).strip():
        raise InvalidSigner(
            "refusing to generate: no pack ships without a named signer "
            "(signer was empty or whitespace)"
        )
    text = str(signer).strip()
    if len(text) > MAX_SIGNER_CHARS:
        raise InvalidSigner(
            f"refusing to generate: the signer is {len(text)} characters; the limit is {MAX_SIGNER_CHARS}"
        )
    for position, ch in enumerate(text):
        if unicodedata.category(ch) in _REFUSED_CATEGORIES:
            raise InvalidSigner(
                f"refusing to generate: the signer holds a control, invisible or line-break character "
                f"(U+{ord(ch):04X} at position {position}); a signer is a name on one line"
            )
    if not any(ch.isalnum() for ch in text):
        raise InvalidSigner(
            "refusing to generate: the signer must name a human: it needs at least one letter or digit"
        )
    return text


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _any_source(sources: EvidenceSources | None) -> bool:
    return sources is not None and any(getattr(sources, f) is not None for f in EvidenceSources.model_fields)


def _caller_asserted_coverage(
    manifest: dict[str, Any], agent_id: str | None, caller: EvidenceSources, live: EvidenceSources | None
) -> tuple[Any, set[str]]:
    """B2 (F1, review of d8561c8): coverage when the caller supplied sources. Every row starts from the LIVE
    evaluation of this run, and a live verdict always stands: True, False, and FC-L-01 "not checked" (the ledger was
    asked and did not answer). Caller input only fills a row the live collection had nothing on (evidenced None):
    a caller positive becomes ``caller-asserted`` (None, plus a gap, returned in the id set), a caller negative
    becomes a not-evidenced gap. So a body can add gaps, never hide one the live run found."""
    claimed = {c.control_id: c for c in evaluate(manifest, agent_id=agent_id, sources=caller).controls}
    checked = evaluate(manifest, agent_id=agent_id, sources=live)
    asserted: set[str] = set()
    rows = []
    for row in checked.controls:
        live_unknown = row.evidenced is None and row.evidence_detail != LEDGER_VERIFY_NOT_CHECKED
        said = claimed[row.control_id]
        if live_unknown and said.evidenced is not None:
            detail = one_line(CALLER_ASSERTED_PREFIX + said.evidence_detail)
            if said.evidenced is True:
                asserted.add(row.control_id)
                row = row.model_copy(update={"evidenced": None, "evidence_detail": detail})
            else:
                row = row.model_copy(update={"evidenced": False, "evidence_detail": detail})
        rows.append(row)
    return checked.model_copy(update={"controls": rows}), asserted


def generate_pack(
    manifest: dict[str, Any],
    *,
    signer: str,
    stale_store: Any,
    agent_id: str | None = None,
    sources: EvidenceSources | None = None,
    caller_sources: EvidenceSources | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Generate the evidence pack: (markdown, dict). Blocked, never fudged.

    ``sources`` is what this process collected live (``collect_evidence``). ``caller_sources`` is evidence a caller
    handed in (``POST /pack`` body): it is never evidenced on its own word, only where ``sources`` confirms the same
    verdict (B2). An ``agent_id`` with no answering source means live collection was requested and nothing answered:
    the evidence status is ``unknown`` and the pack never headlines "No gaps" (B2)."""
    signer = _checked_signer(signer)
    if isinstance(agent_id, str) and any(unicodedata.category(ch) == "Cs" for ch in agent_id):
        # PR 563 / Q-47 F-Q47-3: refused by name rather than cleaned, as for the signer (the API grammar 422s it first)
        raise ValueError("refusing to generate: agent_id holds an unpaired surrogate code unit")

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
    asserted: set[str] = set()
    if not _any_source(caller_sources):
        caller_sources = None  # N3: a body that names no source ({}) asserts nothing; the run is judged on its own
    requested = bool(agent_id)  # N1: an empty agent_id collects nothing (api.py), so it requests nothing either
    if caller_sources is not None:
        coverage, asserted = _caller_asserted_coverage(manifest, agent_id, caller_sources, sources)
        evidence_status = "caller-asserted"
        if requested and not _any_source(sources):
            # B1: the outage is a fact of the LIVE collection alone; whatever the caller's body holds (even {})
            # cannot turn "the ledger was asked and nothing answered" into a clean-looking pack
            evidence_status = "unknown"
    else:
        coverage = evaluate(manifest, agent_id=agent_id, sources=sources)
        if _any_source(sources):
            evidence_status = "collected"
        elif requested:
            evidence_status = "unknown"  # collection was requested (agent_id) and no service answered
        else:
            evidence_status = "not-requested"
    now = now or datetime.now(timezone.utc)
    generated_at = now.isoformat()

    # B7: the same list `crosswalk run` prints (engine.coverage_gaps), so the run and the pack never disagree
    gaps: list[dict[str, Any]] = coverage_gaps(coverage)
    # B2: what only a pack can say: a caller's claim this run did not confirm, and a full outage
    gaps += [{"control_id": cid, "kind": "caller-asserted", "detail": CALLER_ASSERTED_GAP}
             for cid in (c.control_id for c in coverage.controls) if cid in asserted]
    if evidence_status == "unknown":
        # a full outage: FC-L-01 reads "evidence not collected", but the ledger was asked and did not answer
        gaps.append({"control_id": "FC-L-01", "kind": "not-checked", "detail": LEDGER_NOT_CHECKED_GAP})

    lines: list[str] = []
    add = lines.append
    add("# Evidence Pack — FIELD control coverage")
    add("")
    add(f"- generated_at: {generated_at}")
    add(f"- Regulatory corpus version: {corpus_version}")
    add(f"- agent_id: {coverage.agent_id or 'manifest-only'}")
    add(f"- Evidence status: {evidence_status}")
    add(f"- Prepared for signature by: {signer}")
    add("- Document type: named-signer. This pack carries no cryptographic signature, hash or key; the Signature block at the end is completed by the named human.")
    add("")
    add(DISCLAIMER)
    add("")
    add("## Control coverage")
    add("")
    add(
        f"Manifest valid: {_yes_no(coverage.manifest_valid)}. Declared means "
        "the manifest carries the field; evidenced means a live artifact was "
        "collected and checked; not-collected means no evidence was gathered "
        "on this run — an honest unknown, not a pass; declared-only means the "
        "manifest declares it and no evidence artifact is read for it, so it "
        "is not evidenced; caller-asserted means the caller supplied the "
        "evidence and this run did not confirm it."
    )
    add("")
    add("| control_id | manifest_path | declared | evidenced |")
    add("|---|---|---|---|")
    for control in coverage.controls:
        if control.control_id in asserted:
            evidenced = "caller-asserted"
        elif control.control_id in coverage.declared_only:
            evidenced = "declared-only"
        elif control.evidenced is None:
            evidenced = "not-collected"
        else:
            evidenced = _yes_no(control.evidenced)
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
    if evidence_status == "unknown":
        add(EVIDENCE_UNKNOWN_HEADLINE + ".")
        add("")
    if gaps:
        add(
            "Over-conservative is survivable; false assurance is not. Each "
            "gap below stands until remediated and re-checked:"
        )
        add("")
        for gap in gaps:
            label = PACK_GAP_LABELS[gap["kind"]]
            add(f"- {gap['control_id']} — {label}: {gap['detail']}")
    else:
        add(
            "No gaps recorded on this run: every control is declared, and no "
            "collected evidence check failed. Controls marked not-collected "
            "above remain unknowns, not passes."
        )
    if coverage.declared_only:
        add("")
        add(declared_only_note(coverage))
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
            # one line each (PR 563 / Q-47 F-Q47-2): new flags are cleaned when marked (staleness._one_line), but a flag
            # stored before that, or a hand-edited store, is read back as it is
            bits = [f"framework: {one_line(entry.get('framework', 'unknown'))}"]
            if entry.get("flagged_at"):
                bits.append(f"flagged_at: {one_line(entry['flagged_at'])}")
            if entry.get("reason"):
                bits.append(f"reason: {one_line(entry['reason'])}")
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
        "agent_id": coverage.agent_id,
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
        "declared_only": coverage.declared_only,
        "evidence_status": evidence_status,
        "staleness": status,
        "manifest_valid": coverage.manifest_valid,
    }
    return markdown, result
