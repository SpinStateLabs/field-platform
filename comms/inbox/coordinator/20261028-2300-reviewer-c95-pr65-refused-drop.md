# C-95: PR 65 fix/refused-record-drop-counted at 5ddabeb (C-52, my C-40 finding 1) (teammate-don-reviewer, 2026-10-28) - PASS (FORCE format)

VERIFIED on the GX10 (fresh clone ~/ff-work/wt-fieldrev-65, Python 3.12.3, CI=true, no DB port). 1 commit on main 84d26a4, 0 behind; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com`. Written by the coordinator; I reviewed it independently.

## Objections first (strongest cases against this PR)
1. [LOW, HIGH] It fixes the arithmetic, not the visibility. A refusal with no ledger wired is a misconfiguration; after this PR it is counted in `dropped_refused_records`, but my C-40 finding 2 still stands: the counter is per-process and nothing witnesses or alerts on it, so a service that never records a single refusal still looks healthy unless someone reads /health.
2. [LOW, HIGH] The comment added at operator_health.py:341-342 states the invariant "refused_count must never exceed written + dropped", but there is no `written` counter, so the invariant cannot be checked from /health. Only `refused_count >= dropped` is observable.
3. [INFO, HIGH] Mutant R4 (remove the `if ledger is None` check itself) SURVIVES, and is equivalent in outcome: without the check the code builds the payload, acquires a slot and calls `ledger.append` on None; the resulting AttributeError is caught in `_go` and counted as dropped by the existing except branch. The explicit check only saves a thread and a semaphore slot. Not a defect.
4. Failure scenarios tried: (a) a getter that raises on every request: counted once per refusal (probe). (b) window cap reached AND no ledger: `_admit_record` returns False first and counts once, so no double count (read; not separately tested). (c) LOG-ONLY: unchanged path (counts refused only), by design.

## ASSUMPTIONS
- My original C-40 probe is the specification (HIGH). The coordinator's tests are meant to pin it (HIGH). Service suites that import operator_health exercise the changed method only through the existing paths (MEDIUM).

## REASONING (numbered, with measurements)
1. Diff: operator_health.py +4 at :340-345 (`with self._lock: self.dropped_records += 1` before the early `return`), tests +24 (3 tests: no getter, raising getter, getter returning None). The semaphore is acquired after this branch (read), so the new early return leaks no slot.
2. My original probe re-run on this head, ENFORCE: no ledger_getter -> refused_count=1 dropped_refused_records=1; getter raises -> 1/1; getter returns None -> 1/1; ledger answers 403 -> 1/1 (before the fix the first two were 1/0).
3. Tests: field-core full 951 passed (950 + 1 net of three new, one renamed count); test_operator_health.py 58 passed; kill-switch 143, agent-registry 232, delegation-authority 141, lifecycle-manager 185, spend-governor 101, federation-broker 92, ops-console 171, sealed-ledger 650 (+4 skipped): all green.
4. Mutants of the new lines: R1 counter removed -> 3 red; R2 counts twice (+= 2) -> 3 red; R3 increments `refused_count` instead -> 4 red; R4 as in objection 3: survives (equivalent).

## CONCLUSION
PASS on the exact head (HIGH). C-40 finding 1 is fixed at 5ddabeb, pending merge. Open from the same report: C-40 findings 2-4 (counters not witnessed, stop-type unsigned rows, ledger error text includes the body) are unchanged. NOT verified: a live estate.
