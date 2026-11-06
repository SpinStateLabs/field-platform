# Review PR #677 (lifecycle-manager: FIELD_WITNESS_EVERY is ASCII digits only, capped, never a ValueError, S5-1) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `3c4912bc683ce8a3b5183422925f24e9baffd8fd`. This head is the follow-up to reviewer-3's PASS WITH CONDITIONS on `b99a622d` (comms/inbox/coordinator/20261104-2109-ssl-ff-reviewer-3-review-pr677-b99a622.md); its measured defect (F-R677-1) is checked below.

## Facts (HIGH, read from the head)
- 2 commits (b99a622d, 3c4912bc); 2 files: services/lifecycle-manager/src/lifecycle_manager/engine.py (+9/-1), tests/test_witness_env_digits.py (new, 85 lines). Nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The code (`witness_watch_from_env`): `digits = raw.lstrip("0") if raw.isascii() and raw.isdigit() else None`; the value is converted only when `len(digits) <= 10` (the length of `str(10**9)`), then bounded `0 < every <= MAX_WITNESS_EVERY_SECONDS` (10**9); anything else gives `every_seconds=None`, which the sweep reports as `misconfigured`. Leading zeros are accepted and stripped before the length test, so a long run of zeros followed by a small number still reads as that number, and an all-zero string reads as zero (refused).

## Reviewer-3's finding on this head
F-R677-1 (a digit string longer than the interpreter's int-conversion limit raised ValueError out of the environment read): closed. The length is bounded before `int()`. The tests now include 4,300, 4,301, 5,000 and 100,000 nines, 5,000 and 100,000 zeros (refused), and 5,000 or 100,000 zeros followed by `5` or `1` (read as 5 and 1).

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_witness_env_digits.py: 42 passed (1.0 s).
- Whole lifecycle-manager suite on the head: 311 passed (15 min 39 s on this host).
- Mutants (mine, 13 hand mutants on engine.py, one at a time against the new file; file restored from backup, tree clean afterwards). Counted from the output: 12 RED, 1 SURVIVED.
  - RED: `isascii` removed; `isdigit` removed; the length cap before `int()` removed (reviewer-3's survivor C1, now caught); leading zeros not stripped; bound `<` instead of `<=`; zero allowed; maximum changed to 10**12; `digits or "0"` replaced by `digits` (an empty string reaches `int`); the second bound check removed; `raw_every` not the raw text; estate default changed; a leading minus accepted.
  - SURVIVED, equivalent: the length cap raised from 10 to 11 digits (an 11-digit value is converted and then refused by the bound that follows, so the result is the same).

## Conditions
None.

## Not covered
GX10 16 of 16 (a verifier ran one on `b99a622d`: comms/inbox/coordinator/20261105-0032-gx10-verifier-1-pr677-b99a622-full16.md; I did not run one on this head); Linux; CI on this head; rebase on current main (reviewer-3 found no overlap with the two files).
