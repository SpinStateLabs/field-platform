"""Token-usage models, per-agent usage policy, and rogue-usage detection.

Agents report (model, input_tokens, output_tokens); the governor computes
dollar cost from the price book and feeds it into the same spend cap that
already escalates-before-cap and blocks. On top of the cap, three
deterministic rogue signals make abuse visible even below the cap:

  rogue_model  — the agent used a model outside its declared allow-list
  rogue_burst  — token consumption spiked past the agent's rate ceiling
  unpriced     — the model has no price; cost cannot be governed, which is
                 itself suspicious

Every finding is a ledger event and a human-queue escalation. All arithmetic
is integer (price units = 1e-7 USD); no floats near a limit.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UsagePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    allowed_models: list[str] = Field(
        default_factory=list,
        description="Canonical model ids the agent may use; empty = any priced "
        "model is allowed (rogue_model never fires).",
    )
    token_rate_limit: int | None = Field(
        default=None, gt=0,
        description="Max input+output tokens per rate window before rogue_burst.",
    )
    rate_window_seconds: int = Field(default=3600, gt=0)


class RogueKind(str, Enum):
    ROGUE_MODEL = "rogue_model"
    ROGUE_BURST = "rogue_burst"
    UNPRICED = "unpriced"


class RogueFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RogueKind
    detail: str


class UsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    agent_id: str
    ts: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0, default=0)
    cost_units: int | None = Field(
        default=None, description="Integer 1e-7 USD; None if the model is unpriced."
    )
    priced: bool = True
    note: str | None = None


class ModelBreakdown(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost_units: int | None
    priced: bool
    allowed: bool


class UsageStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    window_seconds: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_units: int          # sum over priced models only
    total_cost_display: str
    token_rate_limit: int | None
    allowed_models: list[str]
    by_model: list[ModelBreakdown]
    open_rogue_flags: int


def evaluate_rogue(
    policy: UsagePolicy | None,
    canonical_model: str,
    priced: bool,
    window_tokens_after: int,
) -> list[RogueFinding]:
    """Pure rogue arithmetic for one usage event. window_tokens_after is the
    agent's input+output token total in the current window INCLUDING this
    event."""
    findings: list[RogueFinding] = []

    if not priced:
        findings.append(RogueFinding(
            kind=RogueKind.UNPRICED,
            detail=f"model '{canonical_model}' has no price in the price book — "
            "cost cannot be governed; price it or block the model",
        ))

    if policy is not None:
        if policy.allowed_models and canonical_model not in policy.allowed_models:
            findings.append(RogueFinding(
                kind=RogueKind.ROGUE_MODEL,
                detail=f"model '{canonical_model}' is not in this agent's "
                f"allow-list {policy.allowed_models}",
            ))
        if (policy.token_rate_limit is not None
                and window_tokens_after >= policy.token_rate_limit):
            findings.append(RogueFinding(
                kind=RogueKind.ROGUE_BURST,
                detail=f"token burst: {window_tokens_after} tokens in the last "
                f"{policy.rate_window_seconds}s >= limit {policy.token_rate_limit}",
            ))

    return findings
