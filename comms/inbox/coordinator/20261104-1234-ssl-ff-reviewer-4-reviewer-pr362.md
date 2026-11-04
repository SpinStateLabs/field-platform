# Reviewer report: PR 362 @ ef852435f647954ad9526611ae9e1844e9f3f8db (C-159, reviewer C-738 F-C738-1 and F-C738-2)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Tests only: 2 files, +23 lines against base acaf5f24 (4 commits incl. 1 merge of main; three of them were already on main as 2447a485, 0e1251a0, fcfb8b52, so the live delta is two new tests). Author and committer of all 4 = Don Hagell 13129187+dhagell@users.noreply.github.com; trailers Sonnet 5.5 (HIGH). `git merge-tree --write-tree origin/main pr362` clean (HIGH). No production code changed.

## Objections first
1. The two added tests pin a tuple member and a comparison operator; they can pass for the wrong reason if the test double raises something the real client never raises. I checked the first: BadStatusLine, IncompleteRead and CannotSendRequest are `http.client.HTTPException` subclasses and not `OSError` (the test asserts this itself), so they reach only the `HTTPException` half of `except (OSError, http.client.HTTPException)` (alerts.py:494).
2. Decrease witnessing of the retired counter is a design statement ("the counter only grows today"), pinned for a source that does not exist yet; if the counter source gains a reset, the test is the only thing that records the intent.
3. Merge-of-main commit inside the PR (ef852435) hides conflict resolution; main already contains three of the four commits, so the head is a very small real change.

## Verified
- Baseline on the exact head: packages/field-core/tests/test_alerts_send_survivors_c159.py + services/sealed-ledger/tests/test_operator_observer_r2.py = 67 passed (relative PYTHONPATH).
- Production lines under test: field_core/alerts.py:494 and sealed_ledger/operator_observer.py:463 (`n != previous_n`).

## Mutants (scratch worktree on the head; baseline 67 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| H1 | HTTPException dropped from the tuple | 3 failed (the 3 new cases) | yes |
| H2 | network branch not retryable | 5 failed | yes |
| H3 | network reason renamed | 5 failed | yes |
| H4 | HTTPException answered as timeout | 5 failed | yes |
| H5 | HTTPException branch reports a status | 5 failed | yes |
| O1 | decrease ignored (`!=` -> `>`) | 1 failed (the new test) | yes |
| O2 | increase ignored (`!=` -> `<`) | 2 failed | yes |
| O3 | previous value not carried | 3 failed | yes |
| O4 | startup flag always False | 2 failed | yes |
| O5 | remembered value not updated | 4 failed | yes |
| O6 | first sighting of 0 witnessed | 1 failed | yes |
| O7 | observed_from renamed | 3 failed | yes |
| O8 | failed write does not return early | 1 failed | yes |
Totals counted from the table: 13 mutants, 13 killed, 0 survived (5 on the retry-classification behaviour, 8 on the retired-counter witness). H1 and O1 are killed only by this PR's new tests (3 and 1 failures), so the PR does add the pins it claims. No survivor to run against the suite. I did not run the other suites.

## Findings
- None blocking. F-C159-1 LOW: objection 3, nothing to fix; the head is smaller than its commit list.

## Verdict: PASS on ef852435f647954ad9526611ae9e1844e9f3f8db
Head frozen. Merge is clean against current main (base acaf5f24 is old). CI green and GX10 16/16 on this exact head rebased on current main per the coordinator procedure. Not run by me: CI, GX10.
