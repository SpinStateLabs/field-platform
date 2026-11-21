# wave2-engineer: interim, R-PR1091-b974fa2 and R-PR1090-3e950b3 (paused, no verdict posted)

Paused on the controller's order (no test process until RESUME). Both cards stay claimed. No PR comment is posted
yet: the loop requires running the tests on the exact head first.

## R-PR1091 @ b974fa21f858ee85f22abfbf2b34a8a8ebcbe221 (head has not moved)
Provisional: PASS WITH CONDITIONS, from reading only (confidence LOW until the tests run).
- Full suite started and stopped by the pause: no last line.
- 29 mutants written, 0 run.
Reading findings (all LOW):
1. A build has no total-time cap: a hung build keeps the slot.
2. The retry budget counts seconds slept, so Retry-After: 0 costs nothing.
3. The README says the 503 is named when the budget runs out; only /verify does that.
Callers: ops-console /attest/pack (console.html:1356, :1883). It does not retry on 503.
Usage (subagent, verbatim): 182225 tokens, 39 tool uses, 1892586 ms, Opus.

## R-PR1090 @ 3e950b3363365a81e3cbe102de6ec43a43ac2365 (head has not moved)
Provisional: PASS WITH CONDITIONS.
- The PR's own test file passed: 92 passed (MEASURED).
- The full tools/tests run hit 7 environment import errors; the rerun was stopped by the pause.
- 53 mutants prepared, 0 run.
Finding 1 (MEDIUM, MEASURED): `load_json`'s fallback lets a TRUNCATED list pass with rc 0. That skips the
"list needs --id" and "exactly once" checks (tools/fly_snapshot.py:114-126, 143, 147). The fix is a condition:
return rc 2 when the outer value fails to parse, and add tests for both inputs.
LOW findings: log-line JSON prefix; nan argument order; naive `now`.
Fly docs: the documented and observed claims are labelled correctly. "state as status" and "MIN_YEAR 2020" are
unsupported but fail closed.
Callers: none ("nothing calls it yet" confirmed with a grep).
Usage (subagent, verbatim): 173932 tokens, 30 tool uses, 859765 ms (to the interim report), Opus.

## After RESUME
One test process at a time across both cards (lock D:/claude-tmp/wave2-testslot.lock.d). For each card: full suite
on the exact head, then the mutants, then the PR comment, then dispatch done.
