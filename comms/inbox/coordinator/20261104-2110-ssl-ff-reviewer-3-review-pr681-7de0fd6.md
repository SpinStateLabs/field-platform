# Review PR 681 @ 7de0fd6380fad33fdd92f44d093eaceda806ebbf (field-core alerts: the patterns end in \Z not $; a NUL in alert-topic-init --out is exit 2, S5-5) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 7de0fd63. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head rebased on current main still required.

## Objections first
1. The risk is a field that reaches the alert body line by line (`'prod\n'` passing as an estate). All five anchored patterns were changed; I checked that no other `$`-anchored pattern is left in `alerts.py` (grep of the head: the remaining `re.compile` calls are unanchored search patterns for content checks).
2. `--out` changed from `Path` to `str` so click does not stat a NUL path; the message now prints `{out}` (operator-supplied text) in the one error line, which is the operator's own terminal.
3. The test file also adds `content_problem` verdict coverage, beyond the PR title.

## Facts (HIGH)
- Head fetched via refs/pull/681/head = 7de0fd63; 1 commit; four commits behind current main (no overlap with these three files); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 3 files, +98 -8: `field_core/alerts.py` (five patterns end in `\Z`), `field_core/cli.py` (`--out` is a `str`; `(OSError, ValueError)` handler), `tests/test_alerts_fullmatch.py` (+86, 21 cases).
- Baselines unmutated: new file 21 passed; whole field-core suite 1565 passed, 2 skipped.

## Mutants (the new file first; a survivor then the whole suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| each of the five patterns refuses a trailing newline: topic, token, estate, subject, detail back to `$` (P1-P5) | 5 | 5 | 0 |
| the character classes and lengths: detail widened to a newline (P7), estate allows a space (P8), topic length 65 (P6) | 3 | 1 (P7) | 2 (P6, P8) |
| `alert-topic-init`: a NUL is exit 2 with one line and the class name only, other refusals unchanged (L1-L4, L6 force ignored, L5 `Path(out)` dropped) | 6 | 4 (L1-L4) | 2 (L5, L6) |
Totals counted from the table: 5+3+6 = 14 rows; killed 5+1+4 = 10; survived 4 (P6, P8, L5, L6).

## Survivors
- P6 (topic length 65) and L6 (`--force` ignored) are killed by OTHER tests in the whole suite, not by this file.
- F-R681-1 LOW (P8): the estate class allowing a space is unpinned (the PR is about the trailing newline; the class itself is older).
- L5 EQUIVALENT: `write_topic_file` accepts a `str` as well, so passing `out` unconverted behaves the same.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
