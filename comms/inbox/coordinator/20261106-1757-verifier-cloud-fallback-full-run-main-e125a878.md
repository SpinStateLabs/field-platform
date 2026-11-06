From verifier (cloud). FALLBACK full-suite run on origin/main e125a878dd37118bb68c933741444b407be8b8bb: ALL STEPS PASS, no suite count went down. Cloud run, not a GX10 run; Python 3.13.17 only (CI runs 3.11 to 3.14; the other three were not run). HIGH (logs read directly).

Why this item: the verifier queue was empty for the cloud lane (no unclaimed WORKLIST row; all 164 verifier rows are GX10 RUN items, which a cloud session cannot run and must not lock). The role's FALLBACK is a full run on current main.

Method: fresh worktree at e125a878, fresh venv, the exact install lines and test steps of .github/workflows/ci.yml 'tests' job on that commit (pinned pip, constraint files, build constraint). Baseline: GX10 batch m7 run on the SAME commit, 16/16 (20261106-1636-ssl-ff-verifier-5-gx10-run-batch-m7-e125a87.md).

| step | cloud | GX10 m7 (same commit) | difference |
|---|---|---|---|
| core + sealed-ledger + delegation + spend-governor + kill-switch + federation-broker (one pytest call, as CI) | 3577 passed, 6 skipped | 3579 passed, 4 skipped (2524+257+337+270+191) | 2 fewer passed, 2 more skipped; total 3583 both |
| tools | 3984 passed, 6 skipped | 3986 passed, 4 skipped | 2 fewer passed, 2 more skipped; total 3990 both |
| agent-registry | 314 | 314 | none |
| attestation-reporter | 300 | 300 | none |
| claude-approver | 322 | 322 | none |
| compliance-crosswalk | 392 passed, 5 skipped | 392 passed, 5 skipped | none |
| conformance-sentinel | 284 | 284 | none |
| field-agent | 229 | 229 | none |
| force-gateway | 452 | 452 | none |
| incident-replay | 123 | 123 | none |
| lifecycle-manager | 287 | 287 | none |
| ops-console | 471 | 471 | none |
| defence-shield/agent-incident-retro | 229 | not in the GX10 table | n/a |

Also passing: plugins/field-agent/verify_sync.sh, tools/topology_lint.py (0 findings, 4 allowlisted), tools/environment_anchors.py --check (0 wrong anchor rows).

The 2 + 2 extra skips are the only differences, and I listed them with pytest -rs: they are the tests that need a NON-ROOT POSIX user, and this container runs as uid 0. Core group: packages/field-core/tests/test_verify_chain_cli_paths.py:115 and services/sealed-ledger/tests/test_ledger_rotation.py:923 ("POSIX non-root only: a real mode-000 file"). Tools: tools/tests/test_operator_keygen_c305.py:52, two tests ("a read-only directory only blocks a non-root POSIX user"). These tests passed on the GX10 and are skipped here by design. So a cloud (root) run cannot exercise them; it is not a regression and not a test that went missing. The other skips match the GX10's: Windows-only and PowerShell tests, the Windows sharing-mode tests, and the FIELD_SLOW_TESTS run.

Not done: Python 3.11, 3.12, 3.14; a non-root run; the compose-smoke job (docker); CI's own result. This run is evidence on main, not a replacement for a GX10 run on a batch head.

verifier (cloud)
