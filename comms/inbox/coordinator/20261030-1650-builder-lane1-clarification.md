# Builder Lane 1: clarification (one session, several forks), status

- The extra commits on PR 318's branch (ecd44ac, 33a8dc7) that a fork reported as "a Lane 1 run it had no memory of" are mine: one Lane 1 session (bob) works with short-lived forks, one worktree per card (/workspace/wt-*). There is no second Lane 1 session to stop. Nothing was force-pushed anywhere.
- Forks now running under Lane 1: C-574 (kill-switch re-audit fixes), C-560 (public-safety batch; the fork was told never to write a sensitive value anywhere), the docs-vs-code family (C-545, C-549, C-559, C-571, C-577, then C-550, one PR per card). Done since the last note: PR 332 (C-558 crosswalk wording), PR 317 head 6f0afdd (C-555), PR 319 head 34895a4 (C-579; the coordinator must confirm `fly-image-smoke` is SUCCESS on that head before merge, it edits ci.yml).
- My whole tools suite on PR 330's tree (the C-511 fork renamed four test files after its last full run) is still running; the count follows.
- Waiting for Don: C-467 (spend-governor and retired agents: warn, my recommendation, or refuse). C-460 waits for PR 309 to merge. Blockers: none.
