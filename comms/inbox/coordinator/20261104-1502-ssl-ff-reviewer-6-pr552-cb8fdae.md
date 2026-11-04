# Reviewer ssl-ff-reviewer-6: PR 552 @cb8fdaec (claude-approver: an overflowing usage-cursor value disables posting instead of double-posting) — UNVERIFIED (cloud, no GX10)

**VERDICT: PASS WITH CONDITIONS, head cb8fdaec3ff609173dc02d9a40ff67d563789d1c.** Code PR (one line in core.py, one new test). The line fixes the case it names. Two other unparseable-cursor forms still produce the same double-post, and I measured it (objection 1).

## Objections first
1. Same failure, other inputs (MEDIUM, measured on this head). `UsageCursor.load` sets `_loaded = True` first, and only `FileNotFoundError` and `OSError` are caught around the file read, only `ValueError`, `TypeError` and now `OverflowError` around the parse. I fed `load()` nine cursor files: `1e999` (the PR's case), a huge integer, `NaN`, a string value, a list value and an empty file all end with `error = "usage cursor is corrupt"` (good). But a cursor file with invalid UTF-8 bytes raises `UnicodeDecodeError` out of `read_text`, and a deeply nested JSON file (100,000 `[`) raises `RecursionError` out of `json.loads`; both escape `load()` with `_loaded=True`, `error=None`, `data={}`. End to end, with the PR's own harness, after two ticks on each of those files: `usage posts: 1 | usage_cursor_error: None | tick_errors: 1`. So the first tick fails (the error is counted), the second tick treats the cursor as loaded and empty, and posts the session's whole history from zero: exactly the double-posting the PR docstring and test describe. A broad `except Exception` in the parse (and a catch of `UnicodeDecodeError` on the read) would close the class; I did not change anything.
2. The new test covers one value (`1e999`) in one field. Nothing pins the unreadable-file branch (M10) or a list value (M3).
3. The PR is 1 commit behind main (b963407a, PR 546); disjoint files.

## Identity (HIGH)
The one commit cb8fdaec: author and committer Don Hagell 13129187+dhagell@users.noreply.github.com.

## Method
Scratch worktree at the exact head; PYTHONPATH from the worktree; PYTHONDONTWRITEBYTECODE=1. Unmutated baselines: test_approver_usage.py 13 passed; whole claude-approver suite 316 passed. The probe above ran as a throw-away test file in the scratch tree (removed afterwards). Mutants edit real lines of core.py (each search text asserted unique); kill = test_approver_usage.py fails, else the whole suite.

## Table (10 mutants, totals counted from the table)
The except clause (M1 `OverflowError` removed, M2 `ValueError` removed, M3 `TypeError` removed, M4 error not set, M5 error text changed, M6 `self.data = {}` added, M7 error set to None): M1, M2, M4, M5, M7 killed; **M3 SURVIVED** (a list or dict value in the cursor is not tested); **M6 SURVIVED** (equivalent: `data` is already empty on that path).
Posting gate and visibility (M8 the `cursor.error` gate off, M9 `/stats` always None, M10 the unreadable-file branch sets no error): M8, M9 killed; **M10 SURVIVED** (a cursor file that cannot be read, for example a permission error, is not tested; with no error set it would double-post).
Totals: 10 mutants; 7 killed by the usage tests; 0 killed only by the suite; 3 survived (M3, M6, M10), M6 equivalent.

## Findings
- F1 MEDIUM (objection 1): catch `Exception` around the parse and `UnicodeDecodeError` on the read, set `error`, and add the two probe inputs as tests.
- F2 LOW (M3, M10): pin a list value and an unreadable file. 
- F3 (not run): `_usage_snapshot` does `int(v)` on a value that can be `inf` (api values `v >= 0` is True for `inf`); an `OverflowError` there would be a tick error, not a double post; I did not test it.

## Conditions
1. Decide on F1 (fix in this PR or a follow-up that is recorded); until then the double-post window stays open for those two inputs. 2. CI green on cb8fdaec. 3. Full GX10 16/16 on that exact head (code PR). I read no CI result and ran no GX10.
