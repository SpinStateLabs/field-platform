# C-975 reviewer report (Lane 5): post-merge verification of main acaf5f2 (batch CA: PRs 290, 319, 328), GX10 full set

VERDICT: PASS on acaf5f241f00754442c7adbbb0290769dbfe52c5 (main per `gh api .../commits/main` at review time). Clean GX10 worktree of that exact sha fetched from GitHub (`git status --porcelain` empty before and after; HEAD re-checked after the runs). All 16 batch-layout suites green with counts IDENTICAL to the batch CA run (8448 passed, 13 skipped, 0 failed; difference 0 on every suite); the CI-exact combined step, defence-shield, topology lint and the field-agent template sync also green. Compose resolved check on a model derived from the shipped files: clean on every shipped combination, refuses the three hostile overrides (exit 2), exit 3 on an unreadable model. External-reference guard (ci.yml:313) against the shipped console page: no hit (grep status 1). No failure, so nothing to re-run for flakiness. Python 3.12 only (CI matrix is 3.11 to 3.14). Class and file:line only.

OBJECTIONS FIRST (what could make this green misleading)
1. F-C975-1 LOW: the baseline is the batch CA run on the SAME sha (acaf5f2 was fast-forwarded to main), so "difference 0" proves reproducibility on a second venv and a fresh clone, not new coverage. The meaningful delta is against the previous main 5777030: tools/tests collects 3136 there and 3256 here, +120 = 31 (tools/tests/test_ci_external_ref_guard_c101.py, PR 319) + 89 (tools/tests/test_compose_resolved_bind_c512.py, PR 328); PR 290 is docs and adds 0; tools/tests/test_compose_static_pins.py changed (-33 lines, rules moved to tools/compose_bind_rules.py) and still runs 640. No other suite's files changed (diff 5777030..acaf5f2: 9 files, only tools/, ci.yml, docs, tasks). [HIGH, run]
2. F-C975-2 LOW (correction to the card's premise): ci.yml on main has NO `-rs` and NO skip-count assertion (grep of .github/workflows/ci.yml for `-rs`, `skip`: no such step; the only skip text is the comment at ci.yml:68). There is no CI skip budget to compare with; a new skip would pass CI silently. All 13 skips here are environment gates (list below); the code behind them (Windows/PowerShell paths, msvcrt branch, the 100k served-latency run, live crosswalk fetch) is NOT exercised on the GX10 and, for the Windows ones, not on CI's Linux runners either. [HIGH, read and run]
3. F-C975-3 LOW: the batch's "16 suites" (runbatch.sh layout) is not CI's `tests` job: it omits defence-shield/agent-incident-retro (ci.yml:91), the topology lint (ci.yml:82) and the template sync (ci.yml:51), and splits the repo-root step (ci.yml:58-62) into per-service runs. I ran both layouts: the CI-exact combined step is 2644 passed, 4 skipped = 1924 + 213 + 242 + 160 + 105 (no cross-conftest interference), defence-shield 229 passed, topology lint OK (0 findings, 4 allowlisted, "entrypoint behavioural check: RAN"), templates in sync. A batch log that says "16 suites, 0 failed" therefore does not by itself cover the whole CI job. [HIGH, run]
4. F-C975-4 LOW-MEDIUM (known, reproduced): the external-reference guard does not catch a srcset entry after a comma with no space: a fixture `<img srcset="a.png 1x,https://x.example/b.png 2x">` gives grep status 1 (no hit); `<img src="https://...">` gives status 0 (hit). This is F-C593-1, accepted as non-blocking in the CA packet; still true on main. I did not check whether a follow-up card exists. The guard is also only an accident guard (ci.yml:294-302 says so). [HIGH, run]
5. F-C975-5 LOW: the compose resolved check was run on a MODEL derived from the shipped files by my scratch script, not on real `docker compose config` output (no docker on the GX10 by rule). My model handles `${V:-d}`, `${V-d}`, `${V:?m}`, `!override`/`!reset`, relative paths against integration/demo and volume merge by target; real compose may normalise differently (e.g. short-syntax `~`, project-directory flags). The shipped files carry no env_file, top-level secrets/configs or driver_opts.device, so those branches of check_model (tools/compose_resolved_check.py:115-127) are exercised only by the PR's unit tests, not by shipped data. [HIGH, run]
6. F-C975-6 LOW: tools collect-only reports 3256 tests; the run reports 3255 passed + 4 skipped = 3259. One is explained (module-level `pytest.importorskip("msvcrt")`, tools/tests/test_field_rest_secret.py:41, counts as a skip but is not collected); the other 2 I don't know (probably tests generated at run time). Same on the batch run, so not a regression. [MEDIUM]

ASSUMPTIONS
1. Baseline: comms/inbox/coordinator/20261106-2010-assistant-ready-ca.md (comms tip 8027c2a), section "GX10 (run ca, exact head)", corroborated by the batch's own log ~/ff-work/ca-all.log on the GX10 (same numbers). [HIGH]
2. The batch ran with venv-fp, I ran with venv-fieldrev; both Python 3.12.3, pytest 9.2.0, and `field_core`/`sealed_ledger` import from MY worktree (verified with `__file__`). CI=true, the secret/flag variables unset, PYTHONPATH from the worktree's src directories. [HIGH, run]
3. "Suite" = one pytest invocation as in runbatch.sh, so counts compare one to one. [HIGH]

REASONING
1. Worktree: fresh clone from GitHub (objects borrowed from a local seed with --reference), checkout acaf5f2, porcelain empty. Load 1.6 to 2.5 throughout (under 6). Logged background run (setsid nohup) with `-rs`; scratch files all prefixed l5-c975-. [HIGH, run]
2. Per-suite results (passed / skipped / failed; baseline = batch CA; difference):

| suite | passed | skipped | failed | baseline | difference |
|---|---|---|---|---|---|
| core+sealed-ledger | 1924 | 4 | 0 | 1924 / 4 | 0 |
| tools | 3255 | 4 | 0 | 3255 / 4 | 0 |
| field-agent | 153 | 0 | 0 | 153 | 0 |
| agent-registry | 304 | 0 | 0 | 304 | 0 |
| attestation-reporter | 135 | 0 | 0 | 135 | 0 |
| claude-approver | 282 | 0 | 0 | 282 | 0 |
| compliance-crosswalk | 353 | 5 | 0 | 353 / 5 | 0 |
| conformance-sentinel | 260 | 0 | 0 | 260 | 0 |
| delegation-authority | 213 | 0 | 0 | 213 | 0 |
| federation-broker | 105 | 0 | 0 | 105 | 0 |
| force-gateway | 447 | 0 | 0 | 447 | 0 |
| incident-replay | 91 | 0 | 0 | 91 | 0 |
| kill-switch | 160 | 0 | 0 | 160 | 0 |
| lifecycle-manager | 224 | 0 | 0 | 224 | 0 |
| ops-console | 300 | 0 | 0 | 300 | 0 |
| spend-governor | 242 | 0 | 0 | 242 | 0 |
| TOTAL (16) | 8448 | 13 | 0 | 8448 / 13 | 0 |
| extra: CI combined step (ci.yml:58) | 2644 | 4 | 0 | none (sum of 5 suites above) | n/a |
| extra: defence-shield (ci.yml:91) | 229 | 0 | 0 | not in batch | n/a |
| extra: topology lint (ci.yml:82) | OK, 0 findings, 4 allowlisted | | | not in batch | n/a |
| extra: verify_sync (ci.yml:51) | templates in sync | | | not in batch | n/a |

   Totals computed: 1924+3255+153+304+135+282+353+260+213+105+447+91+160+224+300+242 = 8448; skips 4+4+5 = 13. [HIGH, run]
3. Skip reasons (all environment gates): sealed-ledger test_ledger_latency_100k.py:171 (FIELD_SLOW_TESTS), test_ledger_retention.py:687 and test_ledger_rotation.py:413, :936 (Windows sharing semantics); tools test_field_rest_secret.py:41 (Windows PowerShell), test_ssl_renewal.py:50 x2 (Windows PowerShell), test_proxy_url_required_c285.py:58 (no PowerShell); compliance-crosswalk test_pins_c253.py:231 x2 and :244 x2 (msvcrt branch), test_regwatch.py:892 (live fetch gate). Same 13 as the batch. [HIGH, run]
4. Named tests (separate runs on the same tree): pip pins test_ci_pip_pins_c23.py 16 passed; ENVIRONMENT doc test_environment_doc.py 48; runbook pins test_runbook_pins_c465.py 8; static compose pins test_compose_static_pins.py 640; guard tests test_ci_external_ref_guard_c101.py 31; resolved check tests test_compose_resolved_bind_c512.py 89; with renew-token pins, deploy docs, workflow security lint and YAML duplicate keys the ten files together: 1085 passed. [HIGH, run]
5. Strict YAML: every workflow under .github/workflows (one file, ci.yml) loads under a SafeLoader that raises on duplicate mapping keys: OK, 4 jobs. [HIGH, run]
6. Compose resolved check (model derived from the shipped files, tools/compose_resolved_check.py run as a CLI with --repo-root = the worktree): base alone (15 services, 14 binds) exit 0; base+gb10 (20 services, 29 binds, 19 build contexts) exit 0; base+gb10+gb10.required with placeholder posture values exit 0; base+gb10 with --realpath exit 0; FIELD_CALLER_KEYS_DIR=/etc, FIELD_OPERATORS_DIR=a home directory, CLAUDE_APPROVER_SECRETS_DIR=a home .ssh: each exit 2 with the expected REFUSED line; unparseable model and missing file: exit 3. [HIGH, run; model caveat F-C975-5]
7. External-reference guard: the exact grep line from ci.yml:313 extracted verbatim, run on services/ops-console/src/ops_console/static/console.html flattened with `tr '\n' ' '` as the step does: status 1 (no hit). The page is served verbatim (services/ops-console/src/ops_console/api.py:287-289 reads the file unchanged), so the static file is what the step would see. The five presence greps of ci.yml:305-310 that apply to the HTML all match. Positive control: `src="https://..."` is caught (status 0). [HIGH, run]
8. Flakiness: no failure in any run, so no re-runs were needed. [HIGH]
9. Afterwards: `git status --porcelain` empty (only ignored caches), HEAD still acaf5f2; the temporary base worktree (5777030) used for the collect-only delta was removed and pruned. [HIGH, run]

CONCLUSION
PASS on acaf5f241f00754442c7adbbb0290769dbfe52c5: main reproduces the batch CA GX10 run exactly (8448 / 13 / 0 over 16 suites), the PR 319 and PR 328 test additions account for the whole tools delta from the previous main (+120), and the CI-only pieces the batch layout omits are green too. Proposed cards (coordinator numbers them): P1 builder LOW, ci.yml: add `-rs` and a per-step skip-count ceiling (today 4 tools, 4 combined step) so a new skip fails CI (F-C975-2); P2 coordinator LOW: make the batch script mirror ci.yml's `tests` job (add defence-shield, topology lint, verify_sync) so "16 suites" means the CI set (F-C975-3); P3 builder LOW-MEDIUM: close F-C593-1 (srcset entry after a comma without a space) if no card exists (F-C975-4).

What I did NOT do: run docker or compose (the resolved check ran on a derived model, not real `docker compose config` output); run CI or the three docker CI jobs (compose-smoke, fly-image-smoke, compose-upgrade-smoke); run Python 3.11, 3.13 or 3.14; Windows; mutants; check whether follow-up cards for F-C593-1 or the C-585 conditions exist; explain the 2-test collect-versus-run gap (F-C975-6); write to comms, comment, push or merge.
