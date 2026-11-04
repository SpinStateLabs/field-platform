# Review PR 610 @ 5f8ed984c3c5800a32f2cd42447c9e5f235d8d94 (compliance-crosswalk: a corrupt or wrong-shaped stale-flags file) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head 5f8ed984. UNVERIFIED (cloud, no GX10). Condition 1 is the no-echo pins below.

## Objections first
1. The PR's own claim is "the message is the failure class and the file's basename: never the content, never the directory" and "a fixed text over HTTP". Those are the security claims; I attacked them first (M1-M4, A2).
2. A fail-closed rewrite must cover every entry point: seven CLI commands and the API. A single call site left on the raw `StaleStore()` would crash with a traceback (exit 1) instead of the one line with exit 2; stays closed but not as designed.
3. `StoreCorrupt` on a scheduled check returns None and logs the class (tests exist); a persistent corruption therefore never self-heals and the scheduler stays silent after the first log line: operational, not code. I did not test log volume.

## Facts (HIGH)
- Head fetched via refs/pull/610/head = 5f8ed984; 1 commit; contains origin/main 97dcfec1; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. 6 files, +276 -20: `staleness.py` (`StoreCorrupt`, shape checks), `api.py` (503 handler), `cli.py` (`_open_store`, 8 call sites), new `tests/test_staleness_corrupt_file.py` (215 lines, 14 tests), `tools/tests/boundary_echo_allowlist.txt` (+1).
- Baselines unmutated: crosswalk suite 435 passed, 5 skipped (relative `PYTHONPATH=../../packages/field-core/src:../sealed-ledger/src:src`); boundary-echo lint 61 passed on the head.

## Mutants (the whole crosswalk suite each time; files restored; worktree clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| shape checks: active, its members, history, sources, its members, last_check (S1-S7) | 7 | 6 | 1 (S1) |
| exception classes caught: OSError, ValueError, AttributeError, TypeError; corrupt never reads as empty (E1-E5) | 5 | 4 | 1 (E4) |
| message: basename not path, no exception text, class naming, no chained cause, missing file is empty (M1-M5) | 5 | 2 (M1, M5) | 3 (M2, M3, M4) |
| API: 503, handler registered, no 200, fixed text (A1-A4) | 4 | 3 | 1 (A2) |
| CLI: exit 2 and one line (L1, L2) and each call site on the guard (L3-L9, 7 sites) | 9 | 6 | 3 (L3, L7, L9) |
Totals counted from the table: 7+5+5+4+9 = 30 rows; killed 6+4+2+3+6 = 21; survived 1+1+3+1+3 = 9; anchor failures 0. (M5 also produced 95 collection errors in the run; it is a kill of the right kind: a missing file refused breaks every test.)

## Survivors
- F-R610-1 MEDIUM (M2): the message can carry the exception text (`({kind}: {exc})`) and nothing fails. A `UnicodeDecodeError` message includes the offending bytes, so the file's content could reach the caller line. Pin: a file whose bytes are non-UTF-8 and distinctive; assert the message holds neither the bytes nor any slice.
- F-R610-2 MEDIUM-LOW (A2): the 503 body can be prefixed with `str(exc)` and nothing fails; the tests check the status and a substring, not the exact fixed body. Pin the body with `==`.
- F-R610-3 LOW-MEDIUM (M4): `from exc` instead of `from None` passes; a chained cause would show the original exception in a traceback (not in the reply). No test reads `__cause__`.
- F-R610-4 LOW (M3): the "WrongShape" label is unpinned (a JSON member of the wrong type would show an exception class name instead).
- F-R610-5 LOW-MEDIUM (L3, L7, L9): the `pack`, `regwatch-check-file` and `regwatch-check --fetch` call sites are not tested against a corrupt file; each would still fail closed, with a traceback instead of the one line.
- S1 and E4 are likely EQUIVALENT (a non-dict `active` also raises AttributeError, which is caught; TypeError is reached by no input I constructed): I did not prove either; I do not know.

## Conditions
1. Pin F-R610-1, F-R610-2 and F-R610-5 (an exact-body 503, a non-UTF-8 message, three CLI commands) before this lands, or the coordinator rules them follow-ups; they guard the stated no-echo promise.
2. GX10 16/16 and CI on this head.
