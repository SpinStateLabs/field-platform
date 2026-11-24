"""Registry record models. Registry-owned; other services consume via HTTP."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from agent_registry.redaction import fingerprint, redact, redact_text


def _strip(value: Any) -> Any:
    """Strip surrounding whitespace from text (anything else is left for the type check to refuse)."""
    return value.strip() if isinstance(value, str) else value


#: Request-boundary text: stripped FIRST, then non-blank (where required) and bounded. A 422 never echoes the input
#: (the app's validation handler drops it). ``AgentRecord`` below stays lenient on purpose: a row written before these
#: bounds existed (a long name, a blank owner) must still read back, never 500 a GET.
MAX_NAME, MAX_OWNER, MAX_DOMAIN, MAX_MANIFEST_REF, MAX_ATTESTED_BY = 200, 200, 64, 512, 200
Name = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=MAX_NAME)]
Owner = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=MAX_OWNER)]
Domain = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=MAX_DOMAIN)]
#: Not stripped: a whitespace-only ref is SET (not "no ref") and the resolver refuses it (D3b, test_d3b_manifest_ref_resolves).
ManifestRef = Annotated[str, Field(max_length=MAX_MANIFEST_REF)]
AttestedBy = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=MAX_ATTESTED_BY)]


class AgentStatus(str, Enum):
    ACTIVE = "active"
    KILLED = "killed"
    RETIRED = "retired"


class AgentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1, description="Human owner — never an agent")
    domain: str = Field(
        default="general",
        description="Operating domain, e.g. finance, hr; kill-switch can kill by domain",
    )
    manifest_ref: str | None = Field(
        default=None, description="Path/URL of this agent's FIELD manifest"
    )
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attested_at: datetime | None = Field(
        default=None,
        description="Last human re-attestation (POST /agents/{id}/attest). "
        "Deliberately absent from AgentCreate/AgentUpdate: with extra='forbid' "
        "a PATCH that tries to set it is a 422, so the re-attestation clock "
        "cannot be reset by any ordinary record edit.",
    )
    attested_by: str | None = Field(
        default=None,
        description="Name the attester supplied. A recorded string, NOT an "
        "authenticated identity — see README 'Enforced vs. Declared'.",
    )


# What counts as "blank" for a name, an owner or a domain (R-PR511 C1; the same categories rule as attestation-reporter's
# org.py): a character is IGNORABLE when it is whitespace, or has Unicode category Cc (control, NUL, DEL), Cf (format:
# zero-width, bidirectional marks and embeddings, soft hyphen, invisible operators, tag characters), Zl, Zp, Zs (spaces),
# Cs (a lone surrogate) or Co (private use: no glyph of its own), or is one of the characters that render as nothing but
# are letters or marks to Unicode: the Hangul fillers, the braille blank, the combining grapheme joiner and the
# variation selectors. A value with nothing left once its ignorable ends are trimmed is blank. Ignorable characters
# INSIDE a value are kept (a Persian name keeps its ZWNJ). Decisions recorded here: tag characters and private-use
# characters are treated as blank although a font might draw them; and a TRAILING ignorable character is trimmed even when
# something visible precedes it (a trailing emoji variation selector U+FE0F or right-to-left mark U+200F is dropped): a name
# is stored as the plain text a human typed, and the same rule keeps domain and owner comparisons stable.
# Cn (unassigned, including the default-ignorable ones such as U+2065, U+FFF0 to U+FFF8, U+E0000, U+E0080 to U+E00FF, and
# every code point assigned later) is refused too: a name made only of code points no font draws is not a name (R-PR511 C3).
_IGNORABLE_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Zs", "Cs", "Co", "Cn"})
# U+17B4 and U+17B5 (Khmer inherent vowels) and U+180B to U+180D, U+180F (Mongolian free variation selectors) are category Mn
# but draw nothing on their own (R-PR511 C1 of the second re-review).
_IGNORABLE_EXTRA = frozenset(chr(c) for c in (0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800,
                                              0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F))


def _ignorable(ch: str) -> bool:
    cp = ord(ch)
    return (ch.isspace() or unicodedata.category(ch) in _IGNORABLE_CATEGORIES or ch in _IGNORABLE_EXTRA
            or 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF)


def _stripped_non_blank(v: str | None) -> str | None:
    """Request-boundary rule for name, owner and domain: ignorable characters (see above) are dropped from both ends and
    what is left must not be empty. ``None`` (PATCH: not sent) passes. AgentRecord (the read model) is deliberately NOT
    tightened: a legacy row must still read back."""
    if v is None:
        return None
    start, end = 0, len(v)
    while start < end and _ignorable(v[start]):
        start += 1
    while end > start and _ignorable(v[end - 1]):
        end -= 1
    if start == end:
        raise ValueError("must not be blank")
    return v[start:end]


#: What a NEW agent id may be (reviewer C-528 F-C528-1/-2): lower-case letters and digits in runs, separated by
#: ONE of ``.``, ``_`` or ``-``; no leading, trailing or doubled separator ("a1." and "a..1" would otherwise be
#: distinct agents that read as "a1" in a log), at most 64 characters (the width of the rotation events' ids).
#: Stored ids are not re-checked against this on read: a row written before it keeps working.
MAX_AGENT_ID_LENGTH = 64
_NEW_AGENT_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

#: What a NEW domain may be (backlog B80; Don, 2026-11-23: "Yes, ASCII only"): ASCII letters and digits in runs, separated
#: by ONE space, '.', '_' or '-'; no leading, trailing or doubled separator; at most MAX_DOMAIN (64) characters. Checked
#: AFTER the blank rule above has trimmed ignorable ends, so " finance " and a zero-width space before "finance" are still
#: stored as "finance". Anything left inside (a zero-width or no-break space, a soft hyphen, a fullwidth or Cyrillic
#: letter, a combining mark, a doubled space) is a 422 whose message is fixed and never quotes the value. Why: the
#: registry's domain filter folds ASCII case and trims spaces only, so a look-alike domain is silently missed by a domain
#: halt that names the real one. Stored rows are NOT re-checked on read (AgentRecord stays lenient, a legacy row must
#: still read back); counting them is deploy precondition P21, and the ops console's named fleet halt reports them.
_NEW_DOMAIN = re.compile(r"[A-Za-z0-9]+(?:[ ._-][A-Za-z0-9]+)*")
DOMAIN_RULE = "domain must be ASCII letters and digits separated by single spaces, '.', '_' or '-'"


def _new_domain(v: str | None) -> str | None:
    """The B80 write rule for a domain: the blank rule first (trim ignorable ends, refuse empty), then the ASCII shape.
    ``None`` (PATCH: not sent) passes."""
    v = _stripped_non_blank(v)
    if v is not None and not _NEW_DOMAIN.fullmatch(v):
        raise ValueError(DOMAIN_RULE)
    return v


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=MAX_AGENT_ID_LENGTH, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: Name
    owner: Owner
    domain: Domain = "general"
    manifest_ref: ManifestRef | None = None

    @field_validator("agent_id")
    @classmethod
    def _no_confusable_id(cls, value: str) -> str:
        if not _NEW_AGENT_ID.fullmatch(value):
            raise ValueError("agent_id must be lower-case letters and digits separated by single '.', '_' or '-'")
        return value

    @field_validator("name", "owner", "domain")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        return _stripped_non_blank(v)  # type: ignore[return-value]

    @field_validator("domain")
    @classmethod
    def _domain_shape(cls, v: str) -> str:
        return _new_domain(v)  # type: ignore[return-value]


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # min_length matches AgentRecord/AgentCreate: an empty name or owner is a
    # 422 here, at the request boundary. Without it the value reached the
    # store and failed only on read-back (a 500; before the atomic update, a
    # persisted row that made every read of the registry 500).
    # tests/test_registry_update_validation.py. Omitted (None) stays allowed.
    name: Name | None = None
    owner: Owner | None = None
    domain: Domain | None = None
    manifest_ref: ManifestRef | None = None
    status: AgentStatus | None = None
    # Compare-and-set (kill-path hardening): apply the patch only if the row's updated_at still equals this ISO 8601
    # timestamp (the one a previous read or write of the row returned); otherwise 412. Not a column: it is never
    # stored and never listed in the ledger's field list.
    if_updated_at: str | None = Field(default=None, max_length=64)

    @field_validator("if_updated_at")
    @classmethod
    def _parseable(cls, value: str | None) -> str | None:
        if value is not None:
            parse_updated_at(value)
        return value

    @field_validator("name", "owner", "domain")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        return _stripped_non_blank(v)

    @field_validator("domain")
    @classmethod
    def _domain_shape(cls, v: str | None) -> str | None:
        return _new_domain(v)


def parse_updated_at(value: str) -> datetime:
    """An ISO 8601 timestamp as an aware UTC datetime (``Z`` accepted, naive taken as UTC); ValueError otherwise."""
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class ShadowCandidate(BaseModel):
    """An unregistered-agent candidate found by the discovery scanner."""

    # hide_input_in_errors: a validation error must not quote an input that
    # may carry a credential.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    source: str  # "n8n" | "service-accounts" | "api-keys"
    identifier: str
    display_name: str
    reason: str
    evidence: dict[str, str] = Field(default_factory=dict)

    # v1.2 D3: a candidate echoes strings from the scanned input (an account
    # name, a key's owner, an n8n node name). Any of them can carry a pasted
    # credential, so every echoed string is redacted HERE, at the model, for
    # every scanner — not left to each scanner to remember.
    @field_validator("identifier", "display_name")
    @classmethod
    def _redact_str(cls, v: str) -> str:
        return redact_text(v)

    @field_validator("evidence")
    @classmethod
    def _redact_evidence(cls, v: dict[str, str]) -> dict[str, str]:
        return {redact_text(k): redact_text(val) for k, val in v.items()}


class SecretHit(BaseModel):
    """A credential-shaped string found by ``scan_secrets_text``.

    Built from the RAW value (``SecretHit(value=raw, ...)``) and keeping only
    its redaction: the validator below replaces ``value`` with ``redacted`` +
    ``fingerprint`` + ``length`` before the model exists (the raw value wins
    over any redaction passed alongside it). A model built WITHOUT ``value``
    (parsing a report back) is held to the redaction's shape: ``redacted``
    shows at most 11 characters around an ellipsis and ``fingerprint`` is 16
    hex — so no instance, however built, can carry a whole secret, and a
    validation error never quotes its input."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    pattern: str
    breadth: str = Field(description="low | moderate | broad | generic | very-broad")
    line: int = Field(ge=1)
    redacted: str
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{16}$")
    length: int = Field(ge=1)

    @model_validator(mode="before")
    @classmethod
    def _redact_raw(cls, data):
        if isinstance(data, dict) and "value" in data:
            data = dict(data)
            raw = str(data.pop("value"))
            data.update(redacted=redact(raw), fingerprint=fingerprint(raw),
                        length=len(raw))
        return data

    @field_validator("redacted")
    @classmethod
    def _is_a_redaction(cls, v: str) -> str:
        if v.count("…") != 1 or len(v) - 1 > 11:
            raise ValueError("redacted must be a redaction (at most 11 characters "
                             "around one ellipsis), never a value")
        return v


class DiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanned_workflows: int
    scanned_accounts: int
    registered_agents: int
    candidates: list[ShadowCandidate]
    # v1.2 D3 — defaults keep every pre-D3 report (and test) valid.
    scanned_api_keys: int = 0
    scanned_secret_hits: int = 0
    secret_hits: list[SecretHit] = Field(default_factory=list)
    method: str = (
        "deterministic heuristic v0.1 — AI-node detection in n8n exports + "
        "service-account name patterns; v1.2 D3 adds an API-key inventory "
        "owner check and labeled credential-pattern matching (redacted); "
        "no LLM involved"
    )
