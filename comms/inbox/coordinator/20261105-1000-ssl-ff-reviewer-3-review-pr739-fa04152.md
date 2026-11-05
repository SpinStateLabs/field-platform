# Review PR 739 @ fa041524b94c46d6a004a427a84aa7f8230bdb17 — agent-registry scan_service_accounts input hardening (S7-13)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one MEDIUM, two LOW)** on head fa041524.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: discover.py +9/-2, one new test file (10 collected cases across API, CLI and function).

## Mutants (discover.py `scan_service_accounts`). Baselines unmutated: new file 10 passed; whole agent-registry suite 321 passed.
| # | Mutant | Result |
|---|---|---|
| M1 | drop `check_size` | KILLED |
| M2 | drop BOM strip | KILLED |
| M3 | strip one BOM only (`[1:]`) instead of `lstrip` | SURVIVED (full suite 321 passed) |
| M4 | drop header check | KILLED |
| M5 | require both `account` and `name` | KILLED |
| M6 | accept only `account` | KILLED |
| M7 | accept only `name` | KILLED |
| M8 | header cell not stripped | KILLED |
| M9 | header cell not lowercased | KILLED |
| M10 | drop the `reader.fieldnames` guard | SURVIVED (full suite 321 passed) |
| M14 | message loses the `accounts_csv` label | KILLED |
| M15 | raise ValueError, not ScanInputError | KILLED |
| M16 | size measured after the BOM strip | SURVIVED (full suite 321 passed) |

Totals counted from the table: 13 valid rows, 10 killed, 3 survivors. 0 equivalent. A 14th script row (M17) was a no-op duplicate of M4 and is not counted. The first M2/M3 anchors matched twice and were re-run on a unique anchor; the table shows the re-run.

## Findings
1. MEDIUM (M10): a completely empty CSV (0 bytes, no header) returns `([], 0)` at this head (probed). The docstring says a missing account/name header is "never a silent 0". Removing the `reader.fieldnames` guard would turn empty input into a ScanInputError and no test notices. Either decide empty input is a 0-scan and pin it (as the header-only test does), or refuse it.
2. LOW (M3): the BOM strip uses `lstrip`, so a double BOM is also stripped (probed: scans 1 row). Tests use one BOM, so a `[1:]` rewrite passes.
3. LOW (M16): the size check runs on the raw text before the strip; a file within 3 bytes of the limit differs by order of operations. Boundary is not pinned (`BIG` is well over the limit).
