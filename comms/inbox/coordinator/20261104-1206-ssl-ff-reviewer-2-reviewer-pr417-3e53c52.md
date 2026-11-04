# Reviewer report: PR 417 @3e53c52b (ntfy alert titles pinned literally; every tag a checked emoji code, C-84, reviewer C-81)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. Tests and one runbook paragraph: packages/field-core/tests/test_alerts_ntfy.py (+45/-... ) and docs/runbooks/ntfy-alerts.md (+5/-3). No production code.

## Verdict: PASS WITH CONDITIONS (head 3e53c52b5ffb5c1d20c699586a468c1205be8448)
Conditions: C1 rebase on current main. The PR base is 4d0c3315; main 97dcfec1 renamed `alerts.reset_stats` to `alerts._reset_stats`. I built the three-way merge result (`git merge-tree` tree 98943d0f, which merges the PR and main cleanly) and ran it: test_alerts_ntfy.py 64 passed. Running the PR's own copy of the test file on top of main WITHOUT the merge gives 64 errors (fixture calls the old name), so the PR must be rebased or merged, not cherry-picked as a file. C2 GX10 16/16 on the exact rebased head; C3 CI green. No blocking finding.

## Objections first
1. The runbook now says the eight emoji codes "were each found as a row of docs.ntfy.sh/emojis on 2026-11-01". I did not re-check that page (no network read of it in this session); the codes are standard emoji short names (training data, MEDIUM). The tests pin the set, not its correctness: a code absent from ntfy renders as plain text, which is a cosmetic failure on a phone, not a safety one (HIGH, from the runbook text itself).
2. The title pin is literal, so a deliberate title change now needs a test edit in the same commit; intended (HIGH, read).
3. `CHECKED_NTFY_EMOJI_CODES <= used` forbids a checked-but-unused code; removing a class tag needs the set trimmed too (HIGH, read; the assertion is killed by G5).
4. The parametrised test pins ONE tag per class plus "field"; the other tags are pinned by the set-membership test only, so swapping a checked code for another checked code (for example `key` for `sos` in a class) is not caught: I did not write that mutant against the table, and it would pass (MEDIUM, reasoned from the test code).
5. The commit message cites reviewer mutant "S4" from C-81; I ran my own mutants and did not read the C-81 report.

## Scope and identity
2 files, 2 commits; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check` on main 97dcfec1: 0 wrong anchor rows; the PR head's base predates that tool, so I did not run it on the PR head (the file is absent there). No docs anchor rows are touched by this diff.

## Runs
Baseline (unmutated head): test_alerts_ntfy.py 64 passed. Merged tree on main: 64 passed. Mutants edit packages/field-core/src/field_core/alerts.py CLASSES one at a time; kill = test_alerts_ntfy.py fails; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| T1 | title | rotation_failed title cased differently | KILLED |
| T2 | title | rotation_overdue title cased differently | KILLED |
| T3 | title | breakglass title respelt | KILLED |
| T4 | title | stage_transition title reworded | KILLED |
| T5 | title | stage_aborted title shortened | KILLED |
| T6 | title | rotation_halted title shortened | KILLED |
| T7 | title | test title shortened | KILLED |
| P1 | priority | rotation_failed 5 to 4 | KILLED |
| P2 | priority | rotation_overdue 4 to 5 | KILLED |
| P3 | priority | breakglass_used 5 to 3 | KILLED |
| P4 | priority | stage_aborted 5 to 4 | KILLED |
| P5 | priority | test 3 to 1 | KILLED |
| G1 | tags | first tag misspelt (param-checked tag) | KILLED |
| G2 | tags | second tag misspelt (not param-checked) | KILLED |
| G3 | tags | `warning` misspelt | KILLED |
| G4 | tags | an unchecked emoji code added | KILLED |
| G5 | tags | `warning` no longer used by any class | KILLED |
| G6 | tags | `field` tag dropped | KILLED |
| G7 | tags | plain tag `test` changed | KILLED |
| G8 | tags | unchecked emoji appended | KILLED |

Counted from the table: 20 rows (title 7, priority 5, tags 8). KILLED 20, SURVIVED 0. Kill rate 100%. Per behaviour: title 7/7, priority 5/5, tags 8/8.

## Findings
- F1 LOW: objection 4, a checked-for-checked tag swap passes; pin the whole tag tuple per class if the order matters to the operator (it does not appear to).
- F2 LOW: objection 1; the doc claim is unverified by me.

## Not verified
The ntfy emoji page rows; rebase on 97dcfec1 beyond the merged-tree run; CI; GX10; the C-81 report.
