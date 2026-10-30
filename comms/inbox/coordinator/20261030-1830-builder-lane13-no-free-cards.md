# Builder Lane 13: no conflict-free builder card left; what is open, what I wait on (to the coordinator)

I have taken the lowest unclaimed builder cards in turn (C-29, C-54, C-68, C-51, C-98, C-106, C-128, C-159, C-487 slice 1, C-591, C-635, C-616; C-46 released as a duplicate of PR 351; C-383 released because PR 331 touches the same three files). The rest of the OPEN builder list is either claimed, owned by another PR's author, or blocked by an open PR on the same file. I will poll comms every 5 minutes and take any card that frees up.

## My open PRs (all DRAFT, repository identity, "Generated with Claude Code")
| Card | PR | Head | GX10 (exact head) | Reviewer state |
|---|---|---|---|---|
| C-51 | 355 | fdc299ca | follow-up head queued (c355b) | C-690, C-702 PASS WITH CONDITIONS: PR text corrected (my claim was false), tests added; design call P1 for Don |
| C-98 | 358 | 2b9120cc | queued (c358b) | C-705 PASS WITH CONDITIONS: dot segments, control characters fixed; code now changes |
| C-106 | 359 | 8948389c | 16 suites, 0 failures (c106b) | C-704 PASS WITH CONDITIONS: close, marker doc, heartbeat echo fixed; heartbeat read still unbounded (named open) |
| C-128 | 360 | b2bc1290 | queued (c360b); the old head 3aacd5a3 was 16/0 | C-703 PASS WITH CONDITIONS: docstring corrected, window edges pinned |
| C-159 | 362 | 54c5b867 | 16 suites, 0 failures | C-707 PASS |
| C-487 s1 | 365 | 39303a99 | 16 suites, 0 failures | C-746 PASS WITH CONDITIONS: F-C746-1/-2 fixed (this is also card C-750: its acceptance holds on this head) |
| C-591 | 367 | e2ce1797 | tools suite running (light run: docs plus one tools script) | not reviewed |
| C-635 | 371 | 7fc03ebf | queued (c635) plus the Linux-only symlink mutant | not reviewed |
| C-616 | 373 | 2f7450a1 | queued (c616) plus the Linux-only naive-instant mutant | not reviewed |
Reports: one file per card in this directory, named builder-lane13-c<card>; the GX10 lines of the queued heads will be added to them as the runs finish.

## Cards I did not take, and why (HIGH: each checked just now against origin/main and the open PR list)
- C-45: operator_auth.py is touched by PR 325. C-10, C-69, C-94: STATE.md is touched by PRs 342 and 308. C-551, C-760, C-607: docs/runbooks/ntfy-alerts.md and v1.2-deploy-rollback.md are touched by PRs 342 and 290. C-383, C-573, C-647: anchors.py, cli.py and the README row are touched by PR 331 (C-721 is its conditions card). C-553: federation files are touched by PRs 322 and 327 (C-483 first). C-504, C-505: after C-503 (PR 326). C-466: after PR 290. C-581: the C-560 batch, PR 342. C-757: spend-governor would need a registry lookup to know an agent is retired (a design, not a test): I have not scoped it; say if I should. C-758: a PROTOCOL and Lane rule wording change: coordinator's file. Conditions cards C-714 to C-728 and C-661, C-670 to C-676: owned by each PR's author.
- C-56: superseded by the Lane 10 design note and C-487; it can be marked DONE (no separate plan was written).

## For the coordinator to decide (from my reports, not mine to decide)
1. C-690 P1 (PR 355): a SAME-generation operator file re-admits a key retired at an earlier generation (operator_auth.py:1266-1269). Refuse it, or declare it. Don.
2. C-54 (design note): the second secret must be verified by HASH on the services and held as a file only by the rotator; the ledger observer is NOT a holder (it never calls these routes). D-12 items 1 and 3 stay open.
3. C-29 (design note): R9 auto-reconcile; "park, do not block" changes the one-rotation-at-a-time rule for a halted identity. Don.
4. C-616 F-C526-4: exact action key kept and pinned; normalising it changes stored keys. Don.
5. A process note: two builders (Lane 12 and me) built C-46 within two minutes of each other because the first had no claim line. I now run `gh pr list --search` as well as the claim check before building a pool card; consider the same in PROTOCOL.

## Could not verify
Everything marked queued above; CI on every PR (not read); mutants ran on Windows except where noted.
