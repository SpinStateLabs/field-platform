# Review PR 793 (rebuild of 478, C-1192 pytest --shard) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `ff613b31e94783c9eb1cd31fbdf8349af68a330d` (no conditions; 3 optional LOWs go in a NEW PR).

## Checks (all HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. Files under .github/: 0.
- Rebuild fidelity: `git patch-id --stable` of 478's real commit `fb07bc29` == patch-id of `ff613b31` (both `01e22434...`). Patch identical. 478 net diff vs its merge-base `cd3b7690` is the same 3 files / 192 insertions. 478 head `079e1b7d` is 2 merge commits on top of the real chain (log shows merges + other lane commits below), matching the PR text.
- Diff scope: tools/tests/_sharding.py, conftest.py, test_sharding_c1192.py only (+192/-0).
- Tests on exact head (Windows, py3.14, pytest 9.1.1): 26 pass / 3 fail. The 3 fails are the `python -I -m pytest` child tests (user-site pytest dropped by -I): builder's claim reproduced. With `-I` removed in a throwaway copy: 29 passed.
- Real-suite partition: collect-only of tools/tests: 3619 collected (7 collection errors here are missing PYTHONPATH modules field_core/agent_registry/etc., env, not the PR; builder's 3924 is the clean-env count, not reproduced here). Shards 1/3+2/3+3/3 = 1994+720+905 = 3619 = full. `--shard 3/2` -> usage error "needs 1 <= I <= N".
- Code read: partition by file name, greedy longest-first, deterministic tiebreaks, bad spec -> UsageError at configure; deselected (not skipped) via pytest_deselected. No defect found. Caveat (LOW): partition key is `item.path.name` (basename), so two same-named files in different dirs share a shard (still a partition, no test lost); tools/tests has no subdir test files today.

## Mutants (16, run against the 29-test file with -I removed; table counted)
| # | mutant | result |
|---|---|---|
| M1 | sort light-first | KILLED |
| M2 | ties to highest shard | SURVIVED |
| M3 | always shard 1 | KILLED |
| M4 | drop name tiebreak | KILLED |
| M5 | parse allows I=0 | KILLED |
| M6 | parse allows I=N+1 | KILLED |
| M7 | parse drops left.isdigit | SURVIVED (near-equivalent: int() still rejects most; " 1/3" would parse) |
| M8 | load never accumulated | KILLED |
| M9 | DEFAULT_WEIGHT 1.4->50 | SURVIVED |
| M10 | hook keeps other shards | KILLED |
| M11 | hook does not write items[:] | KILLED |
| M12 | hook no-op | KILLED |
| M13 | configure swallows bad spec | KILLED |
| M14 | hook index off by one | KILLED |
| M15 | pytest_deselected not reported | SURVIVED |
| M16 | shard by nodeid not file | KILLED |
Totals: 16 mutants, 12 killed, 4... recount: killed = M1,M3,M4,M5,M6,M8,M10,M11,M12,M13,M14,M16 = 12; survived = M2,M7,M9,M15 = 4; 12+4=16.
Per behaviour: partition/hook 7 mutants (all killed); balance/determinism 4 (M1,M4 killed; M2,M9 survive); parse 3 (M5,M6 killed; M7 survives, 3 < 4 mutants: only 3 distinct meaningful parse mutants available).

## Optional LOWs (new PR, head stays frozen)
1. M15: nothing asserts the shard's other items are reported "deselected" (docstring claims it). Add a `-q` summary assertion "deselected".
2. M7: add `" 1/3"` / `"1 /3"` to the bad-spec list (int() accepts whitespace and unicode digits; current code only rejects them because of isdigit — which isdigit also accepts e.g. "²"? not verified: LOW uncertainty).
3. M2/M9: which shard gets the heaviest file and the default weight are unpinned; benign (deterministic, a wrong weight only unbalances).
4. The 3 hook tests use `-I`; they fail on any host where pytest is user-site only. CI/GX10 not run by me (not verified there).

Not verified: CI/GX10 green on this head (not my role item); coverage of the 7 env collection errors.
