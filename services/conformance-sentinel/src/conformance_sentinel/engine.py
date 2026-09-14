"""The conformance decision engine.

Deterministic check sequence; the first failing clause decides. Every
BLOCK / ESCALATE cites a clause id from field-core's CLAUSES registry.

Fail-closed posture throughout: unknown agent, missing manifest, missing
token, unreachable ledger — all refuse the action rather than assume.
"""

from __future__ import annotations

from field_core.authn import auth_headers

from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from field_core.clients import (
    AgentNotRegisteredError,
    LedgerClient,
    # B0: the one manifest resolver now lives in field-core and is re-exported
    # here — api.py, both sentinel conftests and field-agent's conftest import
    # ManifestResolver from this module, and SentinelEngine keeps calling the
    # INSTANCE (self.manifests.resolve), which test_self_manifest.py spies on.
    ManifestResolver,
    RegistryUnreachableError,
    RegistryClient,
)
from field_core.conformance import ConformanceVerdict, Decision

from conformance_sentinel.judge import injection_screen
from conformance_sentinel.mode import SentinelMode
from conformance_sentinel.routing import needs_semantic_judgment


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

    def status(self, agent_id: str, *, action: str | None = None) -> dict[str, Any] | None:
        """None means 'no cap configured' (404) — treated as ungoverned-spend,
        which is OK unless the manifest declares a spend_cap (then ESCALATE).
        ``action`` (keyword) asks the governor to include that action's rate
        windows (``?action=``); the judge gate calls without it."""
        if action is None:
            resp = self._client.get(f"{self._base}/status/{agent_id}")
        else:
            resp = self._client.get(f"{self._base}/status/{agent_id}",
                                    params={"action": action})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ConnectionError(f"governor returned {resp.status_code}")
        return resp.json()

    def record_action(self, agent_id: str, action: str, *, shadowed: bool) -> str:
        """Meter ONE allowed action (option A): ``POST /spend`` with
        ``actions=1, action, source=sentinel``. Returns ``"metered"``, or
        ``"no_cap"`` on the governor's 404; raises on anything else."""
        resp = self._client.post(f"{self._base}/spend", json={
            "agent_id": agent_id, "actions": 1, "action": action,
            "source": "sentinel", "shadowed": shadowed,
        })
        if resp.status_code == 404:
            return "no_cap"
        if resp.status_code != 201:
            raise ConnectionError(f"governor /spend returned {resp.status_code}")
        return "metered"

    def totals_since(self, agent_id: str, since: str) -> dict[str, Any] | None:
        """Spend since ``since`` (``GET /totals``); None when uncapped (404)."""
        resp = self._client.get(f"{self._base}/totals/{agent_id}",
                                params={"since": since})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ConnectionError(f"governor /totals returned {resp.status_code}")
        return resp.json()

    def report_usage(self, agent_id: str, model: str,
                     input_tokens: int, output_tokens: int) -> None:
        """Meter one semantic judgment against the sentinel's own cap.
        Raises on any non-201 — the engine escalates unmeterable judgments."""
        resp = self._client.post(f"{self._base}/usage", json={
            "agent_id": agent_id, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "note": "sentinel semantic judgment",
        })
        if resp.status_code != 201:
            raise ConnectionError(f"governor /usage returned {resp.status_code}")


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
        judge=None,              # None = judge OFF (S2-identical behavior)
        judge_floor: float = 0.8,
        judge_spend_agent_id: str = "conformance-sentinel",
    ):
        self.registry = registry
        self.delegation = delegation
        self.governor = governor
        self.ledger = ledger
        self.ledger_health = ledger_health
        self.manifests = manifests
        self.mode = mode
        self.judge = judge
        self.judge_floor = judge_floor
        self.judge_spend_agent_id = judge_spend_agent_id

    def _verdict(
        self,
        req: CheckRequest,
        decision: Decision,
        clause_id: str | None,
        reasons: list[str],
        extra_context: dict[str, Any] | None = None,
    ) -> ConformanceVerdict:
        # ``extra_context`` (e.g. E.rate_limit's retry_after_seconds) rides in
        # the verdict context AND the ledger payload, in both modes.
        extra = dict(extra_context or {})
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
                        **extra,
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
                    **extra,
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
            context={**extra, "token_id": req.token_id,
                     "irreversible": req.irreversible},
        )
        # Blocks and escalations are ledger events (spec). Allows too — the
        # manifests say "every action" is logged. BLOCK/ESCALATE records are
        # best-effort (a block that cannot be recorded is still a block). F2:
        # in ENFORCE mode an ALLOW whose record the ledger refused or failed
        # (a 503 under FIELD_LEDGER_REQUIRE_SIGNING with no key, or any error
        # after the step-1 gate) is NOT an allow — it becomes BLOCK
        # L.unreachable, and the caller never reaches metering. LOG-ONLY is
        # unchanged: the allow record is lost and the caller is not blocked
        # (README LIMITS).
        event_type = f"conformance.{decision.value.lower()}"
        try:
            self.ledger.append(
                event_type,
                payload={
                    **extra,
                    "action": req.action,
                    "clause_id": clause_id,
                    "reasons": reasons,
                },
                agent_id=req.agent_id,
            )
        except Exception as exc:
            if decision is Decision.ALLOW and self.mode is SentinelMode.ENFORCE:
                return ConformanceVerdict(
                    decision=Decision.BLOCK,
                    agent_id=req.agent_id,
                    action=req.action,
                    clause_id="L.unreachable",
                    reasons=["sealed-ledger refused or failed the allow record",
                             f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}"],
                    checked_at=datetime.now(timezone.utc),
                    context={"token_id": req.token_id, "irreversible": req.irreversible,
                             "allow_record_failed": True},
                )
        return verdict

    def _judge_scope(self, req: CheckRequest,
                     effective_scope: list[str]) -> ConformanceVerdict | None:
        """Semantic scope judgment (ADR 02 S3). Fail-to-escalate throughout:
        every guard failure and every uncertainty ESCALATEs D.semantic — never
        silent-allow, never silent-block. Returns None only when the judge
        affirms conformance at/above the floor (remaining checks still run)."""
        tripped = injection_screen(req.action)
        if tripped:
            return self._verdict(
                req, Decision.ESCALATE, "D.semantic",
                [f"injection screen tripped ({tripped}) — semantic judgment "
                 "refused; human review required"],
            )

        # Spend gate: judgments run on the Sentinel's OWN metered budget.
        try:
            spend = self.governor.status(self.judge_spend_agent_id)
        except Exception as exc:
            return self._verdict(
                req, Decision.ESCALATE, "D.semantic",
                [f"judge spend unverifiable (governor: {exc}) — "
                 "structural-only throttle"],
            )
        if spend is None:
            return self._verdict(
                req, Decision.ESCALATE, "D.semantic",
                [f"no spend cap configured for '{self.judge_spend_agent_id}' "
                 "— refusing unmetered semantic judgment"],
            )
        if spend.get("state") == "BLOCK":
            return self._verdict(
                req, Decision.ESCALATE, "D.semantic",
                ["sentinel judgment budget exhausted — structural-only "
                 "throttle"],
            )

        try:
            jv = self.judge.judge(req.action, effective_scope, req.agent_id)
        except Exception as exc:
            return self._verdict(
                req, Decision.ESCALATE, "D.semantic",
                [f"semantic judge failed ({exc}) — fail-to-escalate"],
            )

        # Strict metering: a judgment that cannot be metered escalates.
        try:
            self.governor.report_usage(
                self.judge_spend_agent_id, jv.model,
                jv.input_tokens, jv.output_tokens,
            )
        except Exception as exc:
            return self._verdict(
                req, Decision.ESCALATE, "D.semantic",
                [f"semantic judgment unmeterable ({exc}) — fail-to-escalate"],
            )

        # Model output is untrusted text: collapse whitespace + truncate
        # before it can reach reasons or the ledger.
        rationale = " ".join((jv.rationale or "").split())[:300]
        try:
            self.ledger.append(
                "sentinel.judge",
                payload={
                    "action": req.action, "conforming": jv.conforming,
                    "confidence": jv.confidence, "model": jv.model,
                    "input_tokens": jv.input_tokens,
                    "output_tokens": jv.output_tokens,
                },
                agent_id=req.agent_id,
            )
        except Exception:
            pass

        if jv.conforming is True and jv.confidence >= self.judge_floor:
            return None
        if jv.conforming is False and jv.confidence >= self.judge_floor:
            return self._verdict(
                req, Decision.BLOCK, "D.scope",
                [f"semantic judge ({jv.model}): "
                 f"{rationale or 'outside delegated scope'}"],
            )
        return self._verdict(
            req, Decision.ESCALATE, "D.semantic",
            [f"semantic judge uncertain (confidence {jv.confidence:.2f}, "
             f"floor {self.judge_floor:.2f}): {rationale}"],
        )

    def check(self, req: CheckRequest) -> ConformanceVerdict:
        """Decide, then (option A) meter EVERY ALLOW in EITHER mode — genuine,
        or a log-only shadow decided at any step, steps 1-4 included (before
        identity is established; Don's decision 2026-09-13) — as one action
        against the governor. Metering never changes the decision: it runs
        after the verdict is built and ledgered."""
        probe: dict[str, Any] = {}
        verdict = self._decide(req, probe)
        if verdict.decision is Decision.ALLOW:
            self._meter(req, verdict, probe)
        return verdict

    def _meter(self, req: CheckRequest, verdict: ConformanceVerdict,
               probe: dict[str, Any]) -> None:
        """Best-effort ``actions=1, action, source=sentinel`` post.

        Every ALLOW is posted, including a log-only shadow decided at steps
        1-4, where the caller never proved it is ``agent_id`` (no active
        registry record or no live token bound to it): that action counts
        against the named agent's windows (README LIMITS). Skipped
        (``reason: no_cap``) only when step 8 read no cap — the governor would
        404. A shadowed ALLOW decided before step 8 posts anyway; a 404 there
        is the same ``no_cap``. Any other reply is a metering gap: ledgered
        ``sentinel.metering_gap``, verdict unchanged."""
        shadowed = verdict.context.get("shadowed") is True
        if probe.get("spend_reached") and probe.get("spend_status") is None:
            verdict.context.update({"metered": False, "reason": "no_cap"})
            return
        try:
            outcome = self.governor.record_action(
                req.agent_id, req.action, shadowed=shadowed)
        except Exception as exc:
            verdict.context.update({"metered": False, "reason": "metering_gap"})
            try:
                self.ledger.append(
                    "sentinel.metering_gap",
                    payload={"action": req.action, "shadowed": shadowed,
                             "error": " ".join(str(exc).split())[:300]},
                    agent_id=req.agent_id,
                )
            except Exception:
                pass
            return
        if outcome == "no_cap":
            verdict.context.update({"metered": False, "reason": "no_cap"})
        else:
            verdict.context["metered"] = True

    def _token_ceiling(self, req: CheckRequest,
                       intro: dict[str, Any]) -> ConformanceVerdict | None:
        """D1e: a token that carries ``max_spend_usd`` bounds the agent's
        governor-metered spend since the token's ``issued_at`` (all recorded
        spend when the token names no ``issued_at``). At/over ⇒ BLOCK
        ``E.spend_cap``. Fail closed: an unreadable ceiling or an unverifiable
        total BLOCKs; a vanished cap ESCALATEs (metering gap)."""
        raw = intro.get("max_spend_usd")
        try:
            if isinstance(raw, bool):
                raise ValueError("boolean")
            ceiling = Decimal(str(raw))
            if not ceiling.is_finite() or ceiling < 0:
                raise ValueError("not a finite non-negative amount")
        except (InvalidOperation, ValueError) as exc:
            return self._verdict(
                req, Decision.BLOCK, "E.spend_cap",
                [f"token max_spend_usd {raw!r} is unreadable ({exc}) — refusing"],
            )
        # Floor to whole cents: a sub-cent ceiling rounds DOWN (stricter).
        ceiling_cents = int((ceiling * 100).to_integral_value(rounding=ROUND_FLOOR))
        since = intro.get("issued_at") or "1970-01-01T00:00:00+00:00"
        try:
            totals = self.governor.totals_since(req.agent_id, str(since))
        except Exception as exc:
            return self._verdict(
                req, Decision.BLOCK, "E.spend_cap",
                [f"spend-governor cannot total spend under this token: {exc}"],
            )
        if totals is None:
            return self._verdict(
                req, Decision.ESCALATE, "E.spend_cap",
                ["token carries max_spend_usd but the governor has no cap "
                 "configured — metering gap needs a human"],
            )
        # The ceiling is USD; the governor's cents are in the cap's currency.
        # No FX here: anything but a USD total cannot be compared — refuse.
        currency = totals.get("currency")
        if not isinstance(currency, str) or currency.strip().upper() != "USD":
            return self._verdict(
                req, Decision.BLOCK, "E.spend_cap",
                [f"token max_spend_usd is a USD ceiling but the governor meters "
                 f"this agent in {currency!r} — cannot compare, refusing"],
                extra_context={"token_max_spend_cents": ceiling_cents,
                               "cap_currency": currency},
            )
        spent = int(totals.get("spent_cents", 0))
        if spent >= ceiling_cents:
            return self._verdict(
                req, Decision.BLOCK, "E.spend_cap",
                [f"token spend ceiling reached: {spent} cents since {since} >= "
                 f"token max_spend_usd {ceiling_cents} cents"],
                extra_context={"token_max_spend_cents": ceiling_cents,
                               "token_spent_cents": spent},
            )
        return None

    def _decide(self, req: CheckRequest, probe: dict[str, Any]) -> ConformanceVerdict:
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
        #    S3: when exact membership fails, the paraphrase neighborhood may
        #    go to the semantic judge — judged against the EFFECTIVE scope
        #    (token∩manifest) so the narrower grant still wins. Judge off or
        #    predicate not fired: block exactly as before.
        token_scope = intro.get("scope") or []
        manifest_scope = manifest.delegation.scope
        if req.action not in token_scope or req.action not in manifest_scope:
            judged_conforming = False
            if self.judge is not None:
                effective = [s for s in manifest_scope if s in token_scope]
                if needs_semantic_judgment(req.action, effective):
                    verdict = self._judge_scope(req, effective)
                    if verdict is not None:
                        return verdict
                    judged_conforming = True  # remaining checks still run
            if not judged_conforming:
                if req.action not in token_scope:
                    return self._verdict(
                        req, Decision.BLOCK, "D.scope",
                        [f"'{req.action}' not in token scope {token_scope}"],
                    )
                return self._verdict(
                    req, Decision.BLOCK, "D.scope",
                    [f"'{req.action}' not in manifest delegation.scope "
                     f"{manifest_scope}"],
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

        # 8. Spend state from the governor, including THIS action's rate
        #    windows. Precedence: cap BLOCK > token ceiling (D1e) > THROTTLED
        #    (E.rate_limit) > ESCALATE.
        try:
            spend = self.governor.status(req.agent_id, action=req.action)
        except Exception as exc:
            return self._verdict(
                req, Decision.BLOCK, "E.spend_cap",
                [f"spend-governor unreachable — cannot verify remaining budget: {exc}"],
            )
        probe["spend_reached"] = True
        probe["spend_status"] = spend
        if spend is None:
            if manifest.enforcement.spend_cap is not None:
                return self._verdict(
                    req, Decision.ESCALATE, "E.spend_cap",
                    ["manifest declares a spend_cap but the governor has no cap "
                     "configured — metering gap needs a human"],
                )
            if intro.get("max_spend_usd") is not None:
                return self._verdict(
                    req, Decision.ESCALATE, "E.spend_cap",
                    ["token carries max_spend_usd but the governor has no cap "
                     "configured — metering gap needs a human"],
                )
        else:
            if spend.get("state") == "BLOCK":
                return self._verdict(
                    req, Decision.BLOCK, "E.spend_cap", [spend.get("detail", "cap reached")]
                )
            if intro.get("max_spend_usd") is not None:
                ceiling_verdict = self._token_ceiling(req, intro)
                if ceiling_verdict is not None:
                    return ceiling_verdict
            if spend.get("state") == "THROTTLED":
                return self._verdict(
                    req, Decision.BLOCK, "E.rate_limit",
                    [spend.get("detail", "rate limit exhausted")],
                    extra_context={
                        "retry_after_seconds": spend.get("retry_after_seconds")},
                )
            if spend.get("state") == "ESCALATE":
                return self._verdict(
                    req, Decision.ESCALATE, "E.spend_threshold",
                    [spend.get("detail", "threshold crossed")],
                )

        return self._verdict(req, Decision.ALLOW, None, ["all clauses satisfied"])
