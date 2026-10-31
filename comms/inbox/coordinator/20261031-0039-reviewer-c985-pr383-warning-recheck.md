VERDICT: PASS WITH CONDITIONS on defb7eaf5c705a820471b1c8904d1f3c4d44d167

Reviewer Lane 15, cloud-reviewer, C-985, PR 383 at defb7ea. Same head and findings as my C-907 and C-948 (re-fetched, unchanged). UNVERIFIED: no GX10, CI not read.

## Objections first
1. Duplicate of C-907 and C-948; both stand (HIGH). Lane 4's C-942 (C-939/C-940/C-942 report, 20261107-0300) is a separate read of the same head; I did not depend on it.
2. "Appears once" means once per service name per process, not once per start; several worker processes each print one line (not tested under uvicorn workers) (MEDIUM).

## The four checks
- Names the setting only, never a value: markers as values of the four non-secret settings, and as the secret, never reached stderr in any of the 14 services (HIGH, run, C-907). The old echo of a mistyped operator mode is now fixed text (operator_auth.py:269-270).
- Every service covered: 14 of 14 call warn_open (sites at file:line in C-948).
- Once: 3 create_app calls of one service gave 1 line; a second service in the same process gave its own line (C-948).
- Conflicts: merge-tree with 369, 374, 375 and main: 0. With PR 352 and PR 381 it conflicts in docs/ENVIRONMENT.md only (rebase item).

## Conditions
As C-907: rebase against 352 and 381 and re-run test_environment_doc; log-only decision (Don) and multi-worker behaviour are non-blocking.

Not verified: CI, GX10, uvicorn workers.
