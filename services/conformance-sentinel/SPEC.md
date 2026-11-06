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

## Corrections

### 2026-11-04 — v0.1 scope lines 25–26 are stale (item B-P-22)

Verified against main cd3b76901f9aabfd45cee546f597177b8739d6ea. The v0.1
scope lines above are left as written; where they disagree with this entry,
this entry governs.

- **CLI list (line 25, "`sentinel check | clauses | serve`") is incomplete.**
  `services/conformance-sentinel/src/conformance_sentinel/cli.py` registers
  these commands: `version` (line 28, prints
  `conformance-sentinel <version>`), `check` (line 33), `self-manifest`
  (line 59), `clauses` (line 91), `score` (line 98) and `serve` (line 203).
  `pyproject.toml:20` binds the `sentinel` entry point to that app.
- **Exit codes "0/2/1" belong to `sentinel check` only** (ALLOW / ESCALATE /
  BLOCK, `cli.py:40`). `sentinel score` exits 0 when its gates pass and 3 when
  they fail (`cli.py:115`). `sentinel self-manifest` exits 1 if the
  self-manifest fails validation (`cli.py:61-62`).
- **"15 tests" (line 26) is not the current test count.** A hard-coded count
  goes stale with every test added, so none is copied here. Read the live
  number with `pytest --collect-only -q` from `services/conformance-sentinel`.
  The named adversarial cases (manifest unsealed on disk, token narrower than
  manifest, ledger down, out-of-scope block) were not re-checked in this
  entry.
