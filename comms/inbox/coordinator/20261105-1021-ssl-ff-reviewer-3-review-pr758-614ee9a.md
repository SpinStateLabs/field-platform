# Review PR 758 @ 614ee9a773ffbea7f27eb85ffa37975efebef295 — force-gateway governor 200 with a non-object body counts governor_error (S7-31)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS** on head 614ee9a7 (one LOW note).

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: api.py +9/-3, docs/ENVIRONMENT.md 8 anchor lines shifted by 6, one new test file (7 collected cases).
- `tools/environment_anchors.py --check` on this head: 0 wrong anchor rows.

## Mutants. Baselines unmutated: new file 7 passed; whole force-gateway suite 455 passed; tools doc/anchor tests 98 passed.
| # | Mutant | Result |
|---|---|---|
| M1 | revert to the unguarded `resp.json().get(...)` | KILLED |
| M2 | except branch counts reason "error" | KILLED |
| M3 | except branch returns without counting | KILLED |
| M4 | except branch re-raises | KILLED |
| M5 | `resp.status_code` instead of `getattr` | KILLED |
| M6 | missing status defaults to 200 | KILLED |
| M7 | 404 test inverted | KILLED |
| M8 | status 201 accepted | SURVIVED (full suite 455 passed) |
| M10 | `except ValueError` only | KILLED |
| M11 | `except AttributeError` only | KILLED |
| M12 | `.get` moved outside the try | KILLED |
| M15 | except branch falls through to the judge | KILLED |
| A1 | ENVIRONMENT.md anchor 812 reverted to 806 | KILLED |
| A2 | ENVIRONMENT.md anchor 803 reverted to 797 | KILLED |

Totals counted from the table: 14 valid rows, 13 killed, 1 survivor. 0 equivalent. M8's first anchor matched 4 sites; it was re-run on a unique anchor (table shows the re-run). M9 and M13 to M14 from the plan were not written; numbering gaps are not rows.

## Findings
1. LOW (M8): `status != 200` has no test for another success code such as 201. The governor `/status` returns 200 only; treating 201 as success would be harmless. Not a claim of the PR.
2. The five non-object shapes (non-JSON, list, string, null, number) and a response without `status_code` are each pinned; fail-open (proxied call stays 200) and no bypass entry are asserted.
