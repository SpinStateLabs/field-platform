"""DOA (delegation-of-authority) roster — who may grant what, for how long.

The roster is a YAML file named by ``FIELD_DOA_ROSTER``. It is the operator's
declaration of which human grantors may delegate authority, the scopes each
may delegate, and the longest token each may mint.

What the roster IS: an exact-string membership list, maintained by a human,
checked on every mint while the variable is set.

What the roster is NOT: authentication. ``granted_by`` is still an unverified
request field — the roster proves that the *string* is on a list, never that
the caller is the person named. SPEC's "no grantor authentication" non-goal
stands.

Fail-closed rule (ENFORCED): if ``FIELD_DOA_ROSTER`` is set and the file is
missing, unreadable or not a valid roster, the mint is refused with 503
*before* any ledger write. A roster that cannot be read must never degrade
into an unchecked mint.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DoaRosterError",
    "GrantorRow",
    "DoaRoster",
    "roster_path",
    "load_roster",
]


class DoaRosterError(Exception):
    """The roster was named but could not be loaded as a valid roster."""


class GrantorRow(BaseModel):
    """One human grantor's authority envelope."""

    model_config = ConfigDict(extra="forbid")

    grantor: str = Field(min_length=1, description="Exact `granted_by` string")
    allowed_scope: list[str] = Field(
        min_length=1, description="Scopes this grantor may delegate (exact strings)"
    )
    max_ttl_days: int = Field(gt=0, description="Longest token this grantor may mint")
    #: Recorded in the delegation.mint ledger payload; NEVER enforced here.
    #: Spend caps belong to spend-governor.
    max_spend_usd: float | None = Field(default=None, ge=0)
    active: bool = Field(description="False retires the grantor without deleting the row")

    def may_delegate(self, scope: list[str]) -> list[str]:
        """Scopes in ``scope`` this grantor may NOT delegate (empty = allowed)."""
        allowed = set(self.allowed_scope)
        return [s for s in scope if s not in allowed]

    def ledger_row(self) -> dict[str, object]:
        """The `doa_row` recorded on `delegation.mint`."""
        return {
            "grantor": self.grantor,
            "max_ttl_days": self.max_ttl_days,
            "max_spend_usd": self.max_spend_usd,
        }


class DoaRoster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grantors: list[GrantorRow] = Field(default_factory=list)

    def find(self, grantor: str) -> GrantorRow | None:
        """Exact-string lookup. No normalization: a near-miss is a miss."""
        for row in self.grantors:
            if row.grantor == grantor:
                return row
        return None


def roster_path() -> str | None:
    """The configured roster path, or None when the feature is off.

    Read per call, never cached: an operator who exports the variable later
    gets the check without a restart, and tests can toggle it.
    """
    value = os.environ.get("FIELD_DOA_ROSTER", "").strip()
    return value or None


def load_roster(path: str | Path) -> DoaRoster:
    """Load + validate the roster. Raises DoaRosterError on any failure."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DoaRosterError(f"roster '{path}' is unreadable: {exc}") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DoaRosterError(f"roster '{path}' is not valid YAML: {exc}") from exc
    if data is None:
        raise DoaRosterError(f"roster '{path}' is empty")
    if not isinstance(data, dict):
        raise DoaRosterError(f"roster '{path}' must be a mapping with a 'grantors' list")
    try:
        return DoaRoster.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise DoaRosterError(f"roster '{path}' is not a valid DOA roster: {exc}") from exc
