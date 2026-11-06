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

from field_core.manifest import EXPIRY_PATTERN, SCHEMA_VERSION, SEAL_ALGORITHMS, FieldManifest

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
    return parse_manifest_text(Path(path).read_text(encoding="utf-8"), path)


def parse_manifest_text(text: str, source: str | Path = "<text>") -> dict[str, Any]:
    """Parse manifest text already in memory (the resolver reads a bounded number of bytes once and parses
    THOSE, so the digest it caches and the manifest it serves come from the same bytes; C-1086)."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"manifest at {source} did not parse to a mapping")
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


def parse_expiry(raw: str) -> datetime | None:
    """Public reader for a manifest ``delegation.expiry`` string, shared by
    validation, the delegation-authority mint gate and lifecycle provision.

    A date-only value (``YYYY-MM-DD``) is 00:00:00 UTC of that day, NOT the end
    of it; a naive datetime is read as UTC; an offset datetime is that instant;
    anything unparseable is ``None`` (callers decide; the mint gate refuses).
    """
    return _parse_expiry(raw)


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
    # Dotted paths a targeted rule below already names; a schema violation at or under one of them is not repeated.
    named: set[str] = set()

    def gap(path: str, text: str) -> None:
        critical.append(text)
        named.add(path)

    sections_present = {s: isinstance(data.get(s), dict) for s in FIELD_SECTIONS}

    # --- Targeted critical-gap checks (named rules from the skill) ---
    if data.get("schema_version") != SCHEMA_VERSION:
        gap("schema_version", f"schema_version must be '{SCHEMA_VERSION}' "
            f"(got {data.get('schema_version')!r})")
    if not isinstance(data.get("agent"), dict) or not data.get("agent", {}).get("name"):
        gap("agent.name", "agent.name is missing — every manifest names its agent")

    for section in FIELD_SECTIONS:
        if not sections_present[section]:
            gap(section, f"required section '{section}' is missing")

    enforcement = data.get("enforcement") or {}
    if isinstance(enforcement, dict):
        kill_switch = enforcement.get("kill_switch")
        if not isinstance(kill_switch, dict) or not kill_switch.get(
            "endpoint"
        ) or not kill_switch.get("method"):
            gap("enforcement.kill_switch",
                "enforcement.kill_switch (endpoint + method) is missing — "
                "an agent without a kill switch is a critical gap")

    ledger = data.get("ledger") or {}
    if isinstance(ledger, dict):
        if ledger.get("cryptographic_seal") is not True:
            gap("ledger.cryptographic_seal",
                "ledger.cryptographic_seal must be true — an unsealed ledger "
                "is a critical gap")
        algo = ledger.get("seal_algorithm")
        if algo not in SEAL_ALGORITHMS:
            gap("ledger.seal_algorithm",
                f"ledger.seal_algorithm {algo!r} is not permitted "
                f"(allowed: {', '.join(SEAL_ALGORITHMS)}; 'none' is never valid)")

    delegation = data.get("delegation") or {}
    if isinstance(delegation, dict):
        if not delegation.get("granted_by"):
            gap("delegation.granted_by",
                "delegation.granted_by is missing — an agent without an "
                "authorization chain has no legitimate authority")
        if not delegation.get("scope"):
            gap("delegation.scope", "delegation.scope must list at least one authorized action")

    federated = data.get("federated") or {}
    if isinstance(federated, dict):
        if federated.get("isolated") is False and not federated.get("allowed_peers"):
            gap("federated.isolated",
                "federated.isolated is false but allowed_peers is empty — "
                "a non-isolated agent must declare its peers")
            named.add("federated.allowed_peers")

    # --- Full schema parse catches everything the targeted checks did not ---
    try:
        FieldManifest.model_validate(data)
    except ValidationError as exc:
        for line in _pydantic_gap_lines(exc):
            # Skip a schema error only when a targeted rule already named that dotted path (or one above it), or
            # the identical line is already listed. Never a substring test: it dropped every other violation.
            path = line.split(":", 1)[0]
            already_named = any(path == n or path.startswith(n + ".") for n in named)
            text = f"schema violation — {line}"
            if not already_named and text not in critical:
                critical.append(text)

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
        elif re.match(EXPIRY_PATTERN, delegation["expiry"]):
            # Passes the shape pattern but is not a calendar date (2026-13-45): a warning, not a critical gap (a
            # critical gap would turn the resolver's verdict to 'invalid'; that call is the owner's).
            warnings.append(
                f"delegation.expiry {delegation['expiry']} is not a real calendar date — "
                "it cannot be read as an expiry"
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
