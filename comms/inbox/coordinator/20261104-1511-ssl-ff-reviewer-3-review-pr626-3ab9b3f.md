# Review PR 626 @ 3ab9b3f03fc49f58317aabde1b2fa4a5bad09c93 (field-agent canary: serve validates its env and flags once, S3-6) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head 3ab9b3f0. UNVERIFIED (cloud, no GX10). Condition 1 pins the boundaries and the junk-heartbeat case.

## Objections first
1. The point of the change is that a BAD value exits 2 naming only the variable, never a default and never the value. A parser that falls back on a junk value (N3) or accepts a boundary one past the range (P2) defeats that; both survive.
2. The setting is read lazily so a junk serve-only variable never touches `x3-check`; my mutant for that (X3) was a no-op (details below), so the lazy-read claim is not independently tested by me.
3. Python's `int()` accepts underscores and non-ASCII digits (general knowledge, MEDIUM): `FIELD_CANARY_PORT=8_0` would parse as 80. Not pinned either way.

## Facts (HIGH)
- Head fetched via refs/pull/626/head = 3ab9b3f0; 1 commit; base origin/main 97dcfec1 (main has since moved by unrelated commits); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. `canary.py` +48 -6, `tests/test_canary_main_args.py` +90 (new, 21 tests).
- Baseline unmutated: field-agent suite 227 passed, 1 deselected (the deselected `test_canary_agent.py::test_the_process_never_exits_on_a_halt` fails on main too: subprocess cannot import field_agent in my environment; not counted).

## Mutants (the whole field-agent suite each time; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| port: integer 1..65535 (P1-P5) | 5 | 3 (P1, P3, P4) | 2 (P2, P5) |
| work-every: finite, >= 0.1, no upper bound, float (W1-W4) | 4 | 3 | 1 (W4) |
| heartbeat-every: 0 = off, else >= 1 (H1-H3) | 3 | 2 | 1 (H3) |
| parse: nan, inf, junk refused; value never in the message; message names variable and range (N1-N6) | 6 | 4 (N1, N2, N4, N5) | 2 (N3, N6) |
| naming: flag vs env name, blank env treated as unset, blank flag (T1-T4) | 4 | 2 (T1, T2) | 2 (T3, T4) |
| exit 2, stderr, parsed values stored, no server on a bad value (X1, X2, X4, X5) | 4 | 4 | 0 |
| lazy env read for x3-check (X3) | 1 | INVALID | n/a |
Totals counted from the table: 5+4+3+6+4+4 = 26 valid rows; killed 3+3+2+4+2+4 = 18; survived 2+1+1+2+2+0 = 8; plus X3 invalid (my mutant only added `port = ... = None` before the existing `try`, which changes nothing: a no-op, not counted either way); 0 anchor failures.

## Survivors
- F-R626-1 MEDIUM-LOW (N3): a value that does not parse becomes 0. For `--heartbeat-every` (zero allowed) a JUNK value would then mean "off" instead of exit 2. No test passes a non-numeric heartbeat value (the junk cases use port and work-every, where 0 is already out of range).
- F-R626-2 LOW-MEDIUM (P2, P5): the port boundary values 65536 and 1 are not both pinned (65536 accepted, or 1 refused, passes).
- F-R626-3 LOW (W4, H3): no upper bound check for work-every and the heartbeat's lower boundary (1 refused) are unpinned.
- F-R626-4 LOW (T3, T4): a whitespace-only environment value and a blank flag are not pinned.
- F-R626-5 LOW (N6): the range text in the message is unpinned (cosmetic).

## Conditions
1. Pin F-R626-1 (a non-numeric `FIELD_CANARY_HEARTBEAT_EVERY` exits 2 naming the variable) and F-R626-2 (65536 refused, 1 and 65535 accepted) before this lands, or the coordinator rules them follow-ups.
2. GX10 16/16 and CI on this head rebased on current main.
