# Review PR 750 @ 6bdbb4c984bd57b6b80af4d92aa24629faf55124 — sealed-ledger POST /export bad out_dir and no server path (S7-25)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one MEDIUM, two LOW)** on head 6bdbb4c9.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: api.py +26/-4, docs/ENVIRONMENT.md 4 anchor lines, boundary_echo_allowlist.txt (export api-reply 3 to 2), one new test file (13 collected cases, armed and unarmed).
- `tools/environment_anchors.py --check` on this head: 0 wrong anchor rows. Allowlist count 2 matches the lint.

## Mutants. Baselines unmutated: new file 13 passed; whole sealed-ledger suite 816 passed, 5 skipped; tools checks (boundary lint, anchors, environment doc) 159 passed.
| # | Mutant | Result |
|---|---|---|
| M1 | drop the route check | KILLED |
| M2 | `>=` bound | KILLED |
| M3 | bound off by one (up) | KILLED |
| M4 | drop NUL check | KILLED |
| M5 | drop the encode (lone surrogate) check | KILLED |
| M7 | OSError detail is `str(exc)` | KILLED |
| M8 | OSError log removed | KILLED |
| M9 | OSError log carries `str(exc)` | KILLED |
| M10 | ValueError branch removed | KILLED |
| M11 | ValueError detail is `str(exc)` | KILLED |
| M12 | ValueError log removed | SURVIVED (full suite 816 passed) |
| M12b | ValueError log carries `str(exc)` | SURVIVED (full suite 816 passed) |
| M13 | OSError status 503 | KILLED |
| M13b | ValueError status 502 | KILLED |
| M14 | 422 text changed | KILLED |
| M15 | 422 echoes the value | KILLED |
| M17 | `MAX_OUT_DIR` = 8192 | SURVIVED (full suite 816 passed) |
| M18 | check only when armed | KILLED |
| A1 | allowlist count 3 | KILLED |
| A2 | allowlist count 1 | KILLED |
| A3 | ENVIRONMENT.md anchor reverted to 464 | KILLED |
| A4 | ENVIRONMENT.md anchor 54 to 53 | KILLED |

Totals counted from the table: 22 valid rows, 19 killed, 3 survivors. M6 (`out_dir` guard form) is equivalent (`_bad_out_dir("")` is False) and was not run.

## Findings
1. MEDIUM (M12b): the ValueError branch's no-echo claim is pinned for the response body only. The log line could carry `str(exc)` (the stored timestamp text) and the suite passes. The OSError branch pins its log (M9 killed); the ValueError branch should assert the same with the existing `SECRET-STORED-TS-VALUE`.
2. LOW (M12): the ValueError log line is untested; only the OSError log is asserted.
3. LOW (M17): the bound in the 422 text says 4096, but tests derive the limit from `MAX_OUT_DIR`, so changing the constant passes. Pin 4096 literally once.
4. The lone-surrogate guard is tested only on the helper (HTTP cannot carry one); stated in the test, accepted.
