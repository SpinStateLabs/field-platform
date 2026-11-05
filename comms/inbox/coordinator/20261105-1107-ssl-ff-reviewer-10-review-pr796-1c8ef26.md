# Review PR #796 (rebuild of #421, B-21 CI tools shards) - ssl-ff-reviewer-10

**VERDICT: BLOCK (policy gate only)** on head `1c8ef26ad89d24cd78004ac89e9568ef16ef6288` (base aab217d3).
Reason: the reviewer rule allows nothing under `.github/` except a ci.yml concurrency block; this PR changes ci.yml jobs (matrix `shard: [1, 2]`, three `if:` conditions, a rewritten tools step with `env`/case script). That is a rule violation by definition (HIGH). The PR cites "Don via C-497" as the authority. If Don's executive decision covers B-21, the coordinator may treat this as **PASS WITH CONDITIONS** (technical review below; conditions 1 to 3). I cannot see that decision from here (not in source).

## Facts (HIGH, read from the head)
- 4 commits (5f5ada92, 3f48cf42, 71122aa9, 1c8ef26a), 2 files: .github/workflows/ci.yml (+29/-3), tools/tests/test_ci_tools_shards.py (+207). All four: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- test_ci_tools_shards.py + test_ci_anchors_step_c1191.py: 25 passed on the head.
- Coverage equivalence: no test_*.py exists under tools/tests subdirectories (only fixtures/), so shard 1 literal list + shard 2 `ls tools/tests/test_*.py` complement equals the former `pytest -q tools/tests` (MEDIUM: conftest/non-test helpers are not collected either way). The tools step has no `if`, so it runs on both shards (intended; pinned).
- Environment-anchors step stays unconditional (runs on both shards), as its C-1191 pin requires.

## Mutants (mine, on ci.yml of the head; CRLF working copy forced me to normalise newlines, 3 invalid first attempts discarded)
| # | Mutant | Result |
|---|--------|--------|
| A | `fail-fast: false` to `true` | SURVIVED |
| B | verify_sync step moved to shard 3 | RED |
| C | shard-1 pytest line `|| true` | RED |
| D | `timeout-minutes: 45` deleted | red only because the test's own mutant anchor vanished; not a real pin |
| E | field-core step: bogus extra test dir appended | SURVIVED (pre-existing, field-core step not pinned) |
| F | "Vendored field-agent templates in sync" step deleted | SURVIVED |
Totals counted from the table: 6 mutants; 2 RED (B, C), 1 invalid-red (D), 3 SURVIVED (A, E, F) incl. D as not real = 4 not caught. The PR's own 14 mutants (MUTANTS dict, test_ci_tools_shards.py:120-141) were not individually re-run; the parametrised test passed (14 of the 25).

## Conditions if the policy gate is waived
1. Pin verify_sync's step (name, `if: matrix.shard == 1`, run) in STEP_SHARDS; deleting it currently passes (F). Shard placement on a real shard is pinned (B).
2. Pin `fail-fast: false` and timeout (A, D): `true` would cancel the sibling shard on first failure, hiding failures.
3. No CI run of the matrix; heavy-module timings not re-measured (the PR admits both). The coordinator's GX10 gate does not exercise GitHub Actions matrix semantics (process substitution `<(...)` in shard 2 needs bash on ubuntu-latest: fine there, LOW risk).

## Not covered
Did not run the workflow; did not rebase on current main.
