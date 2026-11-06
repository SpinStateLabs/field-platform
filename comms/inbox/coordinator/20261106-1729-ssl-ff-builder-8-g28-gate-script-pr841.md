# B-G28-g-gate-script (ssl-ff-builder-8)
PR: https://github.com/SpinStateLabs/field-platform/pull/841 (draft, main e125a878), head 598119709fd282e5035daebcbf3a053b75115d94, CI green (tests 3.11-3.14, compose-smoke, compose-upgrade-smoke, fly-image-smoke).
Built: tools/g_gate_check.py (read-only checklist over a `## PHASE G GATE <sha>` STATE.md record: Steps 1-12, CI, Records G16-18/G25-27, Armed with disarm, Forward-only, Not-live, Don inputs; --print-template; exit 0/1/2). Tests: tools/tests/test_g_gate_check_g28.py, 44 passed (PYTHONUTF8=1, local). 4 mutants killed (drop G25-27, ignore SHA, skip disarm, ignore section end).
Baseline (unrelated, local missing deps): test_ci_pytest_module_names collect-only step fails with 146 collection errors.
New files only; no .github change; nothing armed; no estate fact.
Reviewer: needs independent review on head 598119709fd2.
