# Verifier 3: full 16-suite run, PR 609 "rebuild of #473" head 41379dc (docs: ROADMAP/STATE MERGE 20, C-1184): 15/16, tools 1 failure = c57 lint, stale base
Head 41379dcb0dbac59bd60c1f76fd7399abfd7b01ba (equals open PR head at run start). At the end of the run main is b963407 (has the PR546 c57 fix) and this head is 1 commit behind it (HIGH). GX10 ~/ff-work/wt-pr609-v3, log ~/ff-work/pr609-v3-all.log. Full 16-suite run.
- tools: 1 failed, 3800 passed, 4 skipped. Isolated test_http_env_proxy_lint_c57.py on this head: 1 failed, 101 passed (same single failure; name not read from the full-run log; MEDIUM). Same cause as PR587/576/616 reports (start_role_session.py unproxied urlopen; fixed on main by PR546, which this head predates). PR diff = ROADMAP.md + STATE.md only (docs), so it cannot cause it.
- Action: rebase onto main b963407, re-run tools. Not re-run on a rebased tree; not verified green.
- core+sealed-ledger 2350 passed, 4 skipped; field-agent 207
- agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
No TEST_DATABASE_URL set by runbatch.sh.
