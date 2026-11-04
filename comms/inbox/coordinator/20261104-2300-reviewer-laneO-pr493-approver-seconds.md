# Lane O reviewer: PR 493 (S-B3, claude-approver poll and halt-wait seconds finite and bounded) @8eb5ba6cfc11016563d0894638001bba0a5e54ec. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 8eb5ba6c. Lane B (approver). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH). I did not write the head.

Objections first: (1) the bound is 86400 s (builder's own choice, flagged for Don): a halt wait of up to a day blocks /halt that long, and a poll of a day leaves approvals unseen that long; a lower cap, or refusing instead of clamping, is the alternative, and a silent clamp hides a typo (1e30 becomes one day with no log). (2) the test "the clamped value is waitable" asserts only <= threading.TIMEOUT_MAX; any value up to 86400 passes it, and it never calls Event.wait or runs the poller, so the OverflowError path is not exercised (read, HIGH). (3) the poller loop (core.py:1005-1007) and the /halt path were not run with inf by the builder or by me; coverage is the shared function only.

Run here (cloud, relative PYTHONPATH of every service src and packages src): new file 13 passed; whole claude-approver suite 328 passed, matching the builder. NOT run: the 16-suite set, CI.

Mutants on config.py (20, scratch worktree on the exact head; each against the PR file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 non-finite gives the default (isfinite dropped, inf only, nan only, clamps, zero) | 5 | 5 | 0 |
| B2 huge finite clamped to MAX (clamp dropped, to default, max for min, +1, one week) | 5 | 4 | 1 |
| B3 sane values unchanged (scale, int, exclusive bound, halt and poll ignore env) | 5 | 5 | 0 |
| B4 floor and negative default (floor dropped, negative to zero, negative allowed, zero is default, floor min) | 5 | 5 (1 by older tests) | 0 |
| Total (counted from the rows) | 20 | 19 | 1 |

Survivor (1, real LOW pin gap, F-O493-1): MAX_ENV_SECONDS = 86_401 survives. The clamp tests compare to config.MAX_ENV_SECONDS symbolically, and the "sane" test only goes to 86400, so the one-day value itself is not pinned (a test asserting == 86_400.0 would kill it).

CONDITIONS (blocking): C1 CI green on the exact head and a GX10 run of the full set (code PR; I could not run it). C2 Don's choice of bound and clamp-vs-refuse (objection 1), recorded.
Optional, NEW PR only after the head is frozen: F-O493-1 pin; replace the vacuous "waitable" test with one that really calls Event.wait on the clamped value (or drive the poller once).

Tokens/cost line: not available to me. I do not know.
