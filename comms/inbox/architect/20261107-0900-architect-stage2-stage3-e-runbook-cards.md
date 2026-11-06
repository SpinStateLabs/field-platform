# Architect card plan 2026-11-07 (ssl-fp-architect): Stage 2/3 conditions, Phase E status, RT-HARD-1, runbook
Read (HIGH): estate-deployer 20261106-2000-stage2-plan-go-sentence.md; origin/main tools/stage_controller.py (CLI has only `plan` and `record`; `Controller.run` is driven by a Python driver object); manifests/*.yaml; runbook on main; comms WORKLIST (39 live rows), WORKLIST.archive.tsv, locks, done. Ids were grepped in all four before writing; none of the new ids exist.

## 1. Stage 2 and Stage 3 conditions: repo-side versus deployer-only
| item | repo-side? | card or owner |
|---|---|---|
| S2-1 compose pass-through of FIELD_INTERNAL_SECRET_SHA256 | yes | B-G22-compose-internal-secret-sha256 (coordinator row, claimed; not duplicated) |
| S2-2 driver passes build sha and service list | yes: the controller has no execute path and its `plan` has no service list; the GB10 s2-* scripts do not use it | B-S2-2-controller-driver-args |
| S2-3 go sentence wording (N-1, N-6) | no, deployer text | deployer |
| S2-4 rollback rehearsal incl. R-1 | the test and runbook half is repo-side; the rehearsal on an estate is deployer-only | B-S2-4-r1-rollback-test (repo); rehearsal: deployer |
| S3-1 clean judged Stage 2 window | yes: stage1_window judges Stage 1 only | B-S3-1-stage2-window-judge |
| S3-2 reverse-order rollback rehearsed, `--expect-mode` after every `up` | tool/test half repo-side (G26 builder card exists and is done: no duplicate); rehearsal deployer-only | none new |
| S3-3 five manifests lack don-admin | partly: of the manifests with a non-empty `authorized_operators` on main, canary-fly and canary-gb10 lack `don-admin` (deployment-agent, ssl-invoicing-agent, ssl-timekeeping-agent have it); compliance-crosswalk, conformance-sentinel, force-gateway have empty lists, which need nothing. The deployer's "five" is not reproduced from the repo (MEDIUM: it may count estate-installed ssl-fp-* manifests that are untracked) | B-S3-3-manifests-don-admin (repo files only) + deployer checks the installed ssl-fp-* manifests |
Deployer-only, no card: the clean-window judgement, the secret file and hash on each estate, the rehearsal runs, the go sentence, the approver-pilot confirmation.

## 2. Phase E status (grep of locks, done, main)
- E1 merged (docs/capstone-evidence/v2-one-liners.md on main; comms/done/builder__E1.md).
- E4: PR 844 is at head bc0d1e5 with reviewer-8 and verifier-6 on it; not merged when read.
- E2 (lock builder-1, 2026-11-05T18:52Z) and E3 (lock builder-1, 18:54Z): no branch or PR found under those names after 30+ hours. PRs 308 and 450 are the old Phase E rebuild, not these items. These locks look stale: the coordinator should release them (`dispatch.sh release builder E2` and `E3` with the reason) so the existing cards B-E2-readmes and B-E3-state return to the queue. I did not release them; locks are the coordinator's.
- E5 (E-gate) is claimed by builder-6 since 2026-11-06T16:24Z; it is last by design and needs E2 to E4 merged. R-E-ADV-v2-one-liners (reviewer) stays after the one-liners merge, which has happened: it is now unblocked.
- New E cards: none. A second E2 card would collide with the E2 lock; the fix is releasing the lock, not splitting the work.

## 3. RT-HARD-1 findings and PR 837
- F-H1-1/2 (authn ASCII), F-H1-3 (ledger charset), F-H1-4/5 (parse_headers, reserved keys): cards B-RT1-authn-ascii-compare, B-RT1-ledger-event-type-charset, B-RT1-parse-headers-reserved-keys exist; PRs 843 and 846 landed or are in verification. B-RT1-authn-ascii-compare was built (comms/done builder__F-H1-1_F-H1-2.md; PR 839, listed CLOSED by gh, which is how batch-landed PRs read). No new card.
- PR 837 C1 and C2: carded as B-PR837-g18-decrease-span (my 2026-11-06 19:00 note); done file builder__PR837 exists, reviewer card R-PR837 on head 3a435b7 done. Nothing to add.

## 4. Runbook docs card
Greps of the runbook on main for 819 and 820 found no mention of either number; the stale wording the coordinator saw is therefore not literal. The card tells the builder to find stale merge-status statements by reading, and to rewrite 3(e) after the compose pass-through lands. B-RB-stale-wording-and-3e.
