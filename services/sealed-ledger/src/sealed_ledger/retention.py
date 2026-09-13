"""Estate retention check (C2) — ``GET /retention/check`` and ``ledger retention check``.

Retention is ESTATE-level: there is one shared chain per estate, so no agent's
events can be purged on their own. ``FIELD_LEDGER_RETENTION_DAYS`` is what the
estate keeps; each manifest's ``ledger.retention_days`` is a FLOOR the estate
must meet. The check lists every registered agent's manifest (the B0 shared
resolver, the same one the sentinel uses) and flags any that declares more
retention than the estate keeps.

It reports, it never enforces: nothing is archived or refused because of it.
A check that could not run is ``unavailable``, never ``ok``.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from field_core.clients import resolve_manifest_detail

RETENTION_ENV = "FIELD_LEDGER_RETENTION_DAYS"

Status = Literal["ok", "violation", "no_estate_policy", "unresolvable", "unavailable"]


class RetentionCheck(BaseModel):
    ok: bool
    status: Status
    estate_retention_days: int | None
    policy_source: str | None = Field(description="FIELD_LEDGER_RETENTION_DAYS, or None when unset")
    detail: str | None = None
    manifests_checked: int = 0
    agents_without_manifest: int = Field(0, description="agents with NO manifest_ref: skipped, counted")
    max_manifest_retention_days: int | None = None
    offending: list[dict[str, Any]] = Field(default_factory=list)
    unresolvable: list[dict[str, Any]] = Field(default_factory=list)
    # The ledger's own state. All None (and status ``unavailable``) when it
    # could not be read: never a made-up "no hold, 1 segment".
    earliest_live_index: int | None = 0
    earliest_live_ts: str | None = None
    segments: int | None = 1
    archived_segments: int | None = 0
    pending_moves: list[dict[str, Any]] | None = Field(default_factory=list)
    legal_hold: dict[str, Any] | None = None


def estate_retention_days() -> tuple[int | None, str | None]:
    """(days, problem). Unset or blank => (None, None); not an integer >= 1 =>
    (None, why) — a garbage policy is no policy, and says so."""
    raw = os.environ.get(RETENTION_ENV)
    if raw is None or not raw.strip():
        return None, None
    try:
        days = int(raw.strip())
    except ValueError:
        return None, f"{RETENTION_ENV}={raw.strip()[:40]!r} is not an integer"
    if days < 1:
        return None, f"{RETENTION_ENV}={days} must be >= 1"
    return days, None


def retention_check(store, registry) -> RetentionCheck:
    """``registry``: anything with ``list_agents()`` (a ``RegistryClient``), or
    None when disabled. ``store``: the ``LedgerStore`` whose state is reported."""
    estate, problem = estate_retention_days()
    fields: dict[str, Any] = {
        "estate_retention_days": estate,
        "policy_source": RETENTION_ENV if estate is not None else None,
    }
    details: list[str] = [problem] if problem else []
    ledger_state_read = True
    try:
        fields.update(store.retention_state())
    except Exception as exc:  # noqa: BLE001 - the check reports, it never 500s
        ledger_state_read = False
        details.append(f"ledger state unreadable: {type(exc).__name__}: {str(exc)[:200]}")
        fields.update(earliest_live_index=None, earliest_live_ts=None, segments=None,
                      archived_segments=None, pending_moves=None, legal_hold=None)

    agents: list[dict[str, Any]] | None = None
    if registry is None:
        details.append("registry not configured for this ledger app")
    else:
        try:
            listed = registry.list_agents()
            if not isinstance(listed, list):
                raise TypeError(f"list_agents returned {type(listed).__name__}")
            agents = listed
        except Exception as exc:  # noqa: BLE001 - unreachable registry => unavailable
            details.append(f"registry unavailable: {type(exc).__name__}: {str(exc)[:200]}")

    offending: list[dict[str, Any]] = []
    unresolvable: list[dict[str, Any]] = []
    checked = without = 0
    max_days: int | None = None
    for agent in sorted(agents or [], key=lambda a: str(a.get("agent_id"))):
        ref = agent.get("manifest_ref")
        if not ref:
            without += 1
            continue
        manifest, reason = resolve_manifest_detail(ref)
        if reason != "ok" or manifest is None:
            unresolvable.append({"agent_id": agent.get("agent_id"), "manifest_ref": ref,
                                 "reason": reason})
            continue
        days = manifest.ledger.retention_days
        checked += 1
        max_days = days if max_days is None else max(max_days, days)
        if estate is not None and days > estate:
            offending.append({"agent_id": agent.get("agent_id"), "retention_days": days})

    if agents is None or not ledger_state_read:
        status: Status = "unavailable"
    elif estate is None:
        status = "no_estate_policy"
        if not problem:
            details.append(f"no estate policy ({RETENTION_ENV} unset)")
    elif unresolvable:
        status = "unresolvable"
    elif offending:
        status = "violation"
    else:
        status = "ok"
    return RetentionCheck(
        ok=status == "ok", status=status, detail="; ".join(details) or None,
        manifests_checked=checked, agents_without_manifest=without,
        max_manifest_retention_days=max_days, offending=offending, unresolvable=unresolvable,
        **fields,
    )
