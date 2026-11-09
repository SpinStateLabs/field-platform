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
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "ROSTER_ENV",
    "DoaRosterError",
    "GrantorRow",
    "DoaRoster",
    "roster_path",
    "load_roster",
]

#: The one environment variable that arms the mint gate. `delegation doa
#: check` sets it for the duration of its in-process dry run, then restores it.
ROSTER_ENV = "FIELD_DOA_ROSTER"
#: The longest ``max_ttl_days`` a roster row may carry: ten years. A hand-edited row above it is a roster
#: error at load (the mint answers 503 naming it), not an ``OverflowError`` from ``timedelta(days=N)``
#: (N above 999999999) at the lifetime check.
MAX_TTL_DAYS = 3650


class DoaRosterError(Exception):
    """The roster was named but could not be loaded as a valid roster."""


class GrantorRow(BaseModel):
    """One human grantor's authority envelope."""

    model_config = ConfigDict(extra="forbid")

    grantor: str = Field(min_length=1, description="Exact `granted_by` string")
    allowed_scope: list[str] = Field(
        min_length=1, description="Scopes this grantor may delegate (exact strings)"
    )
    max_ttl_days: int = Field(
        gt=0, le=MAX_TTL_DAYS, description="Longest token this grantor may mint, in days (at most 3650)")
    #: Recorded in the delegation.mint ledger payload and stamped on the token
    #: at mint (v1.2 D1e); never enforced here — conformance-sentinel enforces
    #: it as E.spend_cap on the agent's governor-metered spend since issue.
    max_spend_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    active: bool = Field(description="False retires the grantor without deleting the row")

    @field_validator("max_ttl_days", "max_spend_usd", mode="before")
    @classmethod
    def _numbers_are_not_booleans(cls, value: object) -> object:
        # YAML 1.1 reads yes/on/true as a boolean and pydantic's lax int/float turns True into 1 / 1.0: a typo
        # for a number must be a roster error, not a one-day or one-dollar limit
        if isinstance(value, bool):
            raise ValueError("must be a number, not a boolean")
        return value

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

    @model_validator(mode="after")
    def _grantors_are_unique(self) -> "DoaRoster":
        # find() returns the first exact match, so a second row for the same
        # grantor would be silently shadowed: refuse it (exact strings, no case folding).
        seen: set[str] = set()
        for row in self.grantors:
            if row.grantor in seen:
                raise ValueError(f"duplicate grantor {row.grantor!r} in the DOA roster")
            seen.add(row.grantor)
        return self

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
    value = os.environ.get(ROSTER_ENV, "").strip()
    return value or None


class _DuplicateKey(Exception):
    """Carries the key and its line only: a yaml error would print the source line, and with it the value."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """``yaml.safe_load`` keeps the LAST of two equal keys without a word, so a hand edit that repeats ``active:``
    would reactivate a retired grantor unseen. This loader refuses a repeated key and names the key and its line,
    never the value."""

    def construct_mapping(self, node, deep=False):
        seen: set[object] = set()
        for key_node, _ in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                key = self.construct_object(key_node, deep=True)
                try:
                    dup = key in seen
                    seen.add(key)
                except TypeError:
                    continue
                if dup:
                    raise _DuplicateKey(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        return super().construct_mapping(node, deep=deep)


def load_roster(path: str | Path) -> DoaRoster:
    """Load + validate the roster. Raises DoaRosterError on any failure."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DoaRosterError(f"roster '{path}' is unreadable: {exc}") from exc
    try:
        data = yaml.load(raw, Loader=_UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass
    except _DuplicateKey as exc:
        raise DoaRosterError(f"roster '{path}' is not a valid DOA roster: {exc}") from None
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
