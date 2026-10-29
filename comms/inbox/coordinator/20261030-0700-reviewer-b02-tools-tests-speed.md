# B-02: tools/tests speed pass (report only, nothing applied)

Measured on the GX10 (load 0.4 to 1.3, no other full run of mine), main 91bf0c7, `pytest -q tools/tests --durations=0 --durations-min=0.5`, venv-fieldrev, Python 3.12.3, no docker.

## Result
2132 passed, 4 skipped in 553 s (9 min 13 s wall). HIGH (log read).
Tests under 0.5 s are not listed by pytest here, so per-file sums below cover only tests of 0.5 s or more: 466 s of the 553 s. The other roughly 87 s is the many fast tests plus collection. HIGH.

## The five slowest files (sum of listed tests >= 0.5 s, phase: call unless noted)
| file | seconds | tests >= 0.5 s | share of 553 s |
|---|---|---|---|
| test_phase_g_check.py | 177 | 52 | 32% |
| test_topology_lint.py | 108 | 51 | 20% |
| test_fly_identity_c5.py | 66 | 24 | 12% |
| test_renew_token.py | 51 (47 call, 2 setup) | 24 | 9% |
| test_estate_probe.py | 24 (6 call, 3 setup, 16 teardown) | 40 | 4% |
Together 425 s, 77% of the wall time. Next: estate_kill_watcher 14 s, phase_g_check_caller_signed 8 s, operator_cli_c2 6 s.

## What the time is (each claim sourced)
1. test_phase_g_check.py: the cost is in `call`, not setup (setup 1 s in total). The module-scoped estate fixture (`est`, line 48) is booted once. Most slow tests sit at a floor of about 3.4 s each (the FAULT matrix, the c12 and c287 cases, 3.4 to 3.6 s) with one outlier at 12.5 s (`test_FAULT_a_missing_operator_unauthenticated_event_is_red_in_log_only`). The floor is a per-run cost of the tool under test, not fixture start; I did not profile what inside the run costs 3.4 s. Unknown.
2. test_topology_lint.py: 108 s all in `call`; only 3 of its tests call `lint.analyse(REPO)` (lines 335, 356 and one more); the slow ones, at 4 s each, are the "behavioural result" and "roster guard" cases (`test_the_behavioural_result_decides_fly_status_in_analyse` 4.1 s, `test_a_roster_guard_that_passes_a_blank_value_is_a_finding` 4.0 s). The cost per test is the lint's own analysis; whether an analysis result is recomputed that could be shared, I did not determine. Unknown.
3. test_fly_identity_c5.py: 66 s; four `test_each_c5_mutant_is_caught[...]` and `test_absent_secrets_are_byte_identical_to_origin_main` sit at 4.0 s each, and two entrypoint cases at 5.3 and 6.0 s. The file contains real shell sleeps by design (e.g. `sleep 2` in the daemon-shutdown trap at line 674, a 0.5 s wait at 678, polling loops to 8 s at 682), so part of the floor is deliberate waiting. HIGH for the sleeps, unknown for the share.
4. test_renew_token.py: 51 s; the top cases (6.4 s, 6.4 s, 6.0 s) are the "authority cannot read back" sweeps; module-scoped harness (line 450 and 465), so no repeated boot. MEDIUM.
5. test_estate_probe.py: 24 s, of which 16 s is `teardown`: the module-scoped estate stops once at the end. A 16 s stop of the harness is worth a look. LOW confidence on the cause (not investigated).
6. No parallelism: pytest-xdist is not installed in the venv; CI runs the suite as one process (`.github/workflows/ci.yml` pytest steps; I read the grep, not each step). MEDIUM.

## Proposals (none applied)
P1 (largest, lowest risk): shard the `tools/tests` CI step by file into three processes. Suggested split by measured seconds: shard A = test_phase_g_check.py + test_phase_g_check_caller_signed.py (185 s); shard B = test_topology_lint.py + test_estate_probe.py + test_estate_kill_watcher.py (146 s, plus the small files); shard C = test_fly_identity_c5.py + test_renew_token.py + all remaining files (about 117 s + the ~87 s of fast tests, about 200 s). Wall time of the tools step would drop from about 9 min to about 3.5 min if CI has the cores; the step is the long pole of the `tests` job (4 Python versions at 13 to 19 min each, run ids 40808657760 and others, from `gh pr checks`). Done when: three shards pass on a PR, the union of collected tests equals 2132 + 4 skipped, and a mutant removing one file from the shards turns the union count red.
P2: confirm test isolation before sharding or xdist: each estate harness takes a port (`estate_harness.py <port> <data> --secret`); verify the port is chosen free per fixture and not fixed. I did not check this. Unknown until checked.
P3: profile the 3.4 s floor in test_phase_g_check.py (one `--durations` run with `-p no:cacheprovider` and cProfile on one FAULT case); if it is a fixed sleep or poll interval inside tools/phase_g_check.py, a shorter configurable poll for tests could remove most of the 177 s without removing a case.
P4: look at the 16 s teardown in test_estate_probe.py (harness stop) and the 12.5 s outlier in test_phase_g_check.py.
P5: do NOT mark anything `slow` and skip it in CI: these tests are the mutants and FAULT cases that gate the tools; cutting them would weaken the gate.

## What I did NOT do
- Apply anything, run docker, or run the other suites (only `tools/tests`).
- Profile inside any test, or check port allocation (P2, P3).
- Repeat the run: one run, 553 s; a second run would show variance. Unknown.
