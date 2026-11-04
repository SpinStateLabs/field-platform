# Reviewer (read-only, post-merge): batch cb4 = MERGE 2, main 4d0c3315 -> 7de2a064 (PR 413 @468af22f, PR 412 @27f8e4b8; 2 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `7de2a064`** (full PR heads: 413 `468af22f959f3fe6d03fd7336234ea8700898761`, 412 `27f8e4b8ee6277cb6557107a769816cd4068cae7`). No earlier file names cb4 as a batch; this is that file.

## Record checked (HIGH, from git and gh)
- 2 commits (STATUS: two PRs), a fast-forward, 0 nonconforming identities (Don Hagell noreply, author and committer). PRs 412 and 413 CLOSED with a pointer comment each, CI SUCCESS 7/7 on each head.
- Reviewer PASS naming the full heads: PR 413 in `20261101-0945-reviewer-q39-pr413-...` ("VERDICT PASS on 468af22f..."), PR 412 in `20261101-0925-reviewer-q38-pr412-...` ("VERDICT PASS (as tests) on 27f8e4b8..., AND DUPLICATE of PR 402"). Verifier A on the batch head: `20261101-0251-gx10-verifier-A-batch-cb4.md` names 7de2a064be460689b85d2957fde8fdd3478687fb before and after the run, "16 of 16 suites passed, 0 failed". Per-PR verifier B runs also exist (pr412, pr413).
- The B-10 rename left no caller of the old names: `git grep` for `reset_stats(` and `reset_retired_memory(` without an underscore finds 0 at 7de2a064 and 0 on current main.
- Known caveat (Q-38): PR 412 duplicates PR 402 with weaker pins; 412 landed, so 402 had to be rebased afterwards (it landed later in rb-stack2). Not a defect of this batch.

## Objections first
1. Both PRs are tests plus a two-line rename; their value is the pins, so I attacked the pins, not the rename.
2. The hook-reset test (B-10) asserts one counter and one flag after the reset, not the whole state the hooks clear; the mutants below show how much of it is pinned.
3. The "expired N days ago" sign pin and the strict-path pins are about wording and a tight allow-list: cheap, but they guard an operator-facing refusal.

## Measured (GX10 ~/ff-work/wt-cb4 at 7de2a064, python -B, own venv)
`tools/tests/test_renew_token_pins_c212.py` + `test_reset_hooks_private_b10.py`: 49 passed. The 16-suite is the verifier's report.

## Mutants (28 rows; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| G1 `is_guarded` matches the full path only | 5 | 0 |
| G2 the query is ignored, the method case is folded | 4 | 1 (gap: `rstrip("/")` would let `/delegation/tokens/` pass) |
| E1 an expired token prints a positive age ("expired 3.0 days ago") | 5 | 0 |
| E2 exactly zero left is expired, not within the window | 4 | 0 |
| H1 the reset hooks have underscore names only (no public alias) | 5 | 0 |
| H2 the hooks still reset | 1 | 3 (2 equivalent: `alerts._reset_stats` re-zeroes with `update(_zero_stats())` after `clear()`; 1 gap: `_retired_state.clear()` can be removed and only `retired_hash_seen` is checked) |
Totals counted from the table: killed 5+4+5+4+5+1 = 24; survived 0+1+0+0+0+3 = 4; 28 rows. 2 survivors are equivalent and 2 are gaps; H2 is the only behaviour below 4 kills.

## Conditions
- C1: none blocking (merged; record complete).

## Findings (non-blocking; new PR only)
- F-cb4-1 LOW: a hook test that checks `_retired_state` is empty after `_reset_retired_memory()` (H2 gap).
- F-cb4-2 LOW: `is_guarded("POST", "/delegation/tokens/")` with a trailing slash is unpinned (G2 gap).
