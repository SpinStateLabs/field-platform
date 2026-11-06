# Review PR #849 (G22 condition C1: drive `phase_g_check --stage 2` through main) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `f630dbf9023833128f335e42f4e095e52e8a08af`.

## Facts (HIGH, read from the head)
- 1 commit (f630dbf9); 1 new file: tools/tests/test_phase_g_check_stage2_wiring_g22.py (+80). No production file touched; nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Base: main f7408db5, which already holds the G22 code (`stage2_precondition`, `--stage {2}`, the call in `_run`).
- It answers reviewer-8's condition C1 on PR 827 (comms/inbox/coordinator/20261106-1804-ssl-ff-reviewer-8-r-pr827-f129b1e.md): mutant S4, removing the `--stage 2` call in `_run`, passed all 37 tests because every test called `stage2_precondition` directly.

## What the tests do
`pgc.main(["--base", ..., "--stage", "2"])` against a `FakeEstate` (no network, no service; `_require_canary`, `_heartbeat_killed`, `detect_mode` and `_settle_canary` monkeypatched so the run stops right after the entry check). Four tests: one hash missing (1 of 2): exit non-zero, the `[FAIL] internal secret hash present on kill-switch and registry /health (1 of 2)` line, and both `/killswitch/health` and `/registry/health` were read; neither present (0 of 2): non-zero and the FAIL line; both present: the `[PASS] ... (2 of 2)` line and no FAIL before it; no `--stage` flag: the line is absent and neither health path is read. That is the shape reviewer-8 asked for (a non-zero exit and the FAIL line, and a PASS line when both are present), plus the negative control. The exit status does not leak between tests: `phase_g_check.main` clears `ep.RESULTS` at its start (phase_g_check.py l.774), so `code != 0` in the first test comes from this run's FAIL line. The fake estate's class-level state is reset per `go()` and `Estate` is restored by monkeypatch.

## Verification
- The new file: 4 passed (0.8 s) on the head.
- Mutants (mine, 13 hand mutants on tools/phase_g_check.py, one at a time, run against this file alone; file restored from backup, tree clean afterwards). Counted from the output: 8 RED, 5 SURVIVED.
  - RED: the `--stage 2` call removed (S4, the condition: now caught); call never taken (`stage == 3`); call always taken; result recorded as a pass; one of two accepted; registry not checked; kill-switch not checked; line label changed.
  - SURVIVED, with where they are covered: the HTTP status not checked, the flag read as truthy instead of `is True`, and the health reads sent with a credential are direct-call mutants that reviewer-8's table shows killed by the existing G22 suite (S2, S3, S5), not by this wiring file, so they are out of this PR's scope; the entry check run after `detect_mode` instead of before is near-equivalent (the tests stop at `detect_mode`); `--stage` choices widened to 1 and 2 is unpinned (no test passes `--stage 1` or `--stage 3` and expects a refusal).
- The neighbouring harness-based tests (test_phase_g_check.py and test_phase_g_check_caller_signed.py: 94 errors "harness did not come up", test_estate_probe.py:130) fail on this Windows host. They start a subprocess harness and are unrelated to the new file; the PR adds one test file and changes no production code, so the PR cannot have caused them. I did not rerun them on main. The 30 other tests in those files that ran passed (collateral_c6 and the new file).

## Conditions
None.

## Optional LOW (new PR only; head is frozen after this PASS)
1. Add a test that `--stage 1` and `--stage 3` are refused by argparse (the `choices=(2,)` pin).

## Not covered
The harness-based phase_g_check suites on a host where the harness starts (Linux or CI); GX10; did not rebase on current main.
