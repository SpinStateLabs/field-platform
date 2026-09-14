"""Loading a manifest's ``enforcement.rate_limits`` into a governor.

One implementation for both manifest-driven provisioning paths: ``governor
set-cap --from-manifest`` and lifecycle-manager's ``provision`` (which also
imports ``SpendCapConfig`` from this package) call it, so the two cannot
disagree about a cent or a throttle. Validate with ``rate_limits_from_manifest`` BEFORE the first PUT
(a refusal configures nothing), load with ``load_rate_limits`` AFTER the cap
PUT (``PUT /rate-limits`` 404s for an uncapped agent)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from field_core.manifest import FieldManifest
from spend_governor.core import RateLimitSet

NO_SPEND_CAP_REFUSAL = (
    "manifest declares enforcement.rate_limits but no enforcement.spend_cap — "
    "refusing: rate limits are enforced only on a governed cap"
)


class RateLimitsRefusedError(ValueError):
    """The manifest's ``enforcement.rate_limits`` cannot be loaded as declared
    (unknown period, duplicate entry, or no spend_cap to govern them)."""


def rate_limits_from_manifest(manifest: FieldManifest, agent_id: str) -> RateLimitSet:
    """The agent's whole rate-limit set, validated. Raises
    ``RateLimitsRefusedError`` naming every reason; call it before anything is
    PUT. An empty set (no ``rate_limits`` declared) is valid."""
    if manifest.enforcement.rate_limits and manifest.enforcement.spend_cap is None:
        raise RateLimitsRefusedError(NO_SPEND_CAP_REFUSAL)
    try:
        return RateLimitSet.from_manifest(manifest, agent_id)
    except ValidationError as exc:
        reasons = "; ".join(err.get("msg", str(err)) for err in exc.errors())
        raise RateLimitsRefusedError(
            f"enforcement.rate_limits refused: {reasons}") from exc


@dataclass
class RateLimitsLoad:
    """What ``load_rate_limits`` did. ``outcome``: ``loaded`` (the set was PUT,
    possibly empty to clear a stale one), ``unchanged`` (nothing declared and
    the governor holds nothing — or has no ``/rate-limits`` route: a pre-D1
    governor), ``failed`` (the PUT was refused; ``response`` is the reply)."""

    outcome: Literal["loaded", "unchanged", "failed"]
    status_code: int | None
    enforced: list[dict] = field(default_factory=list)
    declared_unenforced: list[dict] = field(default_factory=list)
    response: Any = None

    @property
    def detail(self) -> str:
        if self.outcome == "loaded":
            return (f"{len(self.enforced)} enforced, "
                    f"{len(self.declared_unenforced)} declared-unenforced")
        if self.outcome == "unchanged":
            return "no rate_limits declared and none held"
        text = getattr(self.response, "text", None)
        return f"rate limits NOT loaded ({self.status_code}): {text}"[:500]


def load_rate_limits(
    get: Callable[[str], Any],
    put: Callable[..., Any],
    limits: RateLimitSet,
) -> RateLimitsLoad:
    """Replace the agent's set at ``/rate-limits/{agent}``.

    ``get(path)`` and ``put(path, json=body)`` return httpx-like responses
    (``status_code``, ``json()``, ``text``). A declared set is always PUT, so
    a pre-D1 governor (no route) or an uncapped agent is ``failed``. With
    nothing declared the empty set is PUT only when the governor already
    holds a non-empty set — clearing a stale set from an earlier load without
    failing against a pre-D1 governor."""
    path = f"/rate-limits/{limits.agent_id}"
    body = limits.model_dump()
    if not body["rate_limits"]:
        current = get(path)
        if current.status_code != 200 or not current.json().get("rate_limits"):
            return RateLimitsLoad("unchanged", current.status_code, response=current)
    resp = put(path, json=body)
    if resp.status_code != 200:
        return RateLimitsLoad("failed", resp.status_code, response=resp)
    rows = resp.json().get("rate_limits", [])
    return RateLimitsLoad(
        "loaded", resp.status_code,
        enforced=[r for r in rows if r.get("status") == "enforced"],
        declared_unenforced=[r for r in rows if r.get("status") == "declared_unenforced"],
        response=resp,
    )
