# C-81: PR 59 feat/alerts-ntfy-r2 at c6883e5 (supersedes #56) (teammate-don-reviewer, 2026-10-28) - PASS with one LOW

VERIFIED on the GX10 (fresh clone ~/ff-work/wt-fieldrev-59, Python 3.12.3, CI=true, no network, no DB port). Base: main 75a84c8, 0 behind / 5 ahead. All five commits carry author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> (`git log` on the range): the identity finding on #56 (F-C2-5 pattern, cda3b97 and 9cdef89) is resolved for this branch. Independent reviewer: I authored none of it.

## range-diff against #56 bebf0f1 (`git range-diff c8ecba7..origin/feat/alerts-ntfy origin/main..origin/feat/alerts-ntfy-r2`)
1:cda3b97 -> b4d0495 and 2:9cdef89 -> 0a9fadb: marked `!`, and the ONLY difference is the Author line (donhagell@gmail.com <> -> the repo identity); the patches are identical. 3:f657bea = 07f072a and 4:bebf0f1 = e75d9bb: identical (`=`). 5: new commit c6883e5. So everything I reviewed in C-6, C-43 and C-75 is unchanged; only commit 5 is new.

## Tests
- `test_alerts_ntfy.py` 62 passed (60 + 2 parametrised rows `("stage_aborted","5","rewind")`, `("rotation_halted","5","key")` in the existing priority/tag table); field-core suite 946 passed (= main's 884 + 62).
- Mutants of the new classes (5): S1 stage_aborted priority 5->4 red; S2 rotation_halted priority 5->3 red; S3 stage_aborted tags changed red; S5 stage_aborted removed from the table red; S4 rotation_halted TITLE changed (`HALTED - action needed` -> `notice`): SURVIVES (62 passed).

## Condition status (my earlier reviews)
- C-6 condition 1 (environment proxy), C-43 condition 1 (default-opener test): closed (unchanged commits; mutant E, `send()` not using `_OPENER`, remains LOW from C-75).
- C-6 condition 2 / C-22 (a `stage_aborted`/rollback class at priority 5 and a CRITICAL rotation-fault class before the first automatic arming): CLOSED in code: `stage_aborted` (5, tags rotating_light/rewind/field) and `rotation_halted` (5, sos/key/field; body "stopped after repeated faults and will not retry by itself; a key may be near its expiry"); runbook table rows and README updated (docs/runbooks/ntfy-alerts.md +2, packages/field-core/README.md).
- Still caller-side, not testable here: script callers must exit non-zero on an undelivered alert; the stage controller and rotator that will SEND these classes do not exist on main (#57 sends none).

## Findings (new)
1. LOW: the title of `rotation_halted` ("FIELD: key rotation HALTED - action needed") and `stage_aborted` ("FIELD: Phase G stage ABORTED, rolled back") are not pinned by any test (S4 survives); priority and tags are. The title is what Don reads on the lock screen. Add the two titles to the existing table test.
2. LOW: emoji short codes `rewind` and `sos` are new and unchecked against ntfy's list (same caveat as the earlier `arrow_right`, `rotating_light`, `key`); an unknown code shows as plain text, not a failure.
3. INFO: D-5's design also named a separate "within 14 days of `key_not_after`" CRITICAL class; only `rotation_halted` was added. If the dead-man check is meant to alert on proximity to expiry it needs its own class (not required by C-6/C-22 as written).
4. INFO: #56 should be closed when #59 merges (same commits, superseded); I did not check how the coordinator is handling the stale PR.

## Verdict
PASS for merge on content: the squash-relevant history is the repo identity throughout, the proxy fix and tests are unchanged, the two classes are tested for priority and tags. NOT verified: real ntfy delivery, the emoji codes, iOS.
