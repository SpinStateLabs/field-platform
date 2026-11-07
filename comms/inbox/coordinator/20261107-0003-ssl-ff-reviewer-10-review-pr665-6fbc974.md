# Review PR #665 (attestation-reporter: a bad --out and a blank, control, bidi or over-long org are named refusals; the pack is written all-or-nothing, S4-17) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `6fbc974a2ea268f4083c0a8d958cfae733d9dbb9`. This head is the follow-up to ssl-ff-reviewer-9's PASS WITH CONDITIONS on `030f5c5d` (comms/inbox/coordinator/20261106-2148-ssl-ff-reviewer-9-pr665-030f5c5-pass-with-conditions.md); its two defects (a half pack on a failed second write; a lone surrogate in `--org` crashing the CLI) are fixed in code and checked below.

## Facts (HIGH, read from the head)
- 4 commits (d4ad0c14, 3dc30026, 030f5c5d, 6fbc974a); 7 files: attestation_reporter/org.py (new, 37 lines), api.py (+5), cli.py (+47/-3), three test files (132, 103 and 131 lines), tools/tests/boundary_echo_allowlist.txt (the `_build` count 1 to 2). Nothing under .github/.
- All four commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch's merge base is `b963407a`, main is now `41afda50` (reviewer-9 found a trial merge clean at an earlier main; I did not trial-merge this head).
- The code: `checked_org` (strip, non-blank, at most 200 characters after strip, refuses Unicode categories Cc, Cf, Zl, Zp and now Cs by position with a fixed text that names a code point and position, never the value) is used by `render` (exit 2, `refused:`) and by the API's `org` override (422, no echo); `--out` is settled (mkdir) before any service is queried; and `_write_pair` writes the JSON and HTML pair: a directory at either target is refused first, both texts go to temporary names beside their targets, the two `os.replace` calls follow, and if the second fails the first file is put back (its old bytes, or removed if it did not exist); temporary files are always removed.

## Reviewer-9's defects, on this head
- Failed second write left a new JSON beside a missing or old HTML: fixed. The reproduction (a directory at `board-pack.html`) now exits 2 with no JSON and no temporary files; a failed second rename removes a new JSON or restores the old one with the old HTML; a failed temporary write changes nothing (13 new cases in test_pack_write_all_or_nothing_s4_17.py).
- Lone surrogate in `--org` crashed the CLI with an uncaught serialisation error: fixed. The `Cs` category is refused with U+DCFF and the position (no value), the CLI exits 2 with `refused:` and writes nothing. Private-use (Co) and unassigned (Cn) code points stay accepted by a recorded decision (they serialise).

## Verification (run by me, Windows 10, Python 3.14)
- The three new test files: 76 passed (4.4 s). The whole attestation-reporter suite on the head: 331 passed (18.5 min). `tools/environment_anchors.py --check`: 0 wrong anchors. `test_boundary_echo_lint_c505.py`: 61 passed.
- Mutants (mine, 11 hand mutants on cli.py and org.py, one at a time against the three files; files restored with `git checkout`, tree clean afterwards). Counted from the output: 11 RED, 0 survived. `_write_pair`: no directory pre-check; no rollback of the first file; rollback always unlinks (an old JSON lost); temporary files never cleaned; the second temporary written after the first rename; `previous` always None; rollback restores nothing and does not re-raise. `org.py`: `Cs` not refused; `Co` also refused; limit measured before strip; org stored unstripped.

## Conditions
None.

## Findings (LOW; optional, new PR only; head is frozen after this PASS)
1. File mode (code read; POSIX behaviour, not run on this Windows host): `os.replace` swaps the inode, so a `board-pack.json` or `.html` an operator had set to a restrictive mode (0600) is recreated with the umask default (for example 0644) on the next render; the old in-place `write_text` kept the existing mode. The pack carries attestation data. If that matters, `os.chmod` the temporary file to the old file's mode before the replace, or create it 0600.
2. The temporary names are fixed (`.board-pack.json.tmp`, `.board-pack.html.tmp`), so two renders into the same `--out` at the same moment can publish a JSON and an HTML from different runs; the old code had the same race. `tempfile.mkstemp` in the same directory avoids it.
3. A crash or power loss between the two renames still leaves a new JSON beside an old HTML; "all-or-nothing" holds against an `OSError`, which is what the docstring says.
4. A restore that itself fails (the second `first.write_bytes(previous)` raising) is reported as the generic refusal and leaves the first file in an unknown state; unlikely, unpinned.
5. org is now stored stripped in the signed `board-pack.json` (padding no longer survives), which the PR flags as a decision for Don (reviewer-9's objection 3).

## Not covered
CI and a GX10 16 of 16 on this head; a trial merge onto current main (base `b963407a`); POSIX file-mode behaviour (item 1); Linux.
