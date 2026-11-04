# Review PR 694 @ 1d1fcce08bb8fb1eb4c36bbd61b36956a1c30660 (crosswalk: StaleStore.clear holds the named-human rule; flag text one line, S5-18) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 1d1fcce0. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head rebased on current main still required.

## Objections first
1. `clear` is the act that lifts a regulatory stale flag; it records WHO reviewed. The old rule accepted any non-blank string, including one with a line break that could forge a `reviewed_by:` line downstream. The new rule copies the signer's rule (control, format, line-break categories, length, a letter or digit). Probed per category and per limit.
2. `mark` now REWRITES the flag's reason and version (one line, bounded) instead of storing them verbatim. A reason that was meaningful with line breaks (a multi-line detection note) loses its layout; the regwatch scheduler's own reason (a URL and hashes) must survive unchanged: pinned (the legitimate-reason test; L11).
3. The new constants (200, 2000, 100) are imported by the tests, so the numbers themselves are not pinned (R11, L4, L5 survive).

## Facts (HIGH)
- Head fetched via refs/pull/694/head = 1d1fcce0; 1 commit; four commits behind current main (no overlap); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +139 -6: `staleness.py` (`_named_reviewer`, `_one_line`, the three limits; used in `clear` and `apply_mark`), `tests/test_reviewed_by_named_human.py` (+101, 30 cases).
- A trial merge of this head with PR 610 (which edits the same file's `_load`) is clean (`git merge-tree`); with current main also clean.
- Baselines unmutated: new file 30 passed; whole crosswalk suite 399 passed, 5 skipped.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| `clear` refuses a bad name: rule removed, non-text, blank, over the limit, control/format/line categories, no letter or digit, stored stripped (R1-R4, R6-R8) | 7 | 7 | 0 |
| messages never repeat the name: category message (R9) and length message (R10) | 2 | 1 (R9) | 1 (R10) |
| limit measured on the stripped name (R5) and the constant 200 (R11) | 2 | 0 | 2 |
| each of the four categories is refused: Cc, Cf, Zl, Zp (C1-C4) | 4 | 4 | 0 |
| the flag text: reason and version made one line, `None` stays `None`, controls become spaces, whitespace collapsed, ellipsis, cut position (L1-L3, L6-L9, L11) | 8 | 8 | 0 |
| the limits 2000 and 100 (L4, L5) and the exact-limit boundary (L10) | 3 | 0 | 3 |
Totals counted from the table: 7+2+2+4+8+3 = 26 rows; killed 7+1+0+4+8+0 = 20; survived 6 (R5, R10, R11, L4, L5, L10).

## Survivors (each also survives the whole suite)
- F-R694-1 LOW-MEDIUM (L4, L5, L10, R11): the numbers 2000, 100 and 200 and the "exactly at the limit stays unchanged" boundary are not pinned; the tests import the constants and test at 5000 and 500. A change of a limit goes unnoticed.
- F-R694-2 LOW (R5): a 200-character name with padding spaces is refused under the mutant but accepted by the real code; the stripped length is the one measured, correctly, but the case is untested.
- F-R694-3 LOW (R10): the length-refusal message repeating the name is unpinned (only the category message is).

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
