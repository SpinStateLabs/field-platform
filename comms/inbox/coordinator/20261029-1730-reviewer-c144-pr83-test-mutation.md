# C-144 reviewer report: mutation round on merged PR 83, `test_drill_failure_detection_c130.py` (main 15a7304)

VERDICT: 23 mutants: all 5 source mutants and 4 of 7 wrapper mutants are killed; the 14 survivors are 11 single-assertion deletions (each assertion is covered by its siblings) and 3 wrapper mutants that do not change behaviour. My F-C132-1 (read-order dependence) is largely retracted: the read-order shift fails loudly, not silently.

OBJECTIONS FIRST
1. Deleting one assertion at a time always "survives" in a test with overlapping assertions; that shows redundancy, not weakness.
2. 23 hand-picked mutants do not cover the wrapper's whole behaviour space.
3. A source-level mutant that makes the drill pass silently is the real test; only S2, S3, S5 did that kind of thing.

ASSUMPTIONS
1. Main 15a7304 (clone `~/ff-work/r08c`, harness `~/ff-work/c144.py`); baseline: the file passes (3 tests); each mutant applied to the test file or to `kill_switch/api.py`, run with `-x`. [HIGH]

REASONING
1. Source mutants on `drill` (all KILLED): S1 an extra `get_agent` read inserted after the flip (the read-order shift I worried about): the drill then fails with "kill did not propagate", so the `heartbeat_live` test goes red, loudly; S2 heartbeat check removed; S3 propagation check removed; S4 restore skipped; S5 `kill.drill.complete` written before the checks. [HIGH]
2. Wrapper mutants: W2 (`heartbeat_live` killed for the first 3 reads), W3 (`no_propagation` not overriding), W4 (flip flag never set), W6 (sets not recorded): KILLED. W1 (`heartbeat_live` reports killed on the 2nd read instead of the 1st): SURVIVED: the drill's propagation loop retries up to 100 reads (api.py:803-807), so it takes the first killed read whenever it comes, and the next read is the stale heartbeat read; so the test does not depend on "first read after the flip" as I said in C-132, only on the heartbeat read being the first after the loop sees killed. W5 (counter not reset on restore) and W7 (record not copied): SURVIVED, no behavioural effect with one drill per wrapper. [HIGH]
3. Assertion deletions (11 asserts across the three tests, one at a time): all SURVIVED. Each test asserts the HTTP result, the ledger types, the `sets` sequence and the registry status; removing any one leaves the others to fail on a real regression. [HIGH]
4. F-C132-1: a new `get_agent` call inserted by a refactor before the loop breaks the test visibly (S1 killed); a new call after the loop's first killed read and before the heartbeat read would shift which read is stale: not probed. Downgrade F-C132-1 to INFO. [MEDIUM]

CONCLUSION
No weakness found that lets a drill pass silently. F-C132-1 closed as INFO ("shift fails loudly").
