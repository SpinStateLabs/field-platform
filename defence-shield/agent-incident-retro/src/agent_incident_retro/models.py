"""Pydantic models for Agent Incident Retro v0.1.

Every model is plain data: the engine builds them, the evidence layer hashes
them, the report renders them. Nothing here performs I/O.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The narrowest-allowed-floor of an `--allow-ip` network: nothing wider than /8 (IPv4) or /32 (IPv6) is accepted.
MIN_ALLOW_PREFIX_V4 = 8
MIN_ALLOW_PREFIX_V6 = 32

TOOL_NAME = "agent-incident-retro"
TOOL_VERSION = "0.1.1"
PACK_VERSION = "air/0.1"


class Verdict(str, Enum):
    ESCALATE = "ESCALATE"
    REVIEW = "REVIEW"
    AUTHORIZED = "AUTHORIZED"
    CLEAR = "CLEAR"


class Grade(str, Enum):
    """Attribution grade. G3 exists so the report can name it as Declared;
    the engine never emits it (no signature verification in v0.1)."""

    G0 = "G0"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"


class LineRef(BaseModel):
    """A pointer into a source file that a third party can re-check."""

    model_config = ConfigDict(frozen=True)

    input: str  # input label (file basename, de-duplicated)
    line: int  # 1-based
    sha256: str  # sha-256 of the exact line bytes (newline and trailing \r stripped)


class Request(BaseModel):
    ref: LineRef
    ts: datetime  # timezone-aware, UTC
    client_ip: str
    method: str
    path: str  # path only, percent-decoded
    query: str  # raw query string as logged (no leading '?'), NOT decoded
    status: int
    user_agent: str
    referer: str = ""
    raw: str  # the source line as text (utf-8, replacement on error)
    families: list[str] = Field(default_factory=list)  # payload families matched
    fingerprints: list[str] = Field(default_factory=list)  # normalised payload digests

    @property
    def is_payload(self) -> bool:
        return any(f != "debug_probe" for f in self.families)

    @property
    def is_probe(self) -> bool:
        return "debug_probe" in self.families

    @property
    def is_hostile(self) -> bool:
        return bool(self.families)


class ClauseHit(BaseModel):
    clause: str
    detail: str
    lines: list[LineRef] = Field(default_factory=list)


class SessionFeatures(BaseModel):
    requests: int
    duration_s: float
    distinct_paths: int
    status_4xx: int
    payload_requests: int
    probe_requests: int
    hostile_2xx: int
    families: dict[str, int]
    interarrival_median_s: float | None
    interarrival_cv: float | None


class Finding(BaseModel):
    """One flagged (or authorized) session. Hashed into its ledger event."""

    session_id: str
    client_ip: str
    user_agent: str
    first_ts: datetime
    last_ts: datetime
    verdict: Verdict
    grade: Grade
    grade_basis: str
    markers: list[str] = Field(default_factory=list)
    clauses: list[ClauseHit]
    features: SessionFeatures
    campaign_ids: list[str] = Field(default_factory=list)
    authorized_by: str | None = None
    requests: list[Request]


class InputFile(BaseModel):
    label: str
    sha256: str
    bytes: int
    lines: int
    parsed: int
    unparsed: int
    format: str


class Campaign(BaseModel):
    campaign_id: str
    fingerprint: str
    family: str
    client_ips: list[str]
    session_ids: list[str]
    example: LineRef


class RetroConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_gap_s: float = 1800.0
    pivot_window_s: float = 300.0
    cadence_min_requests: int = 20
    cadence_cv_max: float = 0.35
    include_raw: bool = True
    allow_ips: list[str] = Field(default_factory=list)
    allow_ua_substrings: list[str] = Field(default_factory=list)

    @field_validator("allow_ips")
    @classmethod
    def _no_catch_all_allowlist(cls, entries: list[str]) -> list[str]:
        """An allowlist entry that is a real network must not be a catch-all or too wide (C-240, D-20): `0.0.0.0/0`
        or `::/0` would mark every hostile client AUTHORIZED. The floor is /8 for IPv4 and /32 for IPv6; an IPv4-mapped
        IPv6 network (`::ffff:a.b.c.d/N`, N >= 96) is read as the IPv4 network it is. An entry that is not a network at
        all keeps its old behaviour (it matches only an identical string, so it cannot widen anything)."""
        for entry in entries:
            try:
                net = ipaddress.ip_network(entry.strip(), strict=False)
            except ValueError:
                continue
            version, prefix = net.version, net.prefixlen
            if version == 6 and net.network_address.ipv4_mapped is not None and prefix >= 96:
                version, prefix = 4, prefix - 96
            floor = MIN_ALLOW_PREFIX_V4 if version == 4 else MIN_ALLOW_PREFIX_V6
            if prefix < floor:
                raise ValueError(
                    f"allow_ips entry {entry!r} is refused: a network wider than /{floor} (IPv{version}) would mark "
                    f"nearly every client AUTHORIZED; list the operators' own addresses or narrower networks")
        return entries


class RetroResult(BaseModel):
    tool: dict[str, str]
    config: RetroConfig
    inputs: list[InputFile]
    sessions_total: int
    requests_total: int
    window_first: datetime | None
    window_last: datetime | None
    findings: list[Finding]
    campaigns: list[Campaign]
    counts: dict[str, Any]
