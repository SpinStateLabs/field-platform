# SPEC — conformance-sentinel

**Purpose:** The policy-enforcement point. `/check` takes (agent id,
proposed action, token, context) and answers ALLOW / BLOCK / ESCALATE with
the failed clause id, evaluating: ledger reachability, registry status
(kill propagation), manifest validity, token validity via
delegation-authority introspection, scope allowlists (token ∩ manifest),
irreversible-action policy, declared escalation triggers, and spend state
via spend-governor. Ships the `@governed` decorator any Python agent wraps
around a tool call.

**Exec owner:** CISO.

**FIELD letter:** E — Enforcement (touches all five).

**v0.1 scope**
- Deterministic decision sequence, first failing clause decides; clause ids
  from field-core `CLAUSES` (stable registry, `/clauses` endpoint).
- Fail-closed on every dependency outage (ledger, registry, delegation,
  governor) — each mapped to a specific clause.
- Manifest resolution via registry `manifest_ref` with mtime-cached
  `field validate` (invalid ⇒ `I.manifest` block).
- All verdicts logged to the sealed ledger (`conformance.*`).
- `@governed` decorator + imperative `Governor.check` (raise on non-ALLOW).
- CLI: `sentinel check | clauses | serve` (exit codes 0/2/1).
- 15 tests incl. adversarial: manifest unsealed on disk, token narrower
  than manifest, ledger down, out-of-scope block.
- D1: step 8 reads `/status/{agent}?action=` and maps THROTTLED to BLOCK
  `E.rate_limit` with `retry_after_seconds` threaded through `_verdict` into
  the enforce context, the shadow context and both ledger payloads;
  `ActionBlocked.retry_after`. EVERY ALLOW in EITHER mode is metered to the
  governor as `source=sentinel` (options A + B adopted), including a
  log-only shadow decided at steps 1–4 before identity is established (Don's
  decision 2026-09-13; README LIMITS states the window-pollution cost) —
  `metered: false, reason: no_cap` for an uncapped agent, ledgered
  `sentinel.metering_gap` on any non-201 reply, never flipping the verdict. D1e: a token's `max_spend_usd` (stamped at mint from the matched DOA roster row)
  (when introspection carries it) bounds USD spend since `issued_at` as
  `E.spend_cap`; a cap in another currency is refused.

**Explicit non-goals (v0.1)**
- No interception of un-checked actions (cooperative perimeter; gateway
  interception is Phase 3+).
- No semantic understanding of scopes/triggers (exact/substring only).
- No verdict caching — every check hits live registry + introspection.
- No LLM anywhere in the decision path.
