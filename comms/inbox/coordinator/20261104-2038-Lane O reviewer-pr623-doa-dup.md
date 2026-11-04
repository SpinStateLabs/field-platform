# LANE O review: PR 623 (delegation-authority DOA roster duplicate grantor + finite spend, S3-3) @ 59907bca

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head 59907bca = code+test commit 091242c6 plus a merge of main. Source change: doa.py +13/-2, tests +44. Both commits Don Hagell numeric noreply. Merge with origin/main is clean (git merge-tree).

Objections first: (1) the duplicate check keys on exact strings, so " Don" and "Don" are two grantors; the test pins only the case difference, not whitespace. (2) The refusal fires for an inactive duplicate too; no test has an inactive row, so that choice is unpinned. (3) `allow_inf_nan=False` makes the old `ge=0` partly redundant, which hides that a finite negative spend and an omitted-key default are not pinned by any test.

Baseline (unmutated): new file 7 passed in the file's parametrised set; delegation-authority suite 263 passed.

| Behaviour | Mutants | Killed (file) | Killed (older tests only) | Survived |
|---|---|---|---|---|
| B1 duplicate grantor refused | 6 | 3 | 0 | 3 |
| B2 exact string, no case folding | 4 | 3 | 0 | 1 |
| B3 error names the grantor | 4 | 2 | 0 | 2 |
| B4 non-finite spend refused | 4 | 2 | 0 | 2 |
| B5 finite and null spend still load | 4 | 2 | 1 | 1 |
| Total | 22 | 12 | 1 | 9 |

Totals counted from the table: 22 = 12+1+9 (no invalid, no noapply).

Survivors, 9 = 5 real gaps + 4 equivalent:
Real gaps:
- B1 `if row.grantor in seen and row.active`: an inactive duplicate is not pinned (every test row is active).
- B1 `if row.grantor in list(seen)[1:]`: a plain two-row duplicate is not pinned; the 3-row test only survives on set order, so this mutant's result depends on PYTHONHASHSEED (flaky survivor). Add a two-row duplicate.
- B2 `seen.add(row.grantor.strip())`: whitespace near-miss not pinned (exact-string claim covers case only).
- B4 dropping `ge=0` while keeping `allow_inf_nan=False`: a finite negative max_spend_usd is not pinned (pre-existing rule, not the PR's claim).
- B5 `default=0`: the omitted-key default is not pinned; `_row` always writes `max_spend_usd: null`.
Equivalent:
- B1 added a no-op method (control, no behaviour change).
- B3 message reworded to `duplicate <grantor!r>`: still names the grantor.
- B3 `TypeError` instead of `ValueError`: indistinguishable at the `load_roster` boundary (it still raises DoaRosterError); not pinned at the `DoaRoster` level.
- B4 `le=1e308`: differs only for finite values above 1e308.

Conditions: add a two-row duplicate test, an inactive-duplicate test, a whitespace near-miss test, a negative finite spend test, and an omitted-key spend test. Confidence: HIGH on counts, MEDIUM on gap/equivalence classes. Token/cost: I do not know.
