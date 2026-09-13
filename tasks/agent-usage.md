# Sub-agent usage report — processing time, tokens, models

> Standing convention (Don Hagell, 2026-09-13): every multi-agent workflow or
> sub-agent run on this project appends its usage here at completion — wall
> time, per-agent tokens/tool-calls/duration, and the model that ran each
> agent — taken from the run's own completion summary, never estimated.
> Numbers not captured before the harness expired the raw journal are marked
> "not retained", not reconstructed (FORCE: no invented figures). Main-session
> (non-subagent) token use is not reported by the harness per task and is not
> guessed here.

## 2026-08-29 — v1.1 ADR build (Sentinel S2 → Crosswalk delta)

### Run 1 · workflow `verify-s1-critique-s2` (wf_e925e086-c78)
Purpose: adversarial verification of the S1 review + critique of the S2
scorecard design, before implementation.
Wall time: **500.9 s** · 3 agents (parallel ×2 then 1) · 45 tool calls ·
**366,576 subagent tokens** · 0 errors.

| Agent | Model | Tokens | Tool calls | Duration |
|---|---|---:|---:|---:|
| skeptic:code-refute | claude-fable-5 | 144,137 | 25 | 202.6 s |
| skeptic:test-audit | claude-fable-5 | 114,876 | 12 | 236.3 s |
| critic:s2-metrics | claude-fable-5 | 107,563 | 8 | 262.6 s |

Yield: 1 real cross-service defect found (shadow-blind reporting → S2-R),
3 HIGH/MEDIUM test gaps (S2.0 backfill), 5 required metric-design changes
adopted into the approved S2 plan.

### Run 2 · workflow `crosswalk-delta-parallel` (wf_3cd78e06-3dc)
Purpose: implement the three ADR 07 Crosswalk modules in parallel on
disjoint files (staleness.py, suggestions.py, evidence_pack.py + tests).
Wall time: **407.3 s** · 3 agents (parallel) · 40 tool calls ·
**402,262 subagent tokens** · 0 errors · all 28 delivered tests green on
first pass (8 + 12 + 8).

Per-agent token/model breakdown: **not retained** — the run journal expired
before this report was requested (2026-09-13). The workflow declared no
model override, so agents ran on the session default (claude-fable-5 at the
time); that is an inference from configuration, not a journal record.

### Session totals (sub-agents only)
- 2 workflows, 6 agents, **768,838 subagent tokens**, 85 subagent tool
  calls, **908.2 s** combined workflow wall time, 0 agent errors/retries.
- Everything else that session (S1 review, S2/S2-R/S3/S4 and Gateway
  implementation, GB10 deploy) ran in the main session — per-task token
  cost not reported by the harness.
