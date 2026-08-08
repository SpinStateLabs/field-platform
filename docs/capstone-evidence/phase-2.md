# Phase 2 evidence — Enforcement (spend-governor · kill-switch · conformance-sentinel)

**Date:** 2026-08-08 · **Status:** COMPLETE · **Tests:** 95 passing platform-wide
(41 field-core + 6 sealed-ledger + 7 agent-registry + 8 delegation-authority +
10 spend-governor + 8 kill-switch + 15 conformance-sentinel)

## What shipped

**spend-governor** (E · CFO/CTO) — integer-cents metering vs. manifest-derived
caps; escalation to a human queue at a configurable threshold (default 80%)
*before* the hard cap; BLOCK at the cap. No floats near a limit, no LLM.

**kill-switch** (E · CEO/CISO) — `/kill/{agent}`, `/kill/domain/{domain}`,
heartbeat (fail-closed for unknown agents), `/drill` that kills, verifies
propagation, restores, and reports milliseconds. Act-first ordering: a halt
never waits on the audit trail (documented asymmetry vs. ledger-first minting).

**conformance-sentinel** (E · CISO) — the policy-enforcement point. Eight-step
deterministic decision sequence; first failing clause decides; every verdict
cites a stable clause id and is written to the sealed ledger. Ships
`@governed`, the decorator that puts any Python tool call behind `/check`.

## The honesty line, enforced

Phase 2 is where declared governance became enforced governance:

- A manifest that *declares* `cryptographic_seal: true` and gets quietly
  edited to `false` on disk → the agent loses **all** authority at its next
  check (`I.manifest`). Proven by an adversarial test that edits the file.
- A killed agent's next `/check` is BLOCK in the same request (drill-measured
  platform propagation: ~46 ms kill-confirmed, ~59 ms total in the demo run).
- A token narrower than the manifest: the narrower grant wins (`D.scope`).
- Ledger unreachable ⇒ **no** actions at all (`L.unreachable`) — an action
  that cannot be audited does not run.
- A manifest that declares a spend cap nobody wired into the governor does
  not silently pass — it escalates the metering gap to a human.

Still declared-only (stated in READMEs): the perimeter is cooperative — an
agent that never calls `/check` is not intercepted in v0.1; process-level
termination; operator authn.

## Demo output excerpt (six-service stack, one agent's afternoon)

```
  ALLOW    clause=None            all clauses satisfied
  BLOCK    clause=D.scope         'transfer funds' not in token scope [...]
  BLOCK    clause=D.token         no delegation token presented
  BLOCK    clause=E.kill_switch   agent is killed; kill-switch propagation
  ESCALATE clause=E.spend_threshold  cents at 41000/50000 — crossed 80% threshold
  ...ledger verify: True
```

Demo wall times: governor ~10 s · kill-switch ~11 s (drill: 59 ms) ·
sentinel ~21 s (boots all six services). All <60 s.

## Test counts

95 total. New adversarial cases this phase: negative spend rejected;
integer threshold exactness at 99% of a $6,000 cap; registry-down kill
fails loud while ledger-down kill still lands; unknown-agent heartbeat says
stop; on-disk manifest unsealing; token-narrower-than-manifest; ledger-down
sentinel blocks everything; blocked function body never executes under
`@governed`.
