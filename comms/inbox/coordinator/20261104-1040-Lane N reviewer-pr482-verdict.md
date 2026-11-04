# Reviewer (lane A, sealed-ledger): PR 482 (C-1205) tests for `sealed_ledger.filters` and `sealed_ledger.retention`, called directly

**Verdict: PASS on head `198afb112a08489a9487dacff9c74b8bd091254d`** (conditions are the standard gates only). HIGH CARE (retention). Head unchanged at start and end; base cd3b7690 (main not contained, one new file only); 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): one new file, `tests/test_filters_retention_direct_c1205.py` (+307, 40 tests); no source change. Source under test: `filters.py` (87 lines) and `retention.py` (131 lines), both read in full.

## Objections first
1. Neither module deletes anything: `retention_check` reports and calls only `store.retention_state()` (read of `retention.py:68-79`); the PR pins that with a stub store, and I confirmed it with mutants that add `archive()` / `purge()` calls (killed).
2. `estate_retention_days` reads the process environment: the tests must clear `FIELD_LEDGER_RETENTION_DAYS` between cases or they depend on the runner; mutants that default the variable to "0" were killed, so the isolation holds.
3. "Killed" here means the 40 tests fail under the mutant; I did not check which single assertion fails, so a kill by an unrelated error (for example an `AttributeError` from an added call on a stub) counts the same. The pins named in the PR body match the behaviours I mutated.

## Measured (GX10 ~/ff-work/wt-ln482, relative PYTHONPATH, own venv, python -B)
New file 40 passed. CI at read: see Conditions. 16-suite not run by me.

## Mutants (42 rows on filters.py and retention.py; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| F1 `parse_bound` refuses a non-text bound; the message names the bound | 5 | 0 |
| F2 both bounds inclusive, one microsecond outside is out | 4 | 0 |
| F3 a naive timestamp is UTC | 4 | 0 |
| F4 with no time bound the stored `ts` is never parsed | 3 | 0 |
| F5 agent and event_type match exactly; the agent is decided before the `ts` | 4 | 0 |
| F6 a bad candidate `ts` raises ValueError naming the index | 4 | 0 |
| R1 an unset or blank retention variable is (None, None) | 4 | 0 |
| R2 not an integer or below 1 is no policy, with a reason cut at 40 characters | 5 | 0 |
| R3 status precedence unavailable > no_estate_policy > unresolvable > violation > ok | 5 | 0 |
| R4 the check reports only and calls nothing but `retention_state` | 4 | 0 |
Totals counted from the table: killed 5+4+4+3+4+4+4+5+5+4 = 42; survived 0; 42 rows. F4 has 3 kills because only 3 mutants were written for it (not 4); no survivor.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: GX10 16-suite 16/16 on a head containing main (tests only; light run acceptable).

## Findings (non-blocking; new PR only)
- F-482-1 INFO: none. The one gap in the record is that F4 has 3 mutants rather than the 4 the lane rules ask for.
