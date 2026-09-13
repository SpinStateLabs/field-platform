# spend-governor

Deterministic spend metering against manifest caps. FIELD letter **E**
(Enforcement). Exec owners: **CFO / CTO**.

The meter, not the gate: it records spend (cents, tokens, actions), fires a
**human escalation before the cap** (default 80%), and reports `BLOCK` at
the cap. The conformance-sentinel reads `/status` and refuses the action.
All arithmetic is integer — money is cents, comparisons are exact, no LLM.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/caps/{agent_id}` | PUT / GET | Configure caps (from a manifest's `spend_cap` or explicit) |
| `/spend` | POST | Record a spend event → returns status (OK / ESCALATE / BLOCK) |
| `/usage` | POST | **Agents report token usage** (`model`, `input_tokens`, `output_tokens`); FIELD prices it from the model and folds cost into the cap, runs rogue detection |
| `/usage/{agent_id}` | GET | Token totals, computed cost, per-model breakdown, open rogue flags |
| `/policies/{agent_id}` | PUT / GET | Usage policy: `allowed_models` allow-list + `token_rate_limit` burst ceiling |
| `/status/{agent_id}` | GET | Current window totals + state (the sentinel reads this) |
| `/escalations` | GET | Open human-review queue |
| `/escalations/{id}/resolve` | POST | Human resolves (`resolved_by` required). **First resolver wins**: 200 with the row; the same human retrying gets 200 and the unchanged row; a different human gets **409** with the unchanged row (the first `resolved_by` is never overwritten) |
| `/health` | GET | Liveness |

## Token-cost governance

Agents must **report token usage** (self-report via `/usage`, or
automatically through `force-gateway`, which now sends model + tokens).
FIELD computes the **dollar cost from the tokens and the model used** via a
price book (`field_core.pricing`) and feeds that cost into the *same* cap
that already escalates-before-cap and blocks — so runaway token spend trips
the existing machinery. On top of the cap, three deterministic **rogue
signals** make abuse visible even below it:

| Signal | Fires when | Ledger event |
|---|---|---|
| `rogue_model` | the agent uses a model outside its `allowed_models` allow-list | `usage.rogue_model` |
| `rogue_burst` | input+output tokens in the rate window ≥ `token_rate_limit` | `usage.rogue_burst` |
| `unpriced` | the model has no price — cost can't be governed (suspicious in itself) | `usage.unpriced` |

Each finding is a ledger event **and** a human-queue escalation. The
default price book is Anthropic's **public list price**, transcribed from
platform.claude.com on a dated snapshot and **fully overridable** with your
negotiated rates (`FIELD_PRICE_BOOK` → a JSON file). Money is integer
price units (1e-7 USD) end-to-end; no floats near a limit.

## CLI

```
governor set-cap <agent-id> [--from-manifest m.yaml | --limit-cents N] [--token-limit N] [--action-limit N] [--period daily|monthly|total]
governor spend <agent-id> [--cents N] [--tokens N] [--actions N]    # exit 1 on BLOCK
governor status <agent-id>
governor escalations [--agent-id ID]
governor resolve <escalation-id> --by "Human Name"
governor serve [--port 8006]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Integer arithmetic; no float drift at limit boundaries | **Enforced in code** | cents-int comparisons (`spent*100 >= limit*pct`); adversarial test |
| Threshold escalation fires **before** the cap, once per crossing | **Enforced in code** | dedup on open escalations: the check and the insert are one store call (one lock hold, one `BEGIN IMMEDIATE` transaction), so concurrent crossings open and ledger exactly one escalation per (agent, kind); a partial unique index backs it wherever the database holds no pre-v1.2 duplicates (`tests/test_escalation_atomicity.py`) |
| A resolved escalation keeps its first resolver | **Enforced in code** | `UPDATE … WHERE resolved=0`; exactly one `spend.escalation_resolved` note; retries and refused (409) resolves write none (`tests/test_escalation_atomicity.py`, `tests/test_governor_store_concurrency.py`) |
| At/over cap ⇒ status BLOCK | **Enforced in code** | pure `evaluate()` |
| Negative spend cannot reduce totals | **Enforced in code** | `ge=0` validation |
| Spend without a configured cap is refused | **Enforced in code** | 404 "ungoverned spend" |
| Manifest `spend_cap` maps exactly (sub-cent limits refused) | **Enforced in code** | `from_manifest` |
| Agents actually report their spend | **Declared only** | self-reported metering; interception belongs to force-gateway (LLM spend) and sentinel wiring |
| BLOCK actually stops the agent | **Declared only** (here) | enforcement is the sentinel's `/check` — this service only reports state |
| `per-run` periods | **Declared only** | mapped to `total` in v0.1 (no run concept yet) |

## LIMITS

- Self-reported spend: an agent that never calls `/spend` never hits the
  cap. The honest deployment wires spend recording into the `@governed`
  decorator and the force-gateway, not the agent's goodwill.
- Ledger notes are best-effort (metering survives ledger outages; the gap
  is visible in audit as missing `spend.*` events). Mint-style fail-closed
  semantics belong to authority changes, not meters.
- Window boundaries are UTC calendar days/months.
- A persisted database that already holds duplicate open escalations
  (written before the check-and-insert was atomic) still opens: it logs a
  warning, skips the unique index, and leaves every duplicate in the queue
  for a human (nothing is auto-resolved). The index is added on the first
  start after they are resolved. The store keeps no `resolved_at` column,
  so the resolution time is not recorded here.
- Rollback: an image older than this change, run against a database that
  already has the index, gets an `IntegrityError` (HTTP 500 on `/spend` or
  `/usage`, after the spend is recorded) instead of a duplicate escalation
  when two requests cross a threshold at the same moment.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
