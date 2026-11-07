# Review R-PR659-4ecfa15: PR 659 (lifecycle-manager: unique temp name per persist, /findings refuses non-object state without the path, blank operator refused; S4-11)
Head reviewed: 4ecfa1583ac42c0354ebc76e6edb8888f4847ef7 (4 commits: f6afaf52 the change, 89d78b77 anchors, b61d99a8 pins, 4ecfa158 portable pins and main merged). The PR body names head f6afaf52; the head is now 4ecfa158 (I reviewed 4ecfa158). `git merge-tree` against main is clean (tree b76499f6).

## VERDICT: PASS WITH CONDITIONS (the three stated defects are fixed; the "blank operator" rule is still bypassed by invisible and control characters, reproduced)

## Checks (HIGH, run by me)
1. Identity: all 4 commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 3 files (api.py +32/-7, a new test file, ENVIRONMENT.md two rows).
2. Code read: `_persist` writes `<name>.<pid>.<thread id>.<4 random bytes hex>.tmp` with `write_text` (the umask-default mode, the PR says mkstemp would have changed it to 0600), then `os.replace`, and removes the temp on any `BaseException` before re-raising; `_load` returns only a JSON object (absent file is None; a list, string, null, bad JSON, or a directory raises); `/findings` catches `(OSError, ValueError)` and answers a fixed `lifecycle state unreadable`; `SweepRequest.operator` has `max_length=200` and an after-validator that strips and refuses blank.
3. Tests on head: test_persist_and_findings_shapes 38 passed, 1 skipped (the Linux-only stress test); `environment_anchors.py --check` 0 wrong rows. The whole lifecycle-manager suite: I stopped it at about 50% after 500 s with no failure (slow on Windows); the PR body says 302 passed.
4. Mutants on api.py, 16 run, 16 killed (counted from table).
| # | Mutant | Result |
|---|---|---|
| P1 | shared temp name restored | killed |
| P2 | pid dropped from the temp name | killed |
| P3 | thread id dropped | killed |
| P4 | random part dropped | killed |
| P5 | temp not removed on failure | killed |
| P6 | failure swallowed (no re-raise) | killed |
| P7 | cleanup only for `Exception` | killed |
| P8 | non-object check removed | killed |
| P9 | `/findings` 500 detail carries the exception | killed |
| P10 | `OSError` not caught in `/findings` | killed |
| P11 | operator not stripped | killed |
| P12 | blank operator accepted | killed |
| P13 | operator max_length 201 | killed |
| P14 | operator max_length 199 | killed |
| P15 | operator max_length removed | killed |
| P16 | operator default changed | killed |

## Conditions
### C1 (MEDIUM, confirmed by running): an operator that LOOKS blank, or carries control characters, is still accepted
Probe (lm659.py in my scratchpad; `POST /sweep` on the PR's app with fakes): refused 422: `"   "`, tab, NBSP only, ideographic space only, a 201-character value, a 200-character value with padding (the length cap runs before the strip). Accepted 200: a zero-width space (U+200B) alone, a braille blank (U+2800) alone, a hangul filler (U+3164) alone, `a\nb`, `a\x00b`, and a right-to-left override prefix (U+202E). `str.strip()` does not remove those, so the PR's stated defect ("a whitespace-only operator was accepted and written to kill reasons and ledger rows") remains for them: `config.operator` goes into the ledger payloads (engine.py:630, 660, 679) and the kill-switch call (engine.py:690). The sibling code already has one rule for this (the Cc/Cf/Zl/Zp filter used by `_inline` in lifecycle-manager and `_skipped_id`; PR 489 report).
Fix: refuse an operator whose stripped value is empty after removing every Cc, Cf, Zl, Zp and `So`/`Zs`-blank character, and refuse control and format characters anywhere in it; tests for the six values above.

### C2 (LOW): `/findings` returns any JSON OBJECT unchecked
`last_sweep.json` containing `{}` or `{"operator": 5}` is served 200 as is (probe); only non-objects are refused. This is the shape-validation class of PR 610 C2 one level down: a hand-edited or schema-drifted state file reads as a sweep result. The PR title promises only non-objects; a minimal key check (the report's required keys) would close it.

## Observations (LOW)
- Unique temp names mean a process killed between the write and the replace leaves its `*.tmp` file behind forever (before, one fixed name was overwritten next time). A startup sweep of stale `last_*.json.*.tmp` would stop accumulation. Reasoned, not run.
- The PR body's merge-order note (PR 605 and PR 498 edit the same file in other hunks) still holds; `git merge-tree` of this head against current main is clean, I did not test against 605 or 498.

## Not verified
Whole lifecycle-manager suite to completion; behaviour on Linux (the stress test is skipped here); GX10 16/16.

## Conditions to reach PASS
C1 in a new commit with tests; C2 optional; identity re-check of the new head.
