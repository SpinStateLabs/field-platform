# Reviewer report: PR 621 @2670efe0 (spend-governor: usage totals count the priced rows of a mixed priced/unpriced model, scout S3-1)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (':' separator). Financial arithmetic: I applied zero tolerance and used no figure I did not run. The head is a merge of main (b963407a, the PR base is main itself) onto the fix commit 3645f6b6; a second worklist line names 3645f6b; the code and test content are identical, so this report covers both heads and states the merge head.

## Verdict: PASS WITH CONDITIONS (head 2670efe0cd83ccee3e3d5733b1bf9fd93ad3d351)
Conditions: C1 Don rules the semantic decision the PR names itself ("decision for Don"): by_model for a mixed model now shows the priced cost with `priced: false` (before, `cost_units: null`). C2 the coordinator notes the behaviour change for spend caps: totals fed into `/status` and `/totals` can only go UP for agents whose model had a mix of priced and unpriced rows, so a cap that did not trip before may trip now (that is the fix; it is also an operational change). C3 GX10 16/16 on the exact head and CI green (main is the base, so no rebase is needed). No blocking code finding.

## Objections first
1. The fix changes a number that gates spending. An agent previously under-counted is now counted correctly and can reach BLOCK sooner; any dashboard or alert threshold that learned the old figure shifts (HIGH, reasoned from the diff and the cap test `test_the_cap_trips_on_the_priced_rows_of_a_mixed_model`).
2. The store does not enforce "an unpriced row has NULL cost": `record_usage` writes whatever `cost_units` and `priced` it is given. The API sets `priced = cost_units is not None` (spend_governor/api.py:506), so the invariant holds on every path in the repo that I read, and the new sum, which no longer filters on `priced`, depends on it. A direct store caller that writes `priced=False` with a non-null cost would now have that cost counted (HIGH, read; no test pins the invariant).
3. `by_model[].priced` keeps meaning "every row in the window was priced"; for a mixed model the pair (priced false, cost shown) is easy to misread as "this cost is unreliable" instead of "this is the priced part only". The docstring says so; the field has no separate marker (MEDIUM, design).
4. `total_cost` uses Python ints from the split-sum columns, so int64 overflow cannot occur; a test pins 2 x 2**62 (killed by T6) (HIGH, run).
5. `cost_units=r["c"] if (r["p"] or r["c"]) else None`: a mixed model whose priced rows sum to 0 shows `None`, not 0 (HIGH, read; arguably wrong but not touched by this PR and rare).

## Scope and identity
3 files: spend_governor/core.py (1 line), api.py (1 line), tests/test_usage_mixed_priced.py (new, 128). 2 commits in the PR range (the fix, then the merge of main); author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head): the new test file 12 passed; full spend-governor suite 303 passed. Mutants edit core.py and api.py one at a time; kill = the new file fails; for survivors I ran the full suite; files restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| T1 | total cost | pre-fix: rows of mixed models dropped | KILLED |
| T2 | total cost | zero-cost rows skipped | SURVIVED, EQUIVALENT (adds 0) |
| T3 | total cost | tokens summed instead of cost | KILLED |
| T4 | total cost | max instead of sum | KILLED |
| T5 | total cost | first model only | KILLED |
| T6 | total cost | int64 wrap | KILLED |
| T7 | total cost | mixed model counted only when its cost exceeds 1000 units | SURVIVED (F1) |
| T8 | priced flag | MAX(priced): a mixed model reads priced | KILLED |
| T9 | priced flag | every model reads priced | KILLED |
| T10 | total cost | tokens of mixed models dropped | KILLED |
| A1 | by_model cost | pre-fix: a mixed model shows no cost | KILLED |
| A2 | by_model cost | an only-unpriced model shows 0, not None | KILLED |
| A3 | by_model cost | `and`: a mixed model shows None | KILLED |
| A4 | by_model cost | priced always True | KILLED |
| A5 | by_model cost | cost never shown | KILLED |
| A6 | by_model cost | `r["c"] > 0` instead of `r["c"]` | SURVIVED, EQUIVALENT if cost sums cannot be negative (I did not check the validator) |
| A7 | by_model cost | None replaced by 0 | KILLED |
| S1 | callers | /status ignores token cost | KILLED |
| S2 | callers | /totals ignores token cost in cents | KILLED |
| S3 | callers | /totals reports zero token cost units | KILLED |

Counted from the table: 20 rows (total cost 7 plus tokens 1, priced flag 2, by_model cost 7, callers 3). KILLED 17, SURVIVED 3 (T2 and A6 equivalent, T7 real). Kill rate on non-equivalent rows 17 of 18 = 94%. Per behaviour: total cost 7/8 non-equivalent (T7), priced flag 2/2, by_model cost 6/6 non-equivalent, callers 3/3.

## Findings
- F1 LOW to MEDIUM (HIGH confidence, run): T7. Every mixed-model test uses priced costs of 100,000 units or more; a small priced cost beside an unpriced row (for example 500 units) is untested, and a threshold-style regression would drop it silently. Add one case with a priced cost of a few hundred units.
- F2 LOW: objection 2, pin the store-level invariant (an unpriced record carries NULL cost), or have `record_usage` refuse the mismatch.
- F3 INFO: objection 5, a mixed model whose priced rows sum to zero shows `cost_units: null`.

## Not verified
CI; GX10; the `cost_units` validator's sign rule (A6); live spend data.
