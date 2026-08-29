# conformance-sentinel

The policy-enforcement point. Every proposed action is checked against the
agent's manifest, token, spend state, and kill status — and answered
**ALLOW / BLOCK / ESCALATE with the failed clause id**. FIELD letter **E**
(Enforcement). Exec owner: **CISO**.

This is the service that turns FIELD from *declared* into *enforced*.

## Decision sequence (first failing clause decides)

| # | Check | Clause on failure |
|---|---|---|
| 1 | Sealed ledger reachable (no audit ⇒ no action) | `L.unreachable` BLOCK |
| 2 | Agent registered & active (killed ⇒ instant block) | `R.unregistered` / `E.kill_switch` BLOCK |
| 3 | Manifest present & valid (`field validate`) | `I.manifest` BLOCK |
| 4 | Token presented, active, bound to this agent | `D.token` / `D.expired` / `D.revoked` BLOCK |
| 5 | Action in **both** token scope and manifest scope | `D.scope` BLOCK |
| 6 | Irreversible-action policy | `E.irreversible` BLOCK or ESCALATE |
| 7 | Declared escalation triggers (substring match) | `E.escalation_trigger` ESCALATE |
| 8 | Spend state from the governor | `E.spend_cap` BLOCK / `E.spend_threshold` ESCALATE |

Every verdict (including ALLOW) is written to the sealed ledger as
`conformance.allow|block|escalate`.

## Operating mode — safe-by-default (ADR 02)

`FIELD_SENTINEL_MODE` sets the estate-wide posture; one env var flips it:

| Mode | Behavior |
|---|---|
| `log_only` (**served default**) | Verdicts are computed and **shadow-ledgered** as `conformance.shadow_block` / `shadow_escalate` (carrying the `would_block` clause), but `/check` returns **ALLOW** — nothing is blocked. A new estate observes before it enforces. |
| `enforce` | Verdicts block/escalate for real (the sequence above). |

A new estate ships in `log_only` and graduates to `enforce` only after the
measured gate (catch ≥ 95%, false-block ≤ 2% — see `tasks/todo.md`). Demos and
the compose smoke set `FIELD_SENTINEL_MODE=enforce` to showcase enforcement.
`GET /health` reports the active mode.

## Seeded-violation scorecard (S2 / ADR 02)

`sentinel score` runs a deterministic 100-action seeded suite against a
**log-only** estate (it refuses anything else) and emits a sourced scorecard
(`--out-md/--out-json`; exit 0 gates pass, 3 gates fail). Categories:
scope-breach, expired-token, revoked-token, ledger-unreachable,
ambiguous-violating, exact-conforming, ambiguous-conforming. Gated metrics
*(proposed; ratified at PoC exit)*: **gated catch ≥ 95%** (would-be verdict
must match the seed's expected clause AND decision — refusals for the wrong
reason don't count) and **seeded structural false-block ≤ 2%**. Also reported,
not gated: combined false-block including the semantic gap (paraphrased
conforming actions hard-block pre-S3), false-escalate rate, routing-predicate
coverage (`routing.needs_semantic_judgment` — measurement-only until S3
attaches the judge to it), would-have-blocked, tokens/judgment (0 until S3).

The seeded suite is a **regression harness, not an adversarial eval**: seeds
are authored against the same exact-match checks they exercise, so the gated
numbers are near-tautological by construction — they verify plumbing. The
binding gates for enforce-by-default remain live (2-week log-only burn-in;
30-day live false-block). Captured run: `score_demo.sh` →
`docs/capstone-evidence/sentinel-scorecard-s2.md|.json`.

## API & CLI

`POST /check` `{agent_id, action, token_id?, irreversible?}` → verdict ·
`GET /clauses` · `GET /health`

```
sentinel check <agent-id> "<action>" [--token-id T] [--irreversible]   # exit 0/2/1 = ALLOW/ESCALATE/BLOCK
sentinel clauses
sentinel serve [--port 8004]
```

## `@governed` — one decorator to govern any Python tool call

```python
from conformance_sentinel.governed import governed, ActionBlocked

@governed(agent_id="invoicing-agent", action="draft invoices",
          token_id=lambda: current_token())
def draft_invoice(row): ...
```

BLOCK raises `ActionBlocked` *before* the function body runs; ESCALATE
raises `ActionEscalated`; sentinel unreachable fails closed.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Killed agents fail their next check instantly | **Enforced in code** | registry read per check; test proves it |
| Out-of-scope actions blocked with `D.scope` | **Enforced in code** | intersection of token + manifest scope; narrower grant wins (test) |
| Expired/revoked tokens blocked with exact clause | **Enforced in code** | live introspection per check |
| Invalid/missing manifest ⇒ all authority lost | **Enforced in code** | adversarial test edits the manifest on disk |
| No ledger ⇒ no actions | **Enforced in code** | reachability gate before any ALLOW |
| Declared-but-unmetered spend caps go to a human | **Enforced in code** | `E.spend_cap` ESCALATE on metering gap |
| Blocks/escalates are ledger events | **Enforced in code** | `conformance.*` events |
| Safe-by-default: served estate observes before it enforces | **Enforced in code** | `FIELD_SENTINEL_MODE` defaults to `log_only`; would-blocks are shadow-ledgered, caller not blocked (tests) |
| Scorecard gates: gated catch ≥ 95%, structural false-block ≤ 2% on the seeded suite | **Enforced in code** | `test_scorecard.py` gate test (in-process, full 100-seed corpus) + committed artifact from a real served run |
| Agents route their actions through `/check` at all | **Declared only** | the sentinel governs what it is asked about; bypassing it is an architecture violation the registry/discovery + gateway layers exist to catch |
| Escalation triggers understand meaning | **Declared only** | v0.1 matching is bidirectional substring — deterministic, not semantic |

## LIMITS

- **Log-only + ledger down loses the observation.** In `log_only`, a
  would-block is shadow-ledgered; if the ledger is unreachable at that moment
  the shadow record is lost and the caller is (correctly) not blocked. The
  scorecard's ledger-unreachable seeds quantify this class; live shadow
  traffic lost during an outage is unrecoverable.
- **Missing-write detection is not implemented.** The ledger check is a
  pre-execution reachability proxy; post-hoc executed-vs-ledgered
  reconciliation (the ADR's "missing ledger writes" class) does not exist and
  is not tested — the scorecard category is named `ledger-unreachable`
  accordingly.
- **Unrecognized `FIELD_SENTINEL_MODE` values silently fall back to
  `log_only`.** Fail-safe direction, but a typo ("enfroce", "true") quietly
  disables enforcement — verify `GET /health` after any mode change.
- **Downstream reports don't count shadow events yet.** attestation-reporter
  and compliance-crosswalk read only `conformance.allow|block|escalate`, so a
  log-only estate's board pack shows 100% conformance while violations
  shadow-ledger. Raised as a follow-up (tasks/todo.md S2-R); fix before any
  burn-in whose evidence flows through those reports.
- **The perimeter is cooperative in v0.1.** `@governed` and the demo agent
  route through `/check`; a malicious process with direct tool access
  simply doesn't ask. Containment for that case = revoked tokens + killed
  status + (later) network-level interception via force-gateway.
- Verdict ledger writes after the reachability gate are best-effort; a
  mid-check ledger crash can lose one verdict event while the action
  proceeds. The gate bounds the window; it does not eliminate it.
- Trigger matching is naive substring; write triggers accordingly
  ("send invoice", not "any external send").
- TOCTOU: a kill or revocation landing mid-flight (after ALLOW, before the
  tool completes) is not interrupted — next check catches it.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
