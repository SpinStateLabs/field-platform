# Builder Lane 12: C-1162 test baseline (corrects the earlier note)

Head 7088c48225711531a112bcd3ec8c0cd86e2512d8 (PR 453).
On the head, 7 dependent files: 16 failed, 446 passed (the earlier "89 errors" came from test_phase_g_check.py, which needs service packages not installed on this box; not re-run).
On main 05942b98, the 4 files holding all 16 failures (test_ledger_observer_estates_c6, test_operator_plumbing, test_deploy_docs, test_gb10_required_posture): the same 16 failed (HIGH, measured). So none is caused by PR 453; they are this box (missing packages or environment), not a regression. test_gb10_caddy_tls.py: 47 passed on the head. 16 suites: not run (GX10).
