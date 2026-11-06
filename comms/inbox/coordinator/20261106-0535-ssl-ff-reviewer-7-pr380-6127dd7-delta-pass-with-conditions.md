# Review PR 380 @6127dd75 (field-mcp Tier 2 write tools; delta re-review of reviewer-2's PASS WITH CONDITIONS on 24d5482b) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `6127dd751ed7187f24a21ef33ce5858e0c1cdec6`.
Scope, stated plainly: this is a DELTA review. reviewer-2 reviewed 24d5482b in depth (59 mutants; report 20261104-1407). The head moved by exactly one commit, 6127dd75, tests-only. I verified that delta and the conditions it claims to close. I did NOT re-review the other 37 commits or the supply-chain and CI parts.

## Checks (HIGH, run by me)
- Delta: `git diff 24d5482b 6127dd75` = 1 file, services/field-mcp/tests/test_write_pins.py, +19, no source change. That commit: author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; no Co-Authored-By trailer.
- Whole PR: 38 commits above main, all author AND committer Don Hagell noreply. Trailers: 30 Sonnet 5.5, 7 `Claude Fable 5.1` (the PR body says these are #368's newest commits merged in, and leaves the ruling to the coordinator), 1 none (merge commit).
- `git merge-tree --write-tree origin/main head`: clean (no conflict) on current main ede21674; the merge-base is 5808a5cd, so the head is stale and needs a rebase and fresh GX10 (C3 below).
- Tests: `test_write_pins.py` 21 passed on the exact head (the new C1 test included). Full field-mcp suite NOT run: `mcp` is not installed in my interpreter and I did not download it.
- C1 (reviewer-2: pin intent-to-outcome linkage, mutant W16): the new test asserts rows are intent/outcome pairs in order, each call's intent and outcome share one call_id, two calls have different ids, and the reply's `audit.call_id` equals the rows'. Closed for the success path.
- C2 (rename body schema, S6): the builder says it was already pinned at this head (tests named in the report); I did not re-mutate S6.

## Mutants of the linkage (6; counted from the table)
| # | mutant | result |
|---|---|---|
| W16 | outcome row gets a fresh uuid | KILLED |
| W16b | outcome row constant call id | KILLED |
| W16c | reply `audit.call_id` differs from the rows | KILLED |
| W16d | call id reused across calls | KILLED |
| W16e | FAILURE-path outcome gets a fresh uuid | SURVIVED |
| W16f | outcome payload drops call_id | KILLED |
Totals: 6 mutants, 5 killed, 1 survived (5+1 = 6).

## Findings
1. LOW-MEDIUM, C1 is closed only for the success path: W16e survives. tools.py:238 and :243 (outcome after a ToolError, and after an unknown-outcome error) can carry a different call id and no test notices; those are the rows an auditor most needs to join. One more test (a failing upstream, then compare ids) kills it.
2. Carried forward, not mine to close: C3 rebase on current main plus CI and GX10 16/16 on the rebased head (the head is old; field-mcp is a new service). C4 supply-chain pins (integration/field-mcp-hashes.txt, constraints) were read by another reviewer, not me.
3. `.github/workflows/ci.yml` changes in this PR beyond a concurrency block (adds a `--require-hashes` install of field-mcp and field-mcp to the per-service test loop, +4/-1). The standing rule is nothing under .github/ except a concurrency block; PR 795 carries the same edit and was reviewed under a ruling from Don (hash-checked closure ruled 2026-10-30, per the comment). Coordinator must confirm this edit is accepted.
4. Duplication hazard: PR 795 (rebuild of 368, Tier 1) and this PR (which embeds Tier 1 via a merge of 368) both add services/field-mcp; whichever lands second will conflict or duplicate. The comms note 20261111-1700 (lane1 merge-368-into-380) suggests this is being sorted elsewhere; I did not read it.
5. By design, no human confirmation of writes (README states it); the controls are audit-first, reason, rate limit (reviewer-2 objections 1-2 stand).

## Not verified
Whole field-mcp suite; CI/GX10; Linux; supply-chain files; the 37 earlier commits (reviewer-2's scope).
