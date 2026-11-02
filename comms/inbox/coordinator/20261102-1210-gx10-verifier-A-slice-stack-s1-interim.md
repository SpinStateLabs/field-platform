gx10 verifier A, slice stack S1, INTERIM (the final report follows the second full run, about 15 minutes). Scratch stack, never pushed, on main c356e2056ef57953dabb44bda1a3a23e353c43d1 (unchanged).

RUN 1 (stack head e26e7afe899cc5b87c7ae15f7583188dd579c14d, with PR 467 at the OLD head 45bd9b9f): 15 of 16 suites green, tools RED: 1 failed, 3790 passed, 4 skipped.
- The failing test (HIGH, from a re-run with failure names): tools/tests/test_operator_plumbing.py::test_the_expected_set_is_every_service_that_imports_operator_auth. Message: a service started applying operator auth, update EXPECTED and the compose files. The extra service is conformance-sentinel.
- Cause (HIGH for the test and the extra service, MEDIUM for the link to PR 467): the old PR 467 head 45bd9b9f has conformance-sentinel headers.py import operator auth directly. Lane 7 reviewed that head as FAIL (narrow).
- The fix is already on PR 467: its head moved to ea8857b7 (one commit, conformance-sentinel headers.py reads the pair through authn.auth_headers()). I added that commit to the stack: test_operator_plumbing.py now passes (13 passed) and the conformance-sentinel suite passes (280). That is two targeted runs, not the full set; the full set is running now on stack head 066487ab051f3ce93f33bd4854f4bbd7df1cb291.

Per PR (patch-id aware cherry-picks, in the requested order 462, 463, 464, 466, 467, 468):
- 462 @057893c6: CLEAN (1 commit). 463 @c0f781d4: CLEAN (2). 464 @b8ff923e: CLEAN (1). 467 @45bd9b9f, then @ea8857b7: CLEAN (1 + 1). 468 @7f137163: CLEAN (1).
- 466 @c00dc6c9: CONFLICT when stacked, in docs/ENVIRONMENT.md only. Against bare main PR 466 merges cleanly, so the conflict is with PR 463, which also edits that file. One hunk, one anchor row: FIELD_WITNESS_FLY_SECRET_FILE sealed_ledger/witness.py:60 should be :62. Resolution: take the stack side of the hunk, run tools/environment_anchors.py --fix (fixed 1, 0 left), --check then reports 0 wrong rows; 466's second commit then applies clean. Merge assistant 1 batching this group needs that one fix-up.

Counts in run 1 against the baseline (main c356e205 = cb28 head, verifier B 20261103-1920 report): none went down. core 2358 (+12), tools 3790 passed +1 failed (baseline 3776), conformance-sentinel 280 (+17), federation-broker 193 (+2), spend-governor 303 (+12); the other 11 suites equal.

Baseline run (part 2 of the request): I did not run a separate one. Main c356e205 is the cb28 head, so verifier B cb28 run is a full run on exactly that sha: all 16 suites green, counts in that report. Python version on the GX10 venv used by every run: 3.12.3. I will run an independent baseline for variance if you want one.
