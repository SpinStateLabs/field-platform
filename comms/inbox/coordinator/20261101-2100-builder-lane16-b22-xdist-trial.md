# Builder Lane 16: B-22 pytest-xdist trial on the GX10 (tools/tests): same result every time; no CI change made

Measured on the GX10, main at 9468b184 (the head after batch cb12), `pytest -q tools/tests`, CI=true, pytest-xdist 3.8.0 + execnet 2.1.2 installed with `pip --target` into a private directory and put on PYTHONPATH (the shared test venvs were not changed; xdist is not in the CI install or in integration/ci-constraints.txt, so any CI use is a CI change plus a pin). HIGH confidence for the numbers (run logs).

| Run | Passed | Skipped | Failed | Wall |
|---|---|---|---|---|
| `-n auto` (20 workers) run 1 | 3523 | 3 | 0 | 56 s |
| `-n auto` run 2 | 3523 | 3 | 0 | 56 s |
| `-n auto` run 3 | 3523 | 3 | 0 | 56 s |
| `-n auto` again, with skip reasons | 3523 | 3 | 0 | 53 s |
| `-n 2` (CI-runner-like) | 3523 | 3 | 0 | 293 s |
| serial, same main | 3523 | 4 | 0 | 510 s |

Same pass count (3523) and no failure in all six runs, so the card's test ("same result each time") is met for `-n auto`. Speed-up on this host: 9x with 20 workers, 1.7x with 2 workers (CI runners have about 2 vCPUs and different disks, so treat the 2-worker figure as the guide, not the 20-worker one).

## The skip count differs by one (3 under xdist, 4 serial): explained, not a test difference
`test_ssl_renewal.py:50` is a module-level `pytest.importorskip("msvcrt")`. `test_harness_wait_honoured.py:30` does `import test_ssl_renewal`, so on Linux that whole module (9 tests defined) is skipped at collection too, with the skip location reported as test_ssl_renewal.py:50. Serially it is counted twice, under xdist once. I confirmed that each file alone shows one skip in both modes and that the other two skips (test_field_rest_secret.py:41, test_proxy_url_required_c285.py:58) are identical in both. The xdist de-duplication itself I inferred, not proved (MEDIUM). Separate observation: test_harness_wait_honoured.py never runs on Linux or the GX10 or CI because of that import (only on Windows with PowerShell); not changed here.

## Shared temp dirs, ports and cwd (static survey of the 57 test files, then confirmed by the runs)
- Ports: every real server binds port 0 (ephemeral): test_estate_kill_watcher, test_estate_probe, test_field_rest_secret, test_job_grantors_c13, test_operator_cli_c2, test_renew_token, test_ssl_renewal, test_upgrade_smoke_fixture. The literal 80xx numbers in test_deploy_docs, test_fly_identity_c5, test_ledger_observer_estates_c6 and test_topology_lint are inside strings that are parsed or asserted, not bound. No fixed-port collision seen in 4 xdist runs.
- Temp dirs: no `mkdtemp` or `gettempdir` use found; the `/tmp/...` and `/home/spinner/.field-local/...` strings (test_compose_static_pins, test_compose_resolved_bind_c512) are parametrised path text for lint checks. I did not trace every file for writes under the home directory (not verified).
- cwd: one `monkeypatch.chdir` (test_operator_keygen_c191.py:75), restored per test; each xdist worker is its own process.
- Timing: the timing-sensitive kill-watcher test (a 1 s timeout asserted under 4.0 s) did not fail in 4 xdist runs at 20 workers; it failed once in an earlier concurrent run on a loaded Windows host (C-774 note). Heavier parallelism on a small runner could expose it (not tested).

## Not done / for the coordinator
- No CI change, no ci-constraints pin, no `-n` in any workflow (B-22 says before any CI change). PR 421 (two shards per Python version) already attacks the same wall time; xdist could replace or stack on it, a design choice not tested here.
- Not run: 3.11/3.12/3.14, a loaded-runner stress at `-n 2`, repeated runs at `-n 2`, the services' own suites under xdist (conftest-sensitive, `tests.conftest` imports).
- Mistake already reported earlier today: the pr414b worktree incident (20261101-1800 note). This trial used only l16-named paths (wt-l16xdist, l16-xdist-site, l16-*.sh).
