# Builder B-REBUILD-PR467: rebuilt as draft PR 577

Head of new branch rebuild/pr467-sentinel-operator-pair: 9cf70b92 (old PR 467 head ea8857b7, untouched). UNVERIFIED (no GX10).
- Cherry-picked both commits onto current origin/main, no conflicts. Range-diff: both commits `=` (identical patches), so nothing beyond the rebase.
- Ran: environment_anchors.py --check (0 wrong); the four tools tests: 260 passed, 1 failed = known baseline test_http_env_proxy_lint_c57 (tools/start_role_session.py, PR 543), nothing from this change; services/conformance-sentinel/tests/test_per_request_headers_c1180.py 17 passed.
- NOT run: full conformance-sentinel suite, GX10 16/16 on the new head. No mutant (rebuild, not a bug fix).
- Decision: coordinator to review/merge 577 and close 467 as superseded.
