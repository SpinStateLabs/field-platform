# C-74: triage of the two untriaged heads and the second delete script (teammate-don-reviewer, 2026-10-28)

Files: 20261028-1815-reviewer-c74-delete-branches-2.sh (6 `del` entries; NOT RUN; same safety rules as C-63: dry-run default, deletes only when the remote tip still equals the recorded sha, protects main, comms, #55, #56, #57, fix/renew-token-signed). `bash -n` syntax check: see the commit.

## The two untriaged branches (HIGH): both fully merged, safe to delete
- claude/field-gate-v1-1-integration-7u50hv (bab3d91, 2026-09-12): PR #1 MERGED 2026-09-12T09:27:30Z, tip = PR head; `git merge-base --is-ancestor <tip> origin/main` true; `git rev-list --count origin/main..origin/<branch>` = 0 (nothing only on the branch); main commit 1727de0 is the merge. (It was missing from the C-61 list because an ancestor of main is not "unmerged", not because it was skipped.)
- claude/state-field-gate-1-1-0 (df774fe, 2026-09-12): no PR; tip is an ancestor of main (true), 0 commits only on the branch (138 behind, 0 ahead); one `docs(state)` commit already in main's history.
## The four earlier ones
ci/harden-workflows-2026-10-23 (#16), ci/topology-lint-2026-10-23 (#18), feat/phase-g-check-tool (#28), feat/claude-approver-v0 (#35): squash-merged, tips equal the PR heads (C-9, C-39, C-59); tips re-read from the fresh fetch for this card (4331864, fd59807, fb80a31, 9f1f4ee).
## After this script runs
Remote heads left would be: main, comms, feat/machine-verifier-identity, feat/alerts-ntfy, feat/kr-r4a-rotator-core, fix/renew-token-signed.

