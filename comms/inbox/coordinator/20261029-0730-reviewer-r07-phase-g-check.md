# R-07 reviewer report: tools/phase_g_check.py fail-open read (main 9292246; file unchanged since 45a36f5)

VERDICT: two proven fail-open paths (both exit 0), the rest fails closed. No mutation round (the module's own test file takes 156 s per run).

OBJECTIONS FIRST
1. A check tool that returns green when it saw nothing is worse than none: it is what Don runs before flipping flags.
2. "Fail closed" in the file means a recorded FAIL; a path that records `check(True, ...)` for "nothing to do" is a pass.
3. A hand-read plus two probes is not a coverage claim.

ASSUMPTIONS
1. Main 9292246; file 866 lines; I read every function: wait_for, _no_more, _guard_body, _heartbeat_of, _off_evidence, detect_mode, _probe, refusal_paths, positive_path, no_leak, collateral, status_pairing, restore, main, _run, _settle_canary. [HIGH]
2. Probes use the module's own estate harness (`tools/tests/estate_harness.py`, `test_phase_g_check.py` fixtures) in `~/ff-work/wt-fieldrev-76`; the probe files were deleted after. [HIGH]

REASONING
1. FAIL-OPEN A (MEDIUM, proven): `status_pairing` (:617-660) returns `ep.check(True, "no registry status change of <canary> since the start (nothing to pair)")` when no `registry.status_changed` event is found, even when the positive path ran with a key (one kill + one revive, so at least 2 status changes are expected). Probe: ENFORCE armed, `estate.fault("ledger_status_changed_as_updated")` (registry status changes ledgered under another type), keyed run with `--expect-mode enforce`: EXIT 0, `[PASS] no registry status change ... (nothing to pair)`, `49/49 checks passed`. The same flaw was fixed in estate_probe (RT1-3: "want >= 1: none means the pairing above proved nothing", test_estate_probe.py:412-424) and not here. [HIGH]
2. FAIL-OPEN B (MEDIUM, proven): with no `--expect-mode`, an estate whose guard is OFF passes: probe on an unarmed harness estate, keyed, no `--expect-mode`: EXIT 0, `inferred mode: off`, `12/12 checks passed`; refusal paths, positive path and pairing all print `check(True, "mode off ...")` (:403-405, :465-467, :619-622). The mode is "always inferred from behaviour" (the help text, :711-712), so the tool cannot tell OFF-by-mistake from OFF-by-design unless the caller passes `--expect-mode`. Same class as F-R06-3 in estate_probe. [HIGH]
3. Fails closed (read): unreadable ledger count (`start` not an int) records a FAIL and finishes; `_events` records a FAIL on a failed read (estate_probe.py `_events`), so `no_leak`'s and `status_pairing`'s `if events is None: return` still leave a FAIL; `collateral` checks `0 <= start <= len(events)`; `ep.finish()` returns 1 when no check ran; `detect_mode` records "mode UNVERIFIED" on an unrecognised answer; `_run` refuses a plaintext secret to a public host, requires the canary, refuses a non-active canary before any write, re-reads heartbeat before each write (`guard_active`), sets `killed_by_us` before the kill, and `_settle_canary` revives and returns exit 3 if the canary may be left killed (unlike estate_probe's `cmd_catalogue`, F-R06-2). [HIGH]
4. `restore` with no credentials sends the revive without them: under ENFORCE that is a 401 and a recorded FAIL, as intended. [MEDIUM]
5. Existing test cover: 89 tests in test_phase_g_check.py (88 + the probe I removed) pass in 156 s; every fault test asserts a named check; none of them covers findings A or B. [HIGH]

CONCLUSION
Fix card suggestion: (A) in `status_pairing`, when the positive path ran (key given, mode armed) require >= 2 status changes (kill, revive) and FAIL on none, with a test using `ledger_status_changed_as_updated`; (B) require `--expect-mode` (or treat OFF as FAIL unless `--expect-mode off` is given) so a green run means the guard is armed. Not done: mutation round on this module (about 150 s per mutant); a mutator pinned to `-k` subsets could do it.
