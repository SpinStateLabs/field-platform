# R-13 reviewer report: services/sealed-ledger store.py reader retry engine and rename retry (main 444e49b)

VERDICT: 28 mutants, 21 killed, 7 survived. The snapshot-retry engine (torn read, deadline) has only boundary and perf-level survivors; the rename retry loop's whole behaviour (retry on a transient PermissionError, then give up) is unpinned.

OBJECTIONS FIRST
1. Timing mutants (`< 0.1`, `> deadline`) are nearly equivalent on a float monotonic clock; "survived" there means little.
2. The run used three test files (172 tests, 53 s), not the full 100 s suite, so a mutant killed only by another test file is shown as a survivor here.
3. The suite runs on Linux: the Windows-only `PermissionError` paths are not exercised by anything.

ASSUMPTIONS
1. Main 444e49b; `store.py` 2,652 lines; ranges 1620-1700 (snapshot read with torn-last-line detection and deadline) and 1834-1846 (`_rename_with_retry`); tests `test_ledger_readers.py`, `test_ledger_rotation.py`, `test_ledger_c2_hardening.py` (172 passed, 2 skipped). [HIGH]

REASONING
1. Mutants: range 1620-1700 23 mutants, 19 killed, 4 survived; range 1834-1846 5 mutants, 2 killed, 3 survived. [HIGH]
2. `_rename_with_retry` (store.py:1834-1844), LOW, F-R13-1: `if attempt == self.RENAME_RETRIES: raise` forced False, forced True and `==` -> `!=` ALL survive. Forced True turns the retry loop into a single attempt (the whole point: a Windows WinError 32 held by a reader for a moment); forced False makes exhaustion end in `AssertionError("unreachable")` instead of the PermissionError. No test injects a `PermissionError` from `os.rename`. Used by the rotation path (:2067). Production hosts are Linux, so impact is on Windows dev/test hosts. [HIGH]
3. Torn last line (store.py:1641-1656), LOW, F-R13-2: `if tail.strip():` forced True survives (a whitespace-only tail would be retried until three sightings over 100 ms, then accepted: a delay, not a wrong read); the two `<` -> `<=` mutants on `torn[1] < 3 or now - torn[2] < 0.1` survive (the exact third sighting and the exact 100 ms are untested; the time one is effectively equivalent). The torn-line logic itself (>= 3 identical sightings over >= 100 ms) is otherwise pinned. [HIGH]
4. Deadline (store.py:1671) `time.monotonic() > deadline` -> `>=`: survives; equivalent in practice on a float clock. [MEDIUM]
5. Killed: torn-read retry vs raise, the closed-segment-moved/journal-changed retry, the permission-denied-at-every-attempt `LedgerUnreadable`, the busy `LedgerBusy` branch, the delay back-off (19 of 23 in range 1). [HIGH]

CONCLUSION
One LOW worth a test: inject `PermissionError` N-1 times then success, and N times (expects PermissionError, not AssertionError). The rest is boundary noise. Not done: arithmetic/argument mutants, the other 2,500 lines of store.py (suite takes 100 s per run), `witness.py`, `bundle.py`.
