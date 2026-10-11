"""Evidence: field-core hash-chained, Ed25519-signed events and the signed pack.

Reuses field-core primitives unchanged: ``make_event`` (sha-256 chain from 64
zeros), ``verify_chain``, ``sign_event`` / ``verify_event_signature`` and
``key_fingerprint``. The pack signature is Ed25519 over the canonical JSON of
the pack minus its ``signature`` key.

Trust model: ``verify`` takes the verifier's OWN copy of the signer's public
key. The PEM embedded in the pack is informational; anyone can re-sign an
edited pack with a fresh key, so a pack is only as trustworthy as the key the
verifier pins.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel

from field_core.ledger import GENESIS_HASH, LedgerEvent, make_event, verify_chain
from field_core.signing import (
    key_fingerprint,
    load_ed25519_private_key,
    load_ed25519_public_key,
    sign_event,
    verify_event_signature,
)

from .models import PACK_VERSION, TOOL_NAME, TOOL_VERSION, Finding, RetroResult
from .parsers import file_sha256, line_sha256, split_lines

AGENT_ID = "defence-shield/agent-incident-retro"


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def finding_digest(finding: Finding | dict[str, Any]) -> str:
    data = finding.model_dump(mode="json") if isinstance(finding, Finding) else finding
    return sha256_hex(canonical(data))


def _finding_refs(finding: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for clause in finding.get("clauses", []):
        refs.extend(clause.get("lines", []))
    for req in finding.get("requests", []):
        refs.append(req["ref"])
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for ref in refs:
        unique.setdefault((ref["input"], ref["line"]), ref)
    return [unique[k] for k in sorted(unique)]


def build_events(result: RetroResult, generated_at: str, private_key_pem: str) -> list[LedgerEvent]:
    """The run as a signed chain: started, one flagged event per finding,
    one linked event per campaign, completed."""
    config_digest = sha256_hex(canonical(result.config.model_dump(mode="json")))
    plan: list[tuple[str, dict[str, Any]]] = [
        (
            "retro.run.started",
            {
                "tool": TOOL_NAME,
                "tool_version": TOOL_VERSION,
                "inputs": [{"label": i.label, "sha256": i.sha256, "bytes": i.bytes} for i in result.inputs],
                "config_sha256": config_digest,
            },
        )
    ]
    for f in result.findings:
        data = f.model_dump(mode="json")
        plan.append(
            (
                "retro.session.flagged",
                {
                    "session_id": f.session_id,
                    "verdict": f.verdict.value,
                    "grade": f.grade.value,
                    "clauses": [c.clause for c in f.clauses],
                    "finding_sha256": finding_digest(data),
                    "evidence_lines": _finding_refs(data),
                },
            )
        )
    for c in result.campaigns:
        plan.append(("retro.campaign.linked", c.model_dump(mode="json")))
    plan.append(
        (
            "retro.run.completed",
            {
                "sessions_total": result.sessions_total,
                "requests_total": result.requests_total,
                "verdicts": result.counts.get("verdicts", {}),
                "unparsed_lines": sum(i.unparsed for i in result.inputs),
            },
        )
    )
    events: list[LedgerEvent] = []
    prev = GENESIS_HASH
    for index, (event_type, payload) in enumerate(plan):
        event = make_event(
            event_type,
            payload,
            prev_hash=prev,
            agent_id=AGENT_ID,
            ts=generated_at,
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"air:{generated_at}:{index}")),
        )
        event = sign_event(event, private_key_pem)
        events.append(event)
        prev = event.hash
    return events


def public_pem_from_private(private_key_pem: str) -> str:
    from cryptography.hazmat.primitives import serialization

    key = load_ed25519_private_key(private_key_pem)
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def build_pack(result: RetroResult, report_md: str, generated_at: str, private_key_pem: str) -> dict[str, Any]:
    events = build_events(result, generated_at, private_key_pem)
    public_pem = public_pem_from_private(private_key_pem)
    pack: dict[str, Any] = {
        "pack_version": PACK_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": generated_at,
        "inputs": [i.model_dump(mode="json") for i in result.inputs],
        "config": result.config.model_dump(mode="json"),
        "summary": {
            "sessions_total": result.sessions_total,
            "requests_total": result.requests_total,
            "window_first": result.window_first.isoformat() if result.window_first else None,
            "window_last": result.window_last.isoformat() if result.window_last else None,
            "counts": result.counts,
        },
        "findings": [f.model_dump(mode="json") for f in result.findings],
        "campaigns": [c.model_dump(mode="json") for c in result.campaigns],
        "events": [e.model_dump(mode="json") for e in events],
        "chain": {"genesis": GENESIS_HASH, "head": events[-1].hash, "length": len(events)},
        "report_sha256": sha256_hex(report_md.encode("utf-8")),
        "signer": {
            "alg": "Ed25519",
            "public_key_fingerprint": key_fingerprint(public_pem),
            "public_key_pem": public_pem,
        },
    }
    private = load_ed25519_private_key(private_key_pem)
    pack["signature"] = base64.b64encode(private.sign(canonical(pack))).decode("ascii")
    return pack


# ------------------------------------------------------------------ verify


class Check(BaseModel):
    name: str
    ok: bool
    detail: str


class VerifyResult(BaseModel):
    ok: bool
    checks: list[Check]


def verify_pack(
    pack: dict[str, Any],
    public_key_pem: str,
    report_bytes: bytes | None = None,
    sources: dict[str, bytes] | None = None,
) -> VerifyResult:
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(Check(name=name, ok=ok, detail=detail))

    # 1. the key the verifier pinned is the key the pack names
    try:
        pinned_fp = key_fingerprint(public_key_pem)
    except ValueError as exc:
        add("pinned key", False, f"not an Ed25519 public key: {exc}")
        return VerifyResult(ok=False, checks=checks)
    named_fp = (pack.get("signer") or {}).get("public_key_fingerprint")
    add("signer fingerprint", pinned_fp == named_fp, f"pinned {pinned_fp[:16]}… vs pack {str(named_fp)[:16]}…")

    # 2. pack signature (over everything except 'signature')
    body = {k: v for k, v in pack.items() if k != "signature"}
    try:
        load_ed25519_public_key(public_key_pem).verify(
            base64.b64decode(str(pack.get("signature", "")), validate=True), canonical(body)
        )
        add("pack signature", True, "Ed25519 over the canonical pack")
    except (InvalidSignature, ValueError, TypeError) as exc:
        add("pack signature", False, f"invalid: {type(exc).__name__}")

    # 3. chain + 4. per-event signatures
    try:
        events = [LedgerEvent(**e) for e in pack.get("events", [])]
    except Exception as exc:  # malformed event shape is a failed check, not a crash
        add("events parse", False, f"{type(exc).__name__}: {exc}"[:200])
        return VerifyResult(ok=False, checks=checks)
    chain = verify_chain(events)
    head_ok = bool(events) and events[-1].hash == (pack.get("chain") or {}).get("head")
    add("hash chain", chain.ok and head_ok, chain.reason or f"{chain.length} events, head matches: {head_ok}")
    bad_sigs = [i for i, e in enumerate(events) if not verify_event_signature(e, public_key_pem)]
    add("event signatures", not bad_sigs, "all valid" if not bad_sigs else f"invalid at index {bad_sigs[:5]}")

    # 5. findings are bound to their flagged events, in order
    flagged = [e for e in events if e.event_type == "retro.session.flagged"]
    findings = pack.get("findings", [])
    mismatches: list[str] = []
    if len(flagged) != len(findings):
        mismatches.append(f"{len(findings)} findings vs {len(flagged)} flagged events")
    for f, e in zip(findings, flagged):
        if finding_digest(f) != e.payload.get("finding_sha256") or f.get("session_id") != e.payload.get("session_id"):
            mismatches.append(str(f.get("session_id")))
    add("findings bound to events", not mismatches, "all digests match" if not mismatches else f"mismatch: {mismatches[:5]}")

    # 5b. the inputs the chain's first event names are the inputs the pack lists
    started = next((e for e in events if e.event_type == "retro.run.started"), None)
    chain_inputs = [(i.get("label"), i.get("sha256")) for i in (started.payload.get("inputs", []) if started else [])]
    pack_inputs = [(i.get("label"), i.get("sha256")) for i in pack.get("inputs", [])]
    add("inputs bound to chain", started is not None and chain_inputs == pack_inputs, "match" if chain_inputs == pack_inputs else "differ")

    # 6. displayed raw lines match their hashes (when the bytes were utf-8)
    raw_bad: list[str] = []
    for f in findings:
        for req in f.get("requests", []):
            raw = req.get("raw") or ""
            if raw and "�" not in raw and line_sha256(raw.encode("utf-8")) != req["ref"]["sha256"]:
                raw_bad.append(f"{req['ref']['input']}:{req['ref']['line']}")
    add("raw lines match hashes", not raw_bad, "ok" if not raw_bad else f"mismatch: {raw_bad[:5]}")

    # 7. report digest
    if report_bytes is not None:
        ok = sha256_hex(report_bytes) == pack.get("report_sha256")
        add("report digest", ok, "report.md matches" if ok else "report.md differs from the signed digest")

    # 8. sources: file digests and every cited line
    if sources is not None:
        inputs = {i["label"]: i for i in pack.get("inputs", [])}
        missing = sorted(set(inputs) - set(sources))
        add("sources supplied", not missing, "all inputs supplied" if not missing else f"missing: {missing}")
        file_bad = [label for label, data in sources.items() if label in inputs and file_sha256(data) != inputs[label]["sha256"]]
        unknown = sorted(set(sources) - set(inputs))
        add(
            "source file digests",
            not file_bad and not unknown,
            "all match" if not (file_bad or unknown) else f"differ: {file_bad} unknown: {unknown}",
        )
        line_index = {label: dict(split_lines(data)) for label, data in sources.items()}
        cited: dict[tuple[str, int], str] = {}
        for e in flagged:
            for ref in e.payload.get("evidence_lines", []):
                cited[(ref["input"], ref["line"])] = ref["sha256"]
        line_bad = [
            f"{label}:{line}"
            for (label, line), digest in sorted(cited.items())
            if label in line_index and (line not in line_index[label] or line_sha256(line_index[label][line]) != digest)
        ]
        add("cited source lines", not line_bad, f"{len(cited)} lines match" if not line_bad else f"differ: {line_bad[:5]}")

    return VerifyResult(ok=all(c.ok for c in checks), checks=checks)
