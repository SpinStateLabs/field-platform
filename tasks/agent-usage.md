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

## 2026-09-12 → 13 — v1.2 production build, session c1a86b9f (Claude Code desktop)

Figures are summed from each sub-agent's own transcript (API-reported usage, assistant messages de-duplicated by id), not estimated. Per-agent detail: `tasks/usage-report-2026-09-13.md` (generator: session scratchpad `usage/usage_report.py`). Cache reads are billed at a fraction of normal input.

| Started (UTC) | Workflow | Agents | Model(s) | Output tokens | Cache writes | Cache reads | Uncached input | API calls | Tool calls | Wall h | Agent-h |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-12 10:09 | verify-state-block-and-windows-report (wf_3c2214a9-593) | 6 | claude-fable-5-1 | 200 k | 798 k | 10.64 M | 3 k | 87 | 131 | 0.3 | 0.9 |
| 2026-09-12 12:45 | ground-v1-2-closure-plan (wf_885a53c6-0d5) | 13 | claude-fable-5-1 | 697 k | 2.37 M | 74.59 M | 14 k | 453 | 479 | 0.6 | 2.4 |
| 2026-09-12 13:31 | review-v1-2-plan (wf_bc21e4e7-a73) | 6 | claude-fable-5-1 | 301 k | 1.34 M | 33.11 M | 6 k | 179 | 195 | 0.4 | 1.1 |
| 2026-09-12 14:08 | build-phase-a (wf_96783cf5-6f8) | 5 | <synthetic>, claude-fable-5-1 | 86 k | 477 k | 5.88 M | 1 k | 54 | 73 | 0.1 | 0.3 |
| 2026-09-12 14:48 | plain Agent calls | 5 | claude-opus-5 | 299 k | 1.15 M | 47.45 M | 1 k | 258 | 303 | 6.0 | 1.4 |
| 2026-09-12 15:35 | build-phase-b (wf_8750c2bf-5b8) | 6 | claude-opus-5 | 372 k | 1.22 M | 71.36 M | 1 k | 397 | 448 | 1.3 | 1.5 |
| 2026-09-12 19:07 | phase-c-ground-truth (wf_27809387-93c) | 9 | claude-opus-5 | 509 k | 2.60 M | 62.74 M | 1 k | 361 | 432 | 0.6 | 1.8 |
| 2026-09-12 19:19 | deploy-preflight-a-b (wf_184db9e8-57f) | 13 | claude-opus-5 | 785 k | 2.57 M | 95.28 M | 1 k | 554 | 580 | 1.0 | 3.0 |
| 2026-09-12 19:22 | challenge-plan-revision-2 (wf_5cc2aad5-844) | 6 | claude-opus-5 | 357 k | 1.55 M | 57.69 M | 1 k | 300 | 309 | 0.6 | 1.5 |
| 2026-09-12 19:45 | c2-ledger-rotation-design-panel (wf_e107b392-c58) | 7 | claude-opus-5 | 1.61 M | 14.93 M | 396.85 M | 2 k | 962 | 1105 | 6.1 | 11.5 |
| 2026-09-12 22:34 | build-x1-and-c1 (wf_ba0088c5-ba9) | 7 | claude-opus-5 | 791 k | 3.76 M | 156.37 M | 1 k | 567 | 647 | 2.5 | 4.2 |
| 2026-09-12 22:53 | vt-repair-investigation (wf_a1f81b8a-50b) | 4 | claude-opus-5 | 192 k | 650 k | 20.09 M | 0 k | 137 | 154 | 0.5 | 0.7 |
| 2026-09-12 23:29 | build-token-renewal (wf_4c16d8f0-388) | 5 | claude-opus-5 | 782 k | 8.59 M | 108.42 M | 1 k | 348 | 400 | 4.6 | 5.4 |
| 2026-09-13 01:04 | reverify-x1-c1-fixes (wf_83c19ad9-030) | 4 | claude-opus-5 | 188 k | 932 k | 32.06 M | 0 k | 174 | 186 | 0.7 | 1.4 |
| 2026-09-13 02:09 | phase-c-build (wf_dd6baf04-4ab) | 26 | claude-opus-5, claude-sonnet-5 | 2.36 M | 19.77 M | 621.52 M | 4 k | 1876 | 2219 | 10.5 | 18.3 |
| 2026-09-13 04:08 | renewal-hardening (wf_ca83e1fb-6b8) | 9 | claude-opus-5 | 1.15 M | 9.98 M | 224.97 M | 2 k | 755 | 878 | 5.6 | 8.6 |
| 2026-09-13 09:48 | hardening-close-2 (wf_d006eeba-79c) | 10 | claude-opus-5 | 798 k | 4.62 M | 155.45 M | 1 k | 695 | 779 | 2.8 | 5.8 |
| 2026-09-13 12:39 | phase-c-residuals (wf_55369f99-019) | 2 | claude-opus-5 | 146 k | 952 k | 39.05 M | 0 k | 174 | 202 | 0.7 | 0.7 |
| | **All sub-agents** | **143** | <synthetic>, claude-fable-5-1, claude-opus-5, claude-sonnet-5 | **11.62 M** | **78.27 M** | **2213.51 M** | **39 k** | **8331** | **9520** | | **70.4** |

Main session (orchestrator): Model(s) <synthetic>, claude-fable-5-1, claude-opus-5; output 962 k; cache writes 7.09 M; cache reads 340.20 M; uncached input 3 k; 729 API calls; 812 tool calls; 27.9 h since the transcript began.

### Appended 2026-09-13 from the NSPB fleet-scaffold session (b9ed779a) — EXCLUDED from the totals row above

Only subagent output tokens / tool calls / wall duration were captured in
these completion notices (no cache-read/write breakdown available —
columns left out rather than guessed).

| Date/time | Run | Agents | Model | Subagent tokens | Tool calls | Wall |
|---|---|---|---|---|---|---|
| 2026-09-08 | spin-state-agent-fleet (wf_2b59dc6b-054) | 12 (6 scaffold ‖ 6 verify) | claude-fable-5 (inherited) | 1,606,169 | 268 | 9.8 min |
| 2026-09-08 | SDLC-scaffolding research (claude-code-guide agent) | 1 | claude-fable-5 | 110,442 | 22 | 2.1 min |
| 2026-09-08 | launch.py patch adversarial review (general-purpose agent) | 1 | claude-fable-5 | 140,042 | 15 | 5.4 min |

## 2026-09-14 — Phase F build, session ae3d31d1 (Claude Code desktop, model claude-fable-5-1)

Figures are the harness's own completion notices per agent (subagent tokens as reported, tool
calls, wall duration); no cache-read/write split is available from those notices, so those
columns are left out rather than guessed. Every agent inherited the session model except the
verifier (Sonnet, per Don's token-economy rule for mechanical command runs). Shape: one
read-only explore, three builders on disjoint files, ONE reviewer per builder (medium depth,
mutation checks, small fixes inline, no separate fixer), one verifier.

| Started (UTC) | Agent | Role | Model | Subagent tokens | Tool calls | Wall |
|---|---|---|---|---:|---:|---:|
| 10:52 | explore: map Phase F code paths | Explore (read-only) | claude-fable-5-1 | 311,937 | 84 | 12.2 min |
| 11:06 | build: F2 ledger signatures + sentinel fail-closed | builder (resumed once) | claude-fable-5-1 | 928,180 | 261 | 84.7 min |
| 11:20 | build: F4 served attest signing | builder | claude-fable-5-1 | 331,132 | 68 | 34.5 min |
| 11:40 | build: F1 gateway enforcement + self identity | builder | claude-fable-5-1 | 402,443 | 76 | 46.8 min |
| 11:47 | review: F4 | reviewer | claude-fable-5-1 | 223,280 | 40 | 25.6 min |
| 11:58 | review: F2 | reviewer | claude-fable-5-1 | 267,983 | 75 | 37.5 min |
| 12:10 | review: F1 | reviewer (resumed once) | claude-fable-5-1 | 502,316 | 125 | 29.5 min |
| 12:52 | verify: full suites + demos | verifier | claude-sonnet-5 | 189,388 | 62 | 70.6 min |

Sub-agent total: **8 agents, 3,156,659 subagent tokens, 791 tool calls, 5.7 agent-hours** (vs. 143 agents / 11.6 M output tokens for the whole previous session).
Two agents stopped early to "wait for a background run" and were resumed with one message
each (their second notice's tokens are included above). Main-session token use is not
reported per task by the harness and is not guessed here.
