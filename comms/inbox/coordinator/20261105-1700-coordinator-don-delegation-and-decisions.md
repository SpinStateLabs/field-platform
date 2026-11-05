# COORDINATOR: Don's delegation and decisions, 2026-11-05

Don is away for several hours. Delegation (Don, in chat): authorization for everything EXCEPT money and features. Work autonomously, record decisions, do not stop to ask. A Fable 5 advisor is allowed (advisor only; the no-Fable rule still holds for workers/reviewers/builders). Goal: production deployment.

Rulings given by Don 2026-11-05 (HIGH, chat):
- C-552 lifted: build G23 alert senders and G24 stage controller now.
- PR 796: .github/ rule waived for the ci.yml shard matrix; re-review on content.
- E1: coordinator defines it (narrowest reading of the Phase E text) and records it.
- Estate arming: run G16 Stage 0 and G18 Stage 1 LOG-ONLY on GB10 and Fly, with rollback, without asking.
- REQUIRE: G25 (kill-switch) and G26 (all eight) are authorized ("both gates, do not wait for me"). G27 is Don's own-key write and cannot be done by an agent: it stays open for Don.
- Production = GB10 + Fly estate. No portal billing, no Stripe, no money.

Excluded (do NOT do): anything that spends money; new product features beyond the committed Phase G/E scope.

Coordinator guardrails (my own, recorded): arm a stage only when (a) its checklist in docs/runbooks/v1.2-deploy-rollback.md passes, (b) the prior stage had a clean window, (c) rollback was rehearsed, (d) red-team has reviewed the stage, (e) G21/G22 decided and implemented before G25, (f) G23/G24 on main before G25 (alerts + controller). Roll back immediately on any dropped_unauthenticated_records or dropped_refused_records increase.

Decision log: decisions are appended below by the coordinator and role sessions.
