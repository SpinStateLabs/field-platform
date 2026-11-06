VERDICT: PASS on ea1e59c5c099446a6222dba4e7a1ca415bc62d06  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for reviewer-3's PASS WITH CONDITIONS on 3534e6be. Their condition 1 (the NUL traceback) is fixed and pinned; the standing GX10 and CI gate (their condition 2) stays open; two optional LOW notes go in a new PR.

R-PR685-ea1e59c, PR 685 (S5-9, sealed-ledger `ledger anchor` and `rotate --anchors` fail cleanly). Applies to this head only. This fix is a CODE change (cli.py), not tests only. The fetched pull/685/head is ea1e59c5.

OBJECTIONS FIRST
1. The `except ValueError` branch of `anchor` now ALWAYS says `--key is not a usable Ed25519 private key PEM`, even when no --key was given: the `pem is None` branch that told the two causes apart was removed on the premise that the only other ValueError was the NUL byte, which is now refused first. Any other ValueError from write_anchor with no key (for example a path holding a character the filesystem encoding cannot encode; a lone non-escapable surrogate on POSIX) would blame the key. I could not reproduce a case on this box: on Windows with PYTHONUTF8=1 a path holding "\udcff" was written (anchor exit 0, with and without a key, and `rotate --offline --anchors` also exit 0). POSIX behaviour is NOT verified. LOW (the original F-R685-2), unproven reachability.
2. After a committed rotation, only OSError from the anchor append is handled (cli.py `rotate`, `except OSError`). A ValueError there (the same class as objection 1) would be a traceback AFTER the rotation was committed, with no "rotation SUCCEEDED" line; the NUL byte, the only ValueError the PR names, is now refused before the rotation. Same unproven reachability. LOW.
3. `--anchors ""` (empty string) is not refused: `anchor` answers exit 1 `error: cannot write --anchors : PermissionError` (Path("") is the current directory), so the message works but names nothing. LOW cosmetic.
4. Surviving mutant N6 (`write_anchor` receives the str, not Path(anchors)) is equivalent: write_anchor accepts a str and all 16 tests pass with it; the type hint is the only difference. HIGH.
5. Base is b963407a, 64 commits behind main; `git merge-tree --write-tree origin/main <head>` is clean (tree id only). The PR's allowlist line for the new CLI print is present; the boundary-echo lint on the head: 61 passed, and `environment_anchors.py --check`: 0 wrong anchor rows. HIGH.

ASSUMPTIONS
A1 reviewer-3's measured NUL traceback (click stats a Path-typed option while parsing) is correct; I re-ran it as mutant N7 below. A2 `typer.Option` with str type receives the raw argv text on all platforms.

REASONING / CHECKS
1. Diff against the reviewed head (3534e6be..head), read in full: cli.py `anchor` and `rotate` take `anchors` as str; a NUL byte is refused first in `anchor` (exit 1, before the key is read) and in `rotate` (exit 2, before the rotation; text says "nothing was rotated"); `Path(anchors)` is applied at the use sites; the dead pem-is-None branch is removed. Nothing under .github/ and no other file changed except the tests (+3 cases). HIGH.
2. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core src): test_anchor_cli 16 passed; with the anchor, rotation and CLI-adjacent sealed-ledger test files (test_anchors_c573, test_bundle_rotation_event_c407, test_ledger_rotation, test_load_anchors_c468, test_verify_anchors_fail_closed_c192) 176 passed, 2 skipped, 0 failed (231 s). I did not run the whole sealed-ledger suite. HIGH.
4. Mutants on a copy of the head, test_anchor_cli.py only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| N1 | anchor NUL precheck removed | KILLED |
| N2 | anchor NUL exit code 2 | KILLED |
| N3 | rotate NUL precheck removed | KILLED |
| N4 | rotate NUL exit code 1 | KILLED |
| N5 | anchor NUL message names the key | KILLED |
| N6 | write_anchor receives the str instead of Path(anchors) | SURVIVED (equivalent, objection 4) |
| N7 | anchors typed Path again (the reviewed traceback returns) | KILLED |
| N8 | key-read refusal carries the exception text | KILLED |
| N9 | garbage-key ValueError exit code 1 | KILLED |
| N10 | OSError exit code 2 | KILLED |
| N11 | rotate: anchor failure prints no result first | KILLED |
| N12 | rotate: anchor failure exits 0 | KILLED |
| N13 | rotate: failure message loses "SUCCEEDED" | KILLED |
| N14 | LedgerCorrupt exit code 2 | KILLED |
| N15 | UnicodeDecodeError on key read uncaught | KILLED |

Counted from the table: 15 run, 14 KILLED, 1 SURVIVED (equivalent), 0 NOT APPLIED (N1 and N3 needed a second edit of my script after a quoting slip; the counted results are from the corrected run). reviewer-3's own mutant rows (W4 and T5, killed only elsewhere) were not repeated. HIGH on the counts.

CONDITIONS
C1 (non-blocking, LOW; new PR) restore the cause split or catch ValueError narrowly around the signing call only, so a path ValueError cannot be reported as a key problem; handle ValueError in the post-rotation append beside OSError; refuse an empty --anchors. Pin each with a test.
C2 (standing gate) GX10 16/16 and CI on this exact head rebased on main; not run by me. The head is frozen except a condition fix.

NOT VERIFIED
POSIX behaviour for a non-escapable surrogate in --anchors (objections 1, 2); the whole sealed-ledger suite; GX10 / Linux; CI.

CONCLUSION
reviewer-3's condition is met: a NUL byte in --anchors is now a one-line refusal before any work, a rotation is never committed for an unusable path, and the dead branch is gone. 14 of 14 non-equivalent mutants die, 176 tests pass, identity correct, merge clean. Two LOW notes on what the removed branch used to guard. PASS on ea1e59c5: C1 is optional LOWs for a new PR (the head stays frozen), C2 is the standing gate.
