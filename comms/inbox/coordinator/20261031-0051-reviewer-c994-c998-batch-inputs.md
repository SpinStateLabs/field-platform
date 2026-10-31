VERDICT: INFORMATION on main acaf5f2 (batch inputs for cards C-994 to C-998; no code verdict)

Reviewer Lane 15, cloud-reviewer. UNVERIFIED: no GX10, CI as read from the Actions API, not the logs.

## Objections first
1. The "newest verdict" column is a MATCH BY FILE NAME AND FIRST LINE across the comms reports, not a read of each report; it can attach a report that merely mentions a PR number, and the "[HEAD MOVED]" flag compares the verdict's head with the current head. Treat it as a pointer, not a fact; the recommendation column is mine and uses the reports I wrote or read this session (HIGH on the limit).
2. CI column: from the newest 100 pull-request workflow runs (616 exist); PRs missing from that page show "n/a". "queued" means the run for the current head has not started. For three PRs the current head is newer than any run listed (379, 381, 382 moved after those runs) (HIGH).
3. Newest GX10 verdict (card C-997 asks for GX10, not cloud): I cannot tell from the repository which reports were GX10 runs; the column is not filtered (not verified).
4. Heads moved after my own reports: PR 379 now f958cab (was a020c33), PR 381 now 8c781bb (was f083ed2), PR 382 now 0dde283 (was 5be16e6), PR 348 now b8cf092, PR 388 now 5933066, PR 369 now a469a60. Anything I wrote about 379, 381 and 382 applies to their previous heads only (HIGH, git).
5. Merge test: git merge-tree of each current head against main acaf5f2; textual conflicts only.

## C-994 docs group
| PR | head | CI on head | newest verdict by name (head) | merge vs main | recommendation |
|---|---|---|---|---|---|
| 337 | 72e8fae | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on 3b28331 (20261104) [HEAD MOVED] | clean | docs-only; CI not seen; add to batch after a CI check |
| 338 | f052a0e | n/a (not in newest 100 runs) | none found by name | clean | docs plus a comment line in topology_lint; CI not seen; needs 342 for IMPLEMENTATION.md overlap order |
| 340 | 25ffdc1 | completed/success | PASS WITH CONDITIONS on bde88a2 (20261104) [HEAD MOVED] | clean | BATCH: reviewed on this head (C-910, C-964 PASS) |
| 341 | 67fefb5 | completed/success | PASS WITH CONDITIONS on b6f9b61 (20261104) [HEAD MOVED] | clean | BATCH: reviewed on this head (C-910 PASS) |
| 363 | 02d1159 | in_progress | PASS WITH CONDITIONS on 3b28331 (20261104) [HEAD MOVED] | clean | CI running on the head; wait |
| 377 | dfceabc | completed/success | PASS WITH CONDITIONS on dfceabc (20261030) | clean | BATCH: CI green; C-875 review on dfceabc |
| 378 | 1519000 | in_progress | PASS WITH CONDITIONS on 6727f5b (20261105) [HEAD MOVED] | clean | CI running; wait |
| 379 | f958cab | queued | PASS WITH CONDITIONS on a020c33 (20261031) [HEAD MOVED] | clean | HEAD MOVED to f958cab after my C-966/C-970 (a020c33): re-review; CI queued |
| 382 | 0dde283 | queued | PASS WITH CONDITIONS on 36c0d55 (20261031) [HEAD MOVED] | clean | HEAD MOVED to 0dde283 after my C-967 (5be16e6): re-review; CI queued |
| 392 | 36c0d55 | queued | PASS WITH CONDITIONS on 36c0d55 (20261031) | clean | CI queued; reviewed on this head (C-989) |

## C-995 tests group A
| PR | head | CI on head | newest verdict by name (head) | merge vs main | recommendation |
|---|---|---|---|---|---|
| 343 | e531734 | queued | PASS WITH CONDITIONS on 1f93620 (20261104) [HEAD MOVED] | clean | reviewed (C-979, C-935); CI queued on e531734 |
| 355 | 640e1bd | completed/success | PASS WITH CONDITIONS on 191affb (20261104) [HEAD MOVED] | clean | CI green; reviewed on this head (C-962); open item is a design decision, not a blocker for a tests-only batch |
| 358 | 07bd6d6 | completed/success | PASS WITH CONDITIONS on d5d4fc6 (20261104) [HEAD MOVED] | clean | BATCH: CI green; PASS on this head (C-43, C-980) |
| 360 | c5fddb5 | completed/success | PASS WITH CONDITIONS on 3aacd5a (20261104) [HEAD MOVED] | clean | BATCH: CI green; reviewed on this head (C-963) |
| 361 | 7525a93 | completed/success | PASS on 5a58ee8 (20261104) [HEAD MOVED] | clean | BATCH: CI green; PASS (C-43) |
| 362 | b468f79 | completed/success | PASS WITH CONDITIONS on 5777030 (20261105) [HEAD MOVED] | CONFLICT test_alerts_send_survivors_c159.py, test_operator_observer_r2.py | CONFLICTS with main (content landed in batch BY): rebase or close |
| 365 | d570c31 | completed/success | PASS WITH CONDITIONS on 39303a9 (20261105) [HEAD MOVED] | clean | CI green on the head; I did not re-review it today |
| 366 | 3436007 | completed/success | PASS WITH CONDITIONS on 82d56b2 (20261104) [HEAD MOVED] | clean | BATCH: CI green; reviewed on this head (C-986) |
| 367 | 46bc0d9 | completed/success | PASS WITH CONDITIONS on e2ce179 (20261104) [HEAD MOVED] | clean | CI green; I did not re-review it today |

## C-996 tests group B
| PR | head | CI on head | newest verdict by name (head) | merge vs main | recommendation |
|---|---|---|---|---|---|
| 370 | 1381b56 | completed/success | PASS WITH CONDITIONS on 112cf16 (20261030) [HEAD MOVED] | CONFLICT compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | rebase onto main first |
| 385 | 112cf16 | completed/success | PASS WITH CONDITIONS on fae8cc0 (20261031) [HEAD MOVED] | CONFLICT compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | rebase onto main first |
| 387 | d4902a0 | completed/success | PASS WITH CONDITIONS on d4902a0 (20261031) | CONFLICT compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | rebase onto main first |
| 388 | 5933066 | queued | PASS on 5933066 (20261031) | clean | CI queued; PASS on this head (C-991) |
| 391 | fae8cc0 | completed/success | PASS WITH CONDITIONS on d4902a0 (20261031) [HEAD MOVED] | CONFLICT compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | rebase onto main first |

## C-997 production group
| PR | head | CI on head | newest verdict by name (head) | merge vs main | recommendation |
|---|---|---|---|---|---|
| 322 | 1ce17e6 | in_progress | PASS WITH CONDITIONS on 6ac0f8e (20261105) [HEAD MOVED] | clean | CI in progress on the head; PASS on this head (C-993) |
| 349 | ba35c14 | completed/success | PASS WITH CONDITIONS on 50c87b9 (20261104) [HEAD MOVED] | clean | BATCH: CI green; reviewed on this head (C-908) |
| 352 | 6f30657 | completed/success | PASS WITH CONDITIONS on c28167c (20261105) [HEAD MOVED] | clean | CI green; one open item: a commit authored as 'Claude' (squash or fix) |
| 369 | a469a60 | queued | PASS WITH CONDITIONS on 1eb21c7 (20261106) [HEAD MOVED] | clean | CI queued on a469a60; reviewed on this head (C-992) |
| 371 | 8eb5c87 | completed/success | FAIL on 8eb5c87 (20261030) | clean | FAIL verdict on this head (agent-registry re-audit); rework |
| 372 | 1b8f9e3 | completed/success | PASS WITH CONDITIONS on 1b8f9e3 (20261030) | clean | verdict PASS WITH CONDITIONS on this head; CI green |
| 373 | 8c3cfb5 | completed/success | PASS WITH CONDITIONS on 8c3cfb5 (20261105) | clean | CI green; verdict on this head per name match; not re-read today |
| 374 | b97d35f | completed/success | PASS WITH CONDITIONS on 1eb21c7 (20261106) [HEAD MOVED] | clean | CI green; reviewed on this head (C-983) |
| 375 | 4ff09c7 | completed/success | PASS WITH CONDITIONS on 4ff09c7 (20261031) | clean | CI green; reviewed on this head (C-984) |
| 383 | defb7ea | completed/success | PASS WITH CONDITIONS on f083ed2 (20261031) [HEAD MOVED] | clean | CI green; reviewed on this head (C-985); rebase for ENVIRONMENT.md conflict with 352/381 |

## C-998 MCP and misc
| PR | head | CI on head | newest verdict by name (head) | merge vs main | recommendation |
|---|---|---|---|---|---|
| 368 | 1f7f61f | completed/success | PASS WITH CONDITIONS on 7551327 (20261105) [HEAD MOVED] | clean | merge first of the MCP stack; blocked on PR 356's host predicate (corpus), see C-1000 |
| 380 | e17ea86 | completed/success | PASS WITH CONDITIONS on 7551327 (20261105) [HEAD MOVED] | clean | matches the attest ruling on record; Don to confirm (C-947) |
| 384 | ca41545 | completed/success | PASS WITH CONDITIONS on ca41545 (20261031) | clean | attest tool conflicts with the ruling on record; close or trim (C-947) |
| 57 | 30ac1e1 | n/a (not in newest 100 runs) | PASS WITH BLOCKING CONDITION on 11c55c7 (20261102) [HEAD MOVED] | clean | HEAD MOVED to 30ac1e1 since the last verdict on 11c55c7; re-review needed |
| 297 | 3bb2510 | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on 3bb2510 (20261031) | clean | docs; CI red on an old head (unexplained intermittent test, C-974); rebase and re-run |
| 305 | b484e7d | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on fc8b363 (20261031) [HEAD MOVED] | CONFLICT ROADMAP.md | close as duplicate of 308 (conflicts with main in ROADMAP.md) |
| 308 | fc8b363 | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on fc8b363 (20261031) | clean | merge instead of 305 after the figure and estate-state fixes (C-972) |
| 316 | 6ae698f | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on 6ae698f (20261031) | clean | merge; one live Caddy header check outstanding (C-973) |
| 317 | 9cc5221 | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on 6ae698f (20261031) [HEAD MOVED] | clean | merge (C-865, C-973) |
| 331 | 4014720 | completed/failure | PASS WITH CONDITIONS on 1a45db0 (20261104) [HEAD MOVED] | clean | CI RED on the head (4014720); rework |
| 333 | f34d092 | completed/success | PASS WITH CONDITIONS on 39f8636 (20261104) [HEAD MOVED] | clean | CI green; verdict not re-read today |
| 334 | 8bea8c4 | n/a (not in newest 100 runs) | none found by name | clean | no CI data and no verdict found by name; needs a review |
| 335 | fc73f64 | n/a (not in newest 100 runs) | PASS WITH CONDITIONS on 2e00c73 (20261104) [HEAD MOVED] | clean | docs; no CI data; verdict on an older head by name match |
| 336 | 08463bd | completed/success | PASS WITH CONDITIONS on fe6c2be (20261104) [HEAD MOVED] | clean | CI green; conflicts only in ENVIRONMENT.md with others |
| 356 | 3361e01 | completed/success | PASS WITH CONDITIONS on a9be069 (20261105) [HEAD MOVED] | clean | CI green; see C-999 |

## Lists
- Docs-only batch candidates (clean, CI green, reviewed on the current head): 340, 341, 377. Wait for CI or re-review: 337, 338, 363, 378, 379, 382, 392.
- Tests-only batch A candidates: 355, 358, 360, 361, 366 (CI green, reviewed on current head, clean); 365 and 367 (CI green, not re-reviewed by me today); 343 once CI runs; 362 needs a rebase or closure.
- Tests B: none can merge as they stand; rebase 370, 385, 387, 391 onto main (C-976), then 370, 385, 387, 391 in order; 388 is clean once CI runs.
- Production: 349 and 374, 375, 383, 372, 373, 352 are clean with green CI; 369 and 322 await CI on their heads; 371 failed review. field_core authn files: 369 touches authn.py, 374 operator_health.py, 375 operator_auth.py, 383 operator_auth.py and startup.py: no file is shared except operator_auth.py between 375 and 383 (different hunks, clean pairwise); order is free, with the equality check of the internal secret against the read key added by whichever of 369 and 374 lands second. ENVIRONMENT.md conflicts: 383 with 352 and 381; do those one at a time.
- MCP: 368 first, only after 356; exactly one of 380 or 384 after Don's attest ruling.
- Misc: close 305 (duplicate of 308); rework 331 (CI red); rework 371.

Not verified: CI logs, GX10, whether the by-name verdict matches in each case.
