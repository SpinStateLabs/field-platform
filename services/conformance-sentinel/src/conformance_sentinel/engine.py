"""The conformance decision engine.

Deterministic check sequence; the first failing clause decides. Every
BLOCK / ESCALATE cites a clause id from field-core's CLAUSES registry.

Fail-closed posture throughout: unknown agent, missing manifest, missing
token, unreachable ledger — all refuse the action rather than assume.
"""

from __future__ import annotations

from field_core.authn import auth_headers

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from field_core.clients import (
    AgentNotRegisteredError,
    LedgerClient,
    RegistryUnreachableError,
    RegistryClient,
)
from field_core.conformance import ConformanceVerdict, Decision
from field_core.manifest import FieldManifest
from field_core.validation import load_manifest, validate_manifest_data

from conformance_sentinel.mode import SentinelMode


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    action: str = Field(min_length=1, description="Proposed action, e.g. 'draft invoices'")
    token_id: str | None = Field(
        default=None, description="Delegation token presented by the agent"
    )
    irreversible: bool = Field(
        default=False, description="Caller marks one-way actions (send, delete, pay)"
    )
    context: dict[str, Any] = Field(default_factory=dict)


class SpendStatusClient:
    """Thin client for spend-governor /status. Injectable like the others."""

    def __init__(self, client=None, base_url: str | None = None):
        import os

        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_GOVERNOR_URL", "http://127.0.0.1:8006"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0, headers=auth_headers())

    def status(self, agent_id: str) -> dict[str, Any] | None:
        """None means 'no cap configured' (404) — treated as ungoverned-spend,
        which is OK unless the manifest declares a spend_cap (then ESCALATE)."""
        resp = self._client.get(f"{self._base}/status/{agent_id}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ConnectionError(f"governor returned {resp.status_code}")
        return resp.json()


class DelegationIntrospectClient:
    def __init__(self, client=None, base_url: str | None = None):
        import os

        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_DELEGATION_URL", "http://127.0.0.1:8003"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0, headers=auth_headers())

    def introspect(self, token_id: str) -> dict[str, Any]:
        resp = self._client.post(
            f"{self._base}/introspect", json={"token_id": token_id}
        )
        if resp.status_code != 200:
            raise ConnectionError(f"delegation returned {resp.status_code}")
        return resp.json()


class ManifestResolver:
    """Loads + validates the manifest a registry record points at, with an
    mtime cache. manifest_ref may be absolute or relative to manifest_dir."""

    def __init__(self, manifest_dir: str | Path | None = None):
        import os

        self.manifest_dir = Path(
            manifest_dir or os.environ.get("FIELD_MANIFEST_DIR", ".")
        )
        self._cache: dict[str, tuple[float, FieldManifest]] = {}

    def resolve(self, manifest_ref: str | None) -> FieldManifest | None:
        """None = missing/invalid (caller blocks with I.manifest)."""
        if not manifest_ref:
            return None
        path = Path(manifest_ref)
        if not path.is_absolute():
            path = self.manifest_dir / path
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        cached = self._cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            data = load_manifest(path)
        except Exception:
            return None
        result = validate_manifest_data(data)
        if not result.ok:
            return None
        manifest = FieldManifest.from_dict(data)
        self._cache[str(path)] = (mtime, manifest)
        return manifest


class SentinelEngine:
    def __init__(
        self,
        registry: RegistryClient,
        delegation: DelegationIntrospectClient,
        governor: SpendStatusClient,
        ledger: LedgerClient,
        ledger_health,           # callable () -> bool
        manifests: ManifestResolver,
        mode: SentinelMode = SentinelMode.ENFORCE,
    ):
        self.registry = registry
        self.delegation = delegation
        self.governor = governor
        self.ledger = ledger
        self.ledger_health = ledger_health
        self.manifests = manifests
        self.mode = mode

    def _verdict(
        self,
        req: CheckRequest,
        decision: Decision,
        clause_id: str | None,
        reasons: list[str],
    ) -> ConformanceVerdict:
        # Log-only mode: a would-block / would-escalate is SHADOW-recorded and
        # the caller is NOT blocked (returns ALLOW). ALLOW verdicts behave the
        # same in both modes. This is the safe-by-default deployed posture.
        if self.mode is SentinelMode.LOG_ONLY and decision in (
            Decision.BLOCK, Decision.ESCALATE
        ):
            shadow_type = f"conformance.shadow_{decision.value.lower()}"
            try:
                self.ledger.append(
                    shadow_type,
                    payload={
                        "action": req.action,
                        "would_block": clause_id,
                        "reasons": reasons,
                        "mode": "log_only",
                    },
                    agent_id=req.agent_id,
                )
            except Exception:
                pass
            return ConformanceVerdict(
                decision=Decision.ALLOW,
                agent_id=req.agent_id,
                action=req.action,
                clause_id=None,
                reasons=[
                    f"log-only: would {decision.value} on {clause_id} — not enforced"
                ],
                checked_at=datetime.now(timezone.utc),
                context={
                    "token_id": req.token_id,
                    "irreversible": req.irreversible,
                    "shadowed": True,
                    "would_be": {"decision": decision.value, "clause_id": clause_id},
                },
            )

        verdict = ConformanceVerdict(
            decision=decision,
            agent_id=req.agent_id,
            action=req.action,
            clause_id=clause_id,
            reasons=reasons,
            checked_at=datetime.now(timezone.utc),
            context={"token_id": req.token_id, "irreversible": req.irreversible},
        )
        # Blocks and escalations are ledger events (spec). Allows too — the
        # manifests say "every action" is logged. Best-effort here; the
        # fail-closed guarantee is the reachability check *before* ALLOW.
        event_type = f"conformance.{decision.value.lower()}"
        try:
            self.ledger.append(
                event_type,
                payload={
                    "action": req.action,
                    "clause_id": clause_id,
                    "reasons": reasons,
                },
                agent_id=req.agent_id,
            )
        except Exception:
            pass
        return verdict

    def check(self, req: CheckRequest) -> ConformanceVerdict:
        # 1. Ledger reachability — an action that cannot be logged may not run.
        #    Routed through _verdict so the operating mode applies uniformly
        #    (in log-only the shadow record itself is lost when the ledger is
        #    down, and the caller is not blocked — documented in LIMITS).
        if not self.ledger_health():
            return self._verdict(
                req, Decision.BLOCK, "L.unreachable",
                ["sealed-ledger is unreachable; refusing unloggable action"],
            )

        # 2. Registry: the agent must exist and be active.
        try:
            record = self.registry.get_agent(req.agent_id)
        except AgentNotRegisteredError:
            return self._verdict(
                req, Decision.BLOCK, "R.unregistered",
                [f"agent '{req.agent_id}' is not in the registry"],
            )
        except RegistryUnreachableError as exc:
            return self._verdict(
                req, Decision.BLOCK, "R.unregistered",
                [f"registry unreachable — cannot establish identity: {exc}"],
            )
        status = record.get("status")
        if status == "killed":
            return self._verdict(
                req, Decision.BLOCK, "E.kill_switch",
                ["agent is killed; kill-switch propagation"],
            )
        if status != "active":
            return self._verdict(
                req, Decision.BLOCK, "R.unregistered",
                [f"agent status is '{status}', not active"],
            )

        # 3. Manifest: no declared envelope, no action.
        manifest = self.manifests.resolve(record.get("manifest_ref"))
        if manifest is None:
            return self._verdict(
                req, Decision.BLOCK, "I.manifest",
                ["FIELD manifest missing or invalid for this agent"],
            )

        # 4. Delegation token: presented, active, bound to this agent.
        if not req.token_id:
            return self._verdict(
                req, Decision.BLOCK, "D.token", ["no delegation token presented"]
            )
        try:
            intro = self.delegation.introspect(req.token_id)
        except Exception as exc:
            return self._verdict(
                req, Decision.BLOCK, "D.token",
                [f"delegation-authority unreachable: {exc}"],
            )
        if not intro.get("active"):
            token_status = intro.get("status", "unknown")
            clause = {"expired": "D.expired", "revoked": "D.revoked"}.get(
                token_status, "D.token"
            )
            return self._verdict(
                req, Decision.BLOCK, clause,
                [f"token inactive: {intro.get('reason') or token_status}"],
            )
        if intro.get("agent_id") != req.agent_id:
            return self._verdict(
                req, Decision.BLOCK, "D.token",
                ["token belongs to a different agent"],
            )

        # 5. Scope: action must be inside BOTH the token and the manifest.
        token_scope = intro.get("scope") or []
        if req.action not in token_scope:
            return self._verdict(
                req, Decision.BLOCK, "D.scope",
                [f"'{req.action}' not in token scope {token_scope}"],
            )
        manifest_scope = manifest.delegation.scope
        if req.action not in manifest_scope:
            return self._verdict(
                req, Decision.BLOCK, "D.scope",
                [f"'{req.action}' not in manifest delegation.scope {manifest_scope}"],
            )

        # 6. Irreversible action policy.
        if req.irreversible:
            policy = manifest.enforcement.irreversible_action_policy
            if policy == "forbid":
                return self._verdict(
                    req, Decision.BLOCK, "E.irreversible",
                    ["manifest forbids irreversible actions"],
                )
            if policy == "require_human_approval":
                return self._verdict(
                    req, Decision.ESCALATE, "E.irreversible",
                    ["irreversible action requires human approval"],
                )
            # allow_with_ledger: proceeds — the action is being logged.

        # 7. Escalation triggers (deterministic substring match, both ways).
        for trigger in manifest.enforcement.escalation_triggers or []:
            t, a = trigger.lower(), req.action.lower()
            if t in a or a in t:
                return self._verdict(
                    req, Decision.ESCALATE, "E.escalation_trigger",
                    [f"matched declared trigger: '{trigger}'"],
                )

        # 8. Spend state from the governor.
        try:
            spend = self.governor.status(req.agent_id)
        except Exception as exc:
            return self._verdict(
                req, Decision.BLOCK, "E.spend_cap",
                [f"spend-governor unreachable — cannot verify remaining budget: {exc}"],
            )
        if spend is None:
            if manifest.enforcement.spend_cap is not None:
                return self._verdict(
                    req, Decision.ESCALATE, "E.spend_cap",
                    ["manifest declares a spend_cap but the governor has no cap "
                     "configured — metering gap needs a human"],
                )
        else:
            if spend.get("state") == "BLOCK":
                return self._verdict(
                    req, Decision.BLOCK, "E.spend_cap", [spend.get("detail", "cap reached")]
                )
            if spend.get("state") == "ESCALATE":
                return self._verdict(
                    req, Decision.ESCALATE, "E.spend_threshold",
                    [spend.get("detail", "threshold crossed")],
                )

        return self._verdict(req, Decision.ALLOW, None, ["all clauses satisfied"])
