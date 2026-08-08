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

**Explicit non-goals (v0.1)**
- No interception of un-checked actions (cooperative perimeter; gateway
  interception is Phase 3+).
- No semantic understanding of scopes/triggers (exact/substring only).
- No verdict caching — every check hits live registry + introspection.
- No LLM anywhere in the decision path.
