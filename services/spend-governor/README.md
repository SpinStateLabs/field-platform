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
| `/status/{agent_id}` | GET | Current window totals + state (the sentinel reads this) |
| `/escalations` | GET | Open human-review queue |
| `/escalations/{id}/resolve` | POST | Human resolves (`resolved_by` required) |
| `/health` | GET | Liveness |

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
| Threshold escalation fires **before** the cap, once per crossing | **Enforced in code** | dedup on open escalations |
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
- No API authentication in v0.1 — localhost trust (STATE.md OQ-1).
