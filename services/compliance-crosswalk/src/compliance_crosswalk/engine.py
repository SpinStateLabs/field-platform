"""Coverage evaluation: declared (manifest) vs. evidenced (live artifacts)."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS, Citation, Control
from field_core.validation import validate_manifest_data


#: Unicode categories that cannot appear in text printed into the report or the evidence pack: control (Cc), invisible
#: format (Cf: marks, zero-width characters, bidirectional overrides), line or paragraph separator (Zl, Zp) and, from
#: PR 563 / Q-47 F-Q47-3, an unpaired surrogate (Cs: it cannot be encoded as UTF-8, so a response or a pack file
#: carrying it was a server error). The signer is REFUSED for holding one (evidence_pack._checked_signer); free text
#: from a caller or a service answer is instead made one line (S5-17).
REFUSED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})
ONE_LINE_MAX = 200


def one_line(value: Any, limit: int = ONE_LINE_MAX) -> str:
    """``value`` as ONE line of table-safe text: every control, format and line-break character and every ``|`` (a
    table cell edge) becomes a space, runs of whitespace collapse, and the result is capped at ``limit`` characters
    (ending in an ellipsis when it was cut). So it cannot start a new line, heading, table row, ``Signer:`` line or
    signature block: a forged ``\n\n## Signature\n\nSigner: Ann`` stays inside the one line it was printed on.
    It does NOT escape inline Markdown (``**bold**``, links, ``![image](...)``) or raw inline HTML: the text stays on
    one line of the Markdown, but a renderer that passes raw HTML still reads it as markup, and an unclosed raw-text
    tag (``<script>``, ``<style>``, ``<textarea>``, ``<title>``, ``<xmp>``, ``<plaintext>``) hides EVERYTHING after it
    in the rendered page, the signature block included."""
    text = "".join(
        " " if (c == "|" or unicodedata.category(c) in REFUSED_CATEGORIES) else c for c in str(value)
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


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
    citations: dict[str, Citation]


class CoverageReport(BaseModel):
    agent_id: str | None
    generated_at: str
    manifest_valid: bool
    frameworks: dict[str, str]
    controls: list[ControlCoverage]
    declared_count: int
    evidenced_count: int
    evidence_collected: bool
    #: declared controls for which no evidence artifact is read: neither evidenced nor a gap
    declared_only: list[str] = []
    citation_status: str = (
        "Citations are source-grounded: each cited entry names the verified "
        "reference, source URL, and retrieval date (see INGESTION_LOG). "
        "Unverified mappings carry NO reference and are marked pending-text; "
        "ISO/IEC 42001 is pending-purchase (paid standard). EU AI Act text "
        "was verified via the AI Act Explorer mirror — cross-check EUR-Lex "
        "(CELEX:32024R1689) before external publication."
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


# FC-E-04..06 (ADR-0074): the Claude Code Enforcement Gate enforces these keys on the developer
# host and writes a host-local ledger. Nothing here can see that ledger, so these controls are
# declaration-only and must never read as estate-evidenced.
GATE_CONTROL_IDS = ("FC-E-04", "FC-E-05", "FC-E-06")
GATE_NOTE = "declared, enforced locally by the Claude Code gate, no estate evidence"
#: FC-L-01 when evidence was collected but the ledger gave no /verify answer (503 busy, unreachable): not checked,
#: neither verified nor failed. The evidence pack keys its "not-checked" gap on this exact detail.
LEDGER_VERIFY_NOT_CHECKED = "ledger verify unavailable (busy or unreachable) - chain not verified; retry"
#: gap kind -> its label in a Markdown "Gaps" list (the JSON carries the kind itself)
GAP_LABELS = {"not-declared": "not declared", "not-evidenced": "not evidenced", "not-checked": "not checked"}
#: the FC-L-01 "not-checked" gap detail: fixed text, so Markdown and JSON say the same
LEDGER_NOT_CHECKED_GAP = (
    "the ledger did not answer /verify (busy or unreachable), so the chain was not verified on this run; "
    "this is not a pass: re-run the pack"
)
GATE_NOTE_UNDECLARED = ("not declared in the manifest, so the Claude Code gate enforces nothing for this key "
                        "(a manifest that is not governed by the gate legitimately omits it); no estate evidence")


#: Controls that rest on the manifest declaration: this service reads no artifact that shows they hold. They are never
#: evidenced and never failed (``evidenced`` None); a declared one is listed in ``CoverageReport.declared_only``.
DECLARED_ONLY_CONTROL_IDS = ("FC-E-03", "FC-F-01", "FC-L-02")
DECLARED_ONLY_DETAIL = "declared only: no evidence artifact is read for this control"
DECLARED_ONLY_UNDECLARED = "not declared in the manifest; no evidence artifact is read for this control"


def _gate_declared(control: Control, manifest: dict[str, Any]) -> tuple[bool, str] | None:
    """Declaration test for FC-E-04..06; a key that is present but empty declares nothing."""
    cid = control.control_id
    if cid == "FC-E-04":
        ia = _get_path(manifest, "enforcement.irreversible_actions")
        if isinstance(ia, dict):
            patterns = ia.get("deny_patterns")
            if (isinstance(patterns, list) and any(patterns)) or ia.get("session_written_exec") == "deny":
                return True, "irreversible_actions declares deny_patterns and/or session_written_exec: deny"
        return False, "enforcement.irreversible_actions declares no deny_patterns and no session_written_exec: deny"
    if cid == "FC-E-05":
        paths = _get_path(manifest, "enforcement.protected_paths")
        if isinstance(paths, list) and any(paths):
            return True, f"{len(paths)} protected_paths pattern(s) declared"
        return False, "enforcement.protected_paths absent or empty"
    if cid == "FC-E-06":
        limits = _get_path(manifest, "enforcement.rate_limits")
        for entry in limits if isinstance(limits, list) else []:
            if (isinstance(entry, dict) and str(entry.get("action") or "").strip().casefold() == "tool_call"
                    and str(entry.get("period") or "").strip().casefold() in ("session", "per-session", "per_session")):
                return True, f"tool_call budget declared (max {entry.get('max')} per session)"
        return False, "no rate_limits entry {action: tool_call, period: session}"
    return None


def _declared(control: Control, manifest: dict[str, Any]) -> tuple[bool, str]:
    if control.manifest_path == "(registry)":
        return True, "not a manifest field — see evidence"
    gate = _gate_declared(control, manifest)
    if gate is not None:
        value = _get_path(manifest, control.manifest_path)
        if gate[0] and _has_placeholder(value):
            return False, f"{control.manifest_path} contains unresolved placeholder(s)"
        return gate
    value = _get_path(manifest, control.manifest_path)
    if value is None:
        return False, f"{control.manifest_path} absent"
    if _has_placeholder(value):
        return False, f"{control.manifest_path} contains unresolved placeholder(s)"
    return True, f"{control.manifest_path} = {value!r}"[:120]


def _evidenced(
    control: Control, sources: EvidenceSources, agent_id: str | None
) -> tuple[bool | None, str]:
    if control.control_id in GATE_CONTROL_IDS:
        # None, not True: the estate holds no evidence for the gate, and not False: an absent
        # artifact the estate never receives is not a failed check (no evidence-pack gap).
        return None, GATE_NOTE
    if control.control_id in DECLARED_ONLY_CONTROL_IDS:
        # FC-E-03's escalation events show that the trigger fired, not that the policy holds: counted for the reader,
        # never a verdict. No count is printed when no event counts were read (an unread ledger is not a zero).
        events = sources.ledger_event_types
        if control.control_id == "FC-E-03" and events is not None:
            n = events.get("conformance.escalate", 0)
            s = events.get("conformance.shadow_escalate", 0)
            return None, (f"declared only; {n} enforced + {s} shadow (log-only) escalation event(s) observed; "
                          "no evidence artifact shows the policy holds")
        return None, DECLARED_ONLY_DETAIL
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
        owner = (sources.registry_record or {}).get("owner")
        ok = isinstance(owner, str) and bool(owner.strip())  # blank is no owner; a non-str is none
        return ok, "human owner on registry record" if ok else "no owner on record"
    if control.control_id == "FC-L-01":
        if sources.ledger_verify is None:
            # No /verify answer (503 busy, refused, unreachable): the chain was not checked, which is
            # not a failed check, so unevidenced (None), not False. It is still never silent: the
            # evidence pack records a "not-checked" gap for it (don.reviewer C1 on the rebuild of PR
            # 1093: the 503 can be provoked, so "no gaps" must never be the headline then).
            return None, LEDGER_VERIFY_NOT_CHECKED
        verify = sources.ledger_verify
        if "ok" not in verify and "http_status" in verify:
            # The ledger answered (not 503) but gave no usable verdict: not verified, a gap.
            return False, (
                f"ledger answered HTTP {verify['http_status']} to /verify - "
                "chain NOT verified; investigate"
            )
        if verify.get("tls_failed") is True and "ok" not in verify:
            return False, "ledger TLS failed: chain NOT verified; investigate"
        ok = verify.get("ok") is True  # strict: "false"/1/missing never read as verified
        return ok, (
            "ledger chain verified"
            if ok
            else f"ledger verify failed: {verify.get('reason') or 'no ok:true in /verify answer'}"
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
        revoked = sum(1 for t in (sources.tokens or []) if t.get("revoked") is True)
        ok = n > 0 or revoked > 0
        return ok, f"{n} revoke event(s), {revoked} revoked token(s)"
    # a control with no rule above has nothing to read: never evidenced by default
    return None, DECLARED_ONLY_DETAIL


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
        if control.control_id in GATE_CONTROL_IDS and not declared:
            evidence_detail = GATE_NOTE_UNDECLARED  # never say "enforced" for a key the manifest does not declare
        if control.control_id in DECLARED_ONLY_CONTROL_IDS and not declared:
            evidence_detail = DECLARED_ONLY_UNDECLARED  # never say "declared only" for an undeclared key
        coverages.append(
            ControlCoverage(
                control_id=control.control_id,
                letter=control.letter,
                manifest_path=control.manifest_path,
                statement=control.statement,
                declared=declared,
                # S5-17: both details can carry caller text (a manifest value, a ledger-verify reason); one line each,
                # in the JSON as well as the Markdown, so the two never disagree
                declared_detail=one_line(declared_detail),
                evidenced=evidenced,
                evidence_detail=one_line(evidence_detail),
                citations=control.citations,
            )
        )
    evidence_collected = any(c.evidenced is not None for c in coverages)
    return CoverageReport(
        agent_id=None if agent_id is None else one_line(agent_id),
        generated_at=datetime.now(timezone.utc).isoformat(),
        manifest_valid=validation.ok,
        frameworks=FRAMEWORKS,
        controls=coverages,
        declared_count=sum(1 for c in coverages if c.declared),
        evidenced_count=sum(1 for c in coverages if c.evidenced),
        evidence_collected=evidence_collected,
        # listed in DECLARED_ONLY_CONTROL_IDS order (not the matrix order), so the note reads the same everywhere
        declared_only=[cid for cid in DECLARED_ONLY_CONTROL_IDS
                       if any(c.control_id == cid and c.declared for c in coverages)],
    )


def _not_checked(control: ControlCoverage) -> bool:
    """FC-L-01 with evidence collected but no /verify answer: not checked (neither verified nor failed)."""
    return (control.evidenced is None and control.control_id == "FC-L-01"
            and control.evidence_detail == LEDGER_VERIFY_NOT_CHECKED)


def coverage_gaps(report: CoverageReport) -> list[dict[str, Any]]:
    """Every gap a coverage report shows, in control order: not declared, not evidenced (a collected check failed),
    not checked (FC-L-01: the ledger gave no /verify answer). The evidence pack and ``crosswalk run`` both print this
    list (B7), so the two can never disagree. An offline run's uncollected evidence is an unknown, not a gap."""
    gaps: list[dict[str, Any]] = []
    for control in report.controls:
        if not control.declared:
            gaps.append({"control_id": control.control_id, "kind": "not-declared", "detail": control.declared_detail})
        if control.evidenced is False:
            gaps.append({"control_id": control.control_id, "kind": "not-evidenced", "detail": control.evidence_detail})
        elif _not_checked(control):
            # don.reviewer C1 (rebuild of PR 1093): not checked is not failed, but it is never silent; a provoked
            # 503 on /verify must not let a report say "No gaps recorded" as it would for a verified chain
            gaps.append({"control_id": control.control_id, "kind": "not-checked", "detail": LEDGER_NOT_CHECKED_GAP})
    return gaps


def declared_only_note(report: CoverageReport) -> str:
    """The sentence that goes with any headline when a declared control has no evidence behind it; "" when none."""
    if not report.declared_only:
        return ""
    return (f"Declared only (the manifest declares it and no evidence artifact is read, so it is neither evidenced "
            f"nor a gap): {', '.join(report.declared_only)}.")


def render_markdown(report: CoverageReport) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# Compliance crosswalk — {report.agent_id or '<manifest only>'}")
    add("")
    add(f"*Generated:* {report.generated_at} · *Manifest valid:* "
        f"{'yes' if report.manifest_valid else 'NO'}")
    add(f"*Coverage:* {report.declared_count}/{len(report.controls)} declared · "
        f"{report.evidenced_count}/{len(report.controls)} evidenced · "
        f"{len(report.declared_only)}/{len(report.controls)} declared only"
        + ("" if report.evidence_collected else " (evidence not collected)"))
    add("")
    add(f"> **Citation status:** {report.citation_status}")
    add("")
    add("| Control | L | Statement | Declared | Evidenced | Evidence |")
    add("|---|---|---|---|---|---|")
    for c in report.controls:
        # B7: an unanswered /verify is "✗" (not verified), never the "—" of a run that collected nothing
        evidenced = ("✗" if _not_checked(c) else "—") if c.evidenced is None else ("✓" if c.evidenced else "✗")
        if c.control_id in report.declared_only:
            evidenced = "declared only"
        add(
            f"| {c.control_id} | {c.letter} | {c.statement} | "
            f"{'✓' if c.declared else '✗'} | {evidenced} | {c.evidence_detail} |"
        )
    add("")
    add("## Gaps")
    add("")
    gaps = coverage_gaps(report)
    if gaps:
        add("Each gap stands until remediated and re-checked:")
        add("")
        for gap in gaps:
            add(f"- {gap['control_id']} — {GAP_LABELS[gap['kind']]}: {gap['detail']}")
    elif report.evidence_collected:
        add("No gaps recorded on this run: every control is declared, and no collected evidence check failed.")
    else:
        add("No declaration gaps.")
    if report.declared_only:
        add("")
        add(declared_only_note(report))
    if not report.evidence_collected:
        add("")
        add("Evidence was not collected (offline run): every \"—\" above is an unknown, not a pass.")
    add("")
    add("## Framework mapping (source-grounded citations)")
    add("")
    add("| Control | " + " | ".join(report.frameworks) + " |")
    add("|---|" + "---|" * len(report.frameworks))
    for c in report.controls:
        cells = []
        for f in report.frameworks:
            citation = c.citations[f]
            if citation.status == "cited":
                cells.append(citation.reference)
            else:
                cells.append(f"*{citation.status}*")
        add(f"| {c.control_id} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
