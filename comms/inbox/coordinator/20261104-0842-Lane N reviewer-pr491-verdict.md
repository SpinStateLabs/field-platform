# Reviewer: PR 491 (scout P-10) field-core: verify-chain reports invalid UTF-8 as TAMPERED, exit 1, no traceback

**Verdict: PASS WITH CONDITIONS on head `a86035c1ec681f0cfd68682cb4cc846a4549f2c1`.** Head unchanged at start and end (git ls-remote); base is current main cd3b7690 (contained); 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): `field_core/cli.py` `verify_chain_cmd` (+8/-2): reads `jsonl.read_bytes()`, decodes UTF-8, on `UnicodeDecodeError` prints `TAMPERED — file is not valid UTF-8 at byte {exc.start}` and exits 1; the lines are `io.StringIO(text, newline=None).readlines()`; new `test_verify_chain_cli_decode.py` (5 tests).

## Objections first
1. The change swaps the line reader: `open(encoding="utf-8").readlines()` (universal newlines) became `StringIO(..., newline=None).readlines()`. A different splitter would change what "a line" is for every chain file; I probed it (below) and the PR's new tests do NOT pin it.
2. An error message built from the exception (`{exc}`) would print the offending byte value (`0xff`): the new test only forbids the backslash form `\xff` and the word `SECRETxx` placed at the end of the file.
3. `read_bytes()` loads the whole file at once, as `readlines()` did; no new memory risk (both read everything).
4. A directory path still exits 2 with the existing message (probed).

## Measured (GX10 ~/ff-work/wt-ln491, relative PYTHONPATH, own venv with typer, python -B)
New file 5 passed. field-core suite: PR 1550 passed, 1 skipped; main cd3b7690 1545 passed, 1 skipped (+5, no count down). Probe on the PR head (made-up chains): LF, CRLF and CR chains verify OK (exit 0); a UTF-8 BOM file is TAMPERED (line 1 unparseable, exit 1); an empty file is OK over 0 events (as before, not a change); a directory exits 2. CI when read: see Conditions. 16-suite not run by me.

## Mutants (26 rows; the new file and the existing `test_verify_chain_cli_paths.py` run together; source restored, worktree clean). One batch of my rows first came out NOMATCH because the dash in my anchor was mangled; I re-ran those with an escaped anchor and they are killed.
| Behaviour | Killed | Survived |
|---|---|---|
| V1 invalid UTF-8 is TAMPERED, exit 1, no traceback | 6 | 1 (equivalent: `except ValueError` is the superclass) |
| V2 the offset is the byte offset in the FILE (`exc.start`) | 5 | 0 |
| V3 the message never repeats the bytes | 2 | 3 (gaps: `{exc}` prints `0xff`; `raw[:16]` prints the file head; `{exc.reason}` is a fixed phrase, neutral) |
| V4 a valid non-ASCII chain still verifies | 3 | 1 (equivalent: dropping the trailing newline byte still verifies after `strip`) |
| V6 the lines are the same universal-newline lines | 0 | 5 (gap: no test with a CRLF or CR chain) |
Totals counted from the table: killed 6+5+2+3+0 = 16; survived 1+0+3+1+5 = 10; 26 rows. Of the 10 survivors, 3 are equivalent or neutral and 7 are real unpinned detail (V3 x2, V6 x5). V3 and V6 are below the 4-kill bar.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (value read with the verdict command).
- C2: GX10 16-suite 16/16 on a head containing main (the PR body says cloud, UNVERIFIED).

## Findings (non-blocking; new PR only)
- F-491-1 LOW-MEDIUM: pin the line splitter: one valid chain written with CRLF and one with a lone CR must verify exit 0 (V6; the behaviour is right today, it is unpinned).
- F-491-2 LOW: assert the output does not contain `0xff` or the first bytes of the file (V3).
- F-491-3 INFO: an empty file verifies as "intact over 0 events"; pre-existing, unchanged by this PR.
