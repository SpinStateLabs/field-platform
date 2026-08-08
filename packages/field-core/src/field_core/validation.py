"""``field validate`` — parity with the shipped Force-Field plugin skill.

Reproduces the validation semantics documented in the plugin's SKILL.md:

- Status: VALID / VALID_WITH_WARNINGS / INVALID
- Critical gaps (blocking): missing sections, missing kill switch,
  missing delegation grantor, unsealed ledger, invalid seal algorithm,
  non-isolated agent with no peers, plus any remaining schema violations.
- Warnings (non-blocking): unresolved REPLACE-ME values, missing
  runtime_protocol, past or near-term delegation expiry.

Validation operates on the raw dict first so a broken manifest yields a
gap report, not a stack trace.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from field_core.manifest import SCHEMA_VERSION, SEAL_ALGORITHMS, FieldManifest

FIELD_SECTIONS = ("federated", "identity", "enforcement", "ledger", "delegation")

NEAR_TERM_EXPIRY_DAYS = 30

_PLACEHOLDER = "REPLACE-ME"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"


class ValidationResult(BaseModel):
    path: str | None = None
    status: ValidationStatus
    schema_version: str = SCHEMA_VERSION
    sections_present: dict[str, bool]
    critical_gaps: list[str]
    warnings: list[str]
    runtime_protocol: str

    @property
    def ok(self) -> bool:
        return self.status is not ValidationStatus.INVALID


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load a manifest YAML (or JSON — YAML is a superset) into a dict."""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"manifest at {path} did not parse to a mapping")
    return data


def _walk_placeholders(node: Any, dotted: str, hits: list[str]) -> None:
    if isinstance(node, str):
        if _PLACEHOLDER in node:
            hits.append(dotted)
    elif isinstance(node, dict):
        for key, value in node.items():
            _walk_placeholders(value, f"{dotted}.{key}" if dotted else str(key), hits)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk_placeholders(value, f"{dotted}[{i}]", hits)


def _parse_expiry(raw: str) -> datetime | None:
    value = raw.strip()
    try:
        if len(value) == 10:
            parsed = date.fromisoformat(value)
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
        normalized = value.replace(" ", "T").replace("Z", "+00:00")
        parsed_dt = datetime.fromisoformat(normalized)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt
    except ValueError:
        return None


def _pydantic_gap_lines(exc: ValidationError) -> list[str]:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"{loc}: {err['msg']}")
    return lines


def validate_manifest_data(
    data: dict[str, Any],
    path: str | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    now = now or datetime.now(timezone.utc)
    critical: list[str] = []
    warnings: list[str] = []

    sections_present = {s: isinstance(data.get(s), dict) for s in FIELD_SECTIONS}

    # --- Targeted critical-gap checks (named rules from the skill) ---
    if data.get("schema_version") != SCHEMA_VERSION:
        critical.append(
            f"schema_version must be '{SCHEMA_VERSION}' "
            f"(got {data.get('schema_version')!r})"
        )
    if not isinstance(data.get("agent"), dict) or not data.get("agent", {}).get("name"):
        critical.append("agent.name is missing — every manifest names its agent")

    for section in FIELD_SECTIONS:
        if not sections_present[section]:
            critical.append(f"required section '{section}' is missing")

    enforcement = data.get("enforcement") or {}
    if isinstance(enforcement, dict):
        kill_switch = enforcement.get("kill_switch")
        if not isinstance(kill_switch, dict) or not kill_switch.get(
            "endpoint"
        ) or not kill_switch.get("method"):
            critical.append(
                "enforcement.kill_switch (endpoint + method) is missing — "
                "an agent without a kill switch is a critical gap"
            )

    ledger = data.get("ledger") or {}
    if isinstance(ledger, dict):
        if ledger.get("cryptographic_seal") is not True:
            critical.append(
                "ledger.cryptographic_seal must be true — an unsealed ledger "
                "is a critical gap"
            )
        algo = ledger.get("seal_algorithm")
        if algo not in SEAL_ALGORITHMS:
            critical.append(
                f"ledger.seal_algorithm {algo!r} is not permitted "
                f"(allowed: {', '.join(SEAL_ALGORITHMS)}; 'none' is never valid)"
            )

    delegation = data.get("delegation") or {}
    if isinstance(delegation, dict):
        if not delegation.get("granted_by"):
            critical.append(
                "delegation.granted_by is missing — an agent without an "
                "authorization chain has no legitimate authority"
            )
        if not delegation.get("scope"):
            critical.append("delegation.scope must list at least one authorized action")

    federated = data.get("federated") or {}
    if isinstance(federated, dict):
        if federated.get("isolated") is False and not federated.get("allowed_peers"):
            critical.append(
                "federated.isolated is false but allowed_peers is empty — "
                "a non-isolated agent must declare its peers"
            )

    # --- Full schema parse catches everything the targeted checks did not ---
    try:
        FieldManifest.model_validate(data)
    except ValidationError as exc:
        seen = set(critical)
        for line in _pydantic_gap_lines(exc):
            # Skip schema errors already reported by a targeted named rule.
            prefix = line.split(":", 1)[0].split(".", 1)[0]
            already_named = any(prefix in gap or line in seen for gap in critical)
            if not already_named:
                critical.append(f"schema violation — {line}")

    # --- Warnings (non-blocking) ---
    placeholder_paths: list[str] = []
    _walk_placeholders(data, "", placeholder_paths)
    for dotted in placeholder_paths:
        warnings.append(f"unresolved {_PLACEHOLDER} value at {dotted}")

    if "runtime_protocol" not in data:
        warnings.append(
            "runtime_protocol absent — FIELD wraps FORCE; flag for review"
        )

    if isinstance(delegation, dict) and isinstance(delegation.get("expiry"), str):
        expiry_dt = _parse_expiry(delegation["expiry"])
        if expiry_dt is not None:
            if expiry_dt <= now:
                warnings.append(
                    f"delegation.expiry {delegation['expiry']} is in the past — "
                    "the delegation has lapsed"
                )
            elif expiry_dt <= now + timedelta(days=NEAR_TERM_EXPIRY_DAYS):
                warnings.append(
                    f"delegation.expiry {delegation['expiry']} is near-term "
                    f"(within {NEAR_TERM_EXPIRY_DAYS} days)"
                )

    # --- Runtime protocol summary line ---
    runtime = data.get("runtime_protocol")
    if isinstance(runtime, dict) and runtime.get("name"):
        preset = runtime.get("preset")
        runtime_summary = f"{runtime['name']}" + (f" — preset {preset}" if preset else "")
    else:
        runtime_summary = "absent"

    if critical:
        status = ValidationStatus.INVALID
    elif warnings:
        status = ValidationStatus.VALID_WITH_WARNINGS
    else:
        status = ValidationStatus.VALID

    return ValidationResult(
        path=path,
        status=status,
        sections_present=sections_present,
        critical_gaps=critical,
        warnings=warnings,
        runtime_protocol=runtime_summary,
    )


def validate_manifest_file(
    path: str | Path, now: datetime | None = None
) -> ValidationResult:
    return validate_manifest_data(load_manifest(path), path=str(path), now=now)


def render_validation_report(result: ValidationResult) -> str:
    """Render the exact output format documented in the plugin SKILL.md."""
    mark = {True: "✓", False: "✗"}
    lines = [
        f"FIELD manifest validation — {result.path or '<in-memory>'}",
        f"  Schema: {result.schema_version}",
        f"  Status: {result.status.value}",
        "",
        "  Required sections present:",
    ]
    for section in FIELD_SECTIONS:
        pad = " " * (12 - len(section))
        lines.append(f"    {section}:{pad}[{mark[result.sections_present[section]]}]")
    lines += ["", "  Critical gaps (blocking):"]
    lines += [f"    - {g}" for g in result.critical_gaps] or ["    - None"]
    lines += ["", "  Warnings (non-blocking):"]
    lines += [f"    - {w}" for w in result.warnings] or ["    - None"]
    lines += ["", f"  Runtime protocol: {result.runtime_protocol}"]
    return "\n".join(lines)
