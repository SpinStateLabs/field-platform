# Lane O reviewer: PR 530 (scout S-C9, federation-broker: a lost verdict audit append is counted, logged and shown in /health) @ba42b3b9d185b8e8fe0385b947973cc3c80e8db3. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head ba42b3b9. Lane B (federation). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); +3 lines in api.py, +12/-3 in engine.py, +97 test lines. I did not write the head. Claimed through dispatch.sh (R-PR530-ba42b3b); the builder report is 20261105-2200-builder-s-c9-report-and-pr502-status.md.

Objections first: (1) the counter is a bare `+= 1` on an int attribute, updated from request threads; the kill-switch got a locked counter (`_GapCounter`, C-811 F-C745-3) for exactly this reason, so under concurrent drops this PR can lose increments (read, HIGH; I did not reproduce a lost update, CPython often hides it, MEDIUM that it matters). (2) the counter is per process and resets on restart (the field name says "since start" in the comment, HIGH). (3) the `except Exception` is intentionally broad (a verdict must stand); the test only raises OSError-family exceptions (survivor below).

Run here (cloud, scratch worktree on ba42b3b9, relative PYTHONPATH of every service src and packages src): new file 8 passed; whole federation-broker suite 199 passed. NOT run: the 16-suite set, CI.

Mutants on engine.py and api.py (25 written; 2 excluded: one did not apply, one was invalid (a malformed mutant of mine); 23 run, scratch worktree on ba42b3b9; each against the new test file, survivors against the whole suite):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 each failed append is counted once | 5 | 4 | 1 |
| B2 the verdict stands when the append fails | 4 | 4 | 0 |
| B3 nothing is dropped without a ledger or with a working one | 3 | 2 | 1 |
| B4 a working ledger still gets the event | 1 | 1 (older test) | 0 |
| B5 the log names the event type and exception type, never the message | 5 | 4 | 1 |
| B6 /health shows the counter and keeps its fields | 5 | 5 (1 by an older test) | 0 |
| Total (counted from the rows) | 23 | 20 | 3 |
B3 has 3 and B4 has 1 runnable mutants (under the 4 asked).

Survivors (3): 1 equivalent (`= -0` plus an unused attribute: no behaviour change), 2 real LOW pin gaps:
- F-O-pr530-1: the except clause narrowed to `OSError` survives, because every exception the tests raise (ConnectionError, TimeoutError, OSError) is an OSError. A ledger client failing with another type (a JSON error, an HTTP client error, a ValueError) would escape and break the verdict; no test raises one (engine.py, the except in _verdict). Real, LOW-MEDIUM.
- F-O-pr530-2: the logger name is unpinned: logging to a logger named "other" instead of `__name__` survives (caplog captures through the root handler whatever the logger).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 objection 1 recorded: either a locked counter like the kill-switch's, or a stated reason a plain int is enough here.
Optional, NEW PR only after the head is frozen: F-O-pr530-1/2 pins (a test with a ValueError and a non-OSError client error).

Tokens/cost line: not available to me. I do not know.
