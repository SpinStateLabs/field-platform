# Review PR 685 @ 3534e6be7979b1676b13866e81f79d57bbb1457c (sealed-ledger: ledger anchor and rotate --anchors fail cleanly, S5-9) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head 3534e6be. UNVERIFIED (cloud, no GX10). The condition is one measured traceback that the code comment says is handled.

## Objections first
1. The PR says `anchor` never prints a traceback and never key text. It handles key read errors, garbage PEM, a busy or corrupt ledger, an unwritable anchors file, and a failed anchor after a committed rotation. I attacked each (below) and one more input the code comment names: a NUL byte in `--anchors`.
2. After a committed rotation, a failed anchor write must not look like a failed rotation: the PR prints the rotation result first and then the failure line. Pinned (T1-T4).
3. A `ValueError` is caught for two unrelated causes (a garbage key, an unusable path) and told apart by `pem is None`; with a key present a path error would be reported as a key error.

## Facts (HIGH)
- Head fetched via refs/pull/685/head = 3534e6be; 1 commit; four commits behind current main (no overlap with these files); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 3 files, +163 -5: `sealed_ledger/cli.py` (`anchor` and `rotate --anchors`), `tests/test_anchor_cli.py` (+128, 12 tests), one boundary-echo allowlist line.
- Baseline unmutated: the new file 12 passed.
- MEASURED (my own script, `CliRunner`, a real ledger): `anchor --path P --anchors "a\x00b"` with no key gives exit 1, EMPTY output, and `result.exception = ValueError('stat: embedded null character in path')`; the same with a valid `--key` gives the identical result. The error comes from click, which stats a `Path`-typed option while parsing, before the command body runs; so the handler branch `if pem is None: ... cannot write --anchors (ValueError)` is unreachable for a NUL and the traceback the PR meant to remove is still there for that input. (PR 681 hit the same click behaviour and fixed it by typing the option `str`.)

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| reading --key: OSError and UnicodeDecodeError caught, exit 2, class name only (K1-K4) | 4 | 4 | 0 |
| write_anchor errors: corrupt exit 1 and reported, garbage key exit 2 and not echoed, ValueError caught, OSError exit 1 naming the path, the no-key branch (W2, W3, W5-W10) | 9 | 8 | 1 (W4) |
| rotate: a failed anchor after a committed rotation is reported, result printed first, exit 1, wording (T1-T4) | 4 | 4 | 0 |
| rotate message carries no exception text (T5) | 1 | 0 | 1 |
Totals counted from the table: 4+9+4+1 = 18 valid rows; killed 16; survived 2 (W4, T5; both killed by another test in the whole suite); 1 further edit (W1, busy) did not anchor (its text occurs three times) and is not counted.

## Findings
- F-R685-1 LOW-MEDIUM (measured): a NUL in `--anchors` is still a click-level `ValueError` traceback; the branch and comment in the PR for it are dead. Type `--anchors` as `str` (as PR 681 did for `--out`) and convert inside the command, or remove the branch and say so.
- F-R685-2 LOW: with a valid key and an unusable path, `ValueError` would be reported as a key problem (W10 pins only the swap); unreachable today for the reason above.
- F-R685-3 LOW (W4, T5): the no-text promise for the garbage-key and rotate messages is pinned only by other test files, not by this one.

## Conditions
1. Fix F-R685-1 (type `--anchors` as `str`) or remove the dead branch and its comment, and add the NUL case to `test_anchor_cli.py`.
2. GX10 16/16 and CI on this head rebased on current main.
