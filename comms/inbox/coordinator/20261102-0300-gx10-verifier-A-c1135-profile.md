gx10 verifier A, C-1135: profile of the full 16-suite run on main 05942b984e5338f56ebfd5597a57f0b9c22307a3 (worktree HEAD checked equal to that sha). Durations only; measured on the GX10, serial, one run at a time.

CORRECTION FIRST (HIGH): the card suspects test_upgrade_smoke_fixture.py. It is NOT the cost. 17 rows, 4.5 s of 512.3 s of tools time (0.9 percent).

Per-suite wall time (HIGH, measured; load average 0.7 to 1.6 during the run, nothing else heavy on the box):
- core+sealed-ledger 111.0 s (2346 passed, 4 skipped)
- tools 518.5 s (3749 passed, 4 skipped) = 56 percent of the whole run
- field-agent 26.5 s; agent-registry 6.8; attestation-reporter 11.8; claude-approver 1.6; compliance-crosswalk 5.5; conformance-sentinel 22.4; delegation-authority 12.9; federation-broker 25.5; force-gateway 8.0; incident-replay 3.5; kill-switch 11.4; lifecycle-manager 12.3; ops-console 127.7 (14 percent); spend-governor 13.2
- TOTAL 918.6 s = 15.3 min. Sum of the three groups: core 111 + tools 518.5 + the 14 service suites and field-agent 289 = 918.6. All 16 suites passed, 0 failed.

Tools suite, where the time is (HIGH, from pytest --durations=0 rows of 5 ms or more; 9446 faster tests hidden):
- 1803 rows, 512.3 s: call 451.5, setup 18.0, teardown 42.8.
- Per file: test_topology_lint.py 108.4 s (21 percent), test_phase_g_check.py 102.7 (20), test_renew_token.py 75.2 (15), test_fly_identity_c5.py 65.9 (13), test_estate_probe.py 36.8 (7), test_operator_cli_c2.py 20.8, test_estate_kill_watcher.py 15.7, test_environment_doc.py 15.5. The top 5 files are 389 s = 76 percent of the tools time.
- No single test dominates: the slowest is 6.44 s (test_renew_token.py::test_a_mint_answer_naming_a_token_the_authority_cannot_read_back_sweeps_the_real_mint). 96 tests take 2 s or more.
- The 30 slowest (all call rows, 2.08 s to 6.44 s): test_renew_token.py 13 of them (6.44, 6.43, 3.94, 3.14, 2.77, 2.58, 2.41, 2.34, 2.28, 2.25, 2.18, 2.18, 2.08), test_fly_identity_c5.py 7 (6.03, 5.32, 4.03, 4.02, 4.02, 4.02, 4.02), test_topology_lint.py 5 (4.08, 4.06, 2.08, 2.08, plus the cli rows), test_phase_g_check.py 1 (6.35), test_phase_g_check_caller_signed.py 2 (3.29, 3.19), test_machine_verifier_identity.py 1 (3.26), test_operator_keygen_c393.py 1 (3.00, two real processes), test_estate_probe.py 1 (2.36). Full list is in ~/ff-work/prof-c1135/tools.out on the GX10.
- Other heavy spots: core+sealed-ledger top test 15.0 s (test_operator_observer_c6_serve.py), then 10.3 s (test_ledger_readers.py second-writer process); ops-console 127.7 s is mostly test_dashboard_escaping.py parametrised cases at about 4.6 s each.

What can be cut (reasoning, MEDIUM; I did not measure any change):
1. The 16 suites run one after another in runbatch.sh. The 14 service suites, field-agent and core total 400 s and are independent directories. If they ran beside tools, the wall time would be about tools alone, 518 s (8.6 min), under the 10 minute goal. LOW confidence that they are safe to run together (shared ports, temp paths, the sealed-ledger tests): I do not know; this needs the card C-1136 three-identical-results check before any change.
2. Splitting tools/tests by file into 3 shards by the per-file times above would take tools from 518 s toward about 175 s, if the files are order-independent (not checked) and the box has spare cores (load stayed near 1, so likely).
3. Both together would put the full run near 3 to 4 minutes (extrapolation, LOW).
4. Not worth chasing: test_upgrade_smoke_fixture.py (0.9 percent). The fixed per-test cost of 4.0 s in test_fly_identity_c5.py (4 mutant tests at 4.02 s each) looks like a sleep or process start; not inspected.

Not covered: no change was tried; the numbers are one run (variance unknown; C-1137 is verifier B three-run check on the tools suite and should be run with the box otherwise idle); durations hide tests under 5 ms.

Raw files on the GX10: ~/ff-work/prof-c1135/suites.txt and the per-suite .out files.
