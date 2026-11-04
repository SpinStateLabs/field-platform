# Review PR 622 @ 2aaf1c08190b97e07a2a79eaa380137dd6e44602 (lifecycle-manager: the sweep refuses an owner-less roster and reads a BOM header, S3-2) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 2aaf1c08. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. The danger is `--auto-kill-orphans` with an owner-less roster: every agent becomes an orphan and is killed. The refusal must come BEFORE any ledger note or kill, and must hold with auto-kill on. Probed (R1, R2, R4, R7); the test asserts `kill.calls == []` and `ledger.events == []`.
2. A BOM fix that strips too much (`lstrip`, `[1:]`) can eat a real first character or leading blank lines. Probed (B2, B3).
3. The CLI prints `{exc}` for a `LifecycleError`; if any other raise site of that class carries operator text, it reaches the terminal. The PR adds a boundary-echo allowlist line for this print (operator terminal, no reply leaves the host); I did not audit the other `LifecycleError` raise sites (not read).

## Facts (HIGH)
- Head fetched via refs/pull/622/head = 2aaf1c08; 3 commits (the fix, a merge of main, and an allowlist line); contains current main; author AND committer on all three: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 4 files, +138 -9: `engine.py` (BOM strip in `parse_roster_entries`; the refusal at the start of `sweep`), `cli.py` (the sweep catches `LifecycleError`, prints one line, exit 2), `tests/test_empty_roster_refusal.py` (+112, 8 cases), `tools/tests/boundary_echo_allowlist.txt` (+1).
- Baselines unmutated: new file 8 passed; whole lifecycle-manager suite 277 passed; the boundary-echo lint 61 passed on the head.

## Mutants (the new file first; a survivor then the whole suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| owner-less roster refused, also with auto-kill, same class, before any action (R1, R2, R4, R5, R6 message text, R7 blank-only roster) | 6 | 5 | 1 (R6) |
| a BOM before the header is read, nothing else eaten (B1-B4) | 4 | 3 | 1 (B3) |
| the CLI prints one line to stderr, exits 2, catches `LifecycleError` only (L1-L6) | 6 | 5 (L6 by the whole suite, not the new file) | 1 (L3) |
Totals counted from the table: 6+4+6 = 16 rows; killed 5+3+5 = 13; survived 3 (R6, B3, L3). Two first-pass edits did not anchor (a "refusal after the ledger note" idea and an ambiguous `except` edit); the second was rewritten as L6; the first is dropped and not counted.

## Survivors
- F-R622-1 LOW (R6): the refusal text is pinned only by the phrase "no owners"; the "(nothing was ledgered or killed)" claim is true by the other assertions but its wording is free.
- F-R622-2 LOW (B3): stripping a BOM followed by blanks and newlines passes; only a BOM is documented, and the extra stripping is harmless, so this is near-equivalent.
- F-R622-3 LOW (L3): printing to stdout instead of stderr passes, because the test reads `res.output` (the mixed stream); the PR's "stderr" is unpinned. Use `res.stderr` or `mix_stderr=False`.
- L6 (catching `Exception` instead of `LifecycleError`) is killed by another test in the whole suite, not by the new file.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head.
