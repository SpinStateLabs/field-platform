# builder-N3: queue EMPTY again, fallback scan (proposal only)

`dispatch.sh next builder` EMPTY; `level`: builder, reviewer and verifier all 0 (RESTOCK). Restock-needed reports from other roles are already filed, so I file none of my own. Last WORKLIST.tsv change on comms was about 4 hours ago.
Done by builder-N3 this session: PRs 577 (rebuild of 467), 588 (S2-1), 636 (S3-14), 643 (S3-21); 443 released as superseded. All four test jobs on 577 and 588 are red only on the known test_http_env_proxy_lint_c57 baseline (PR 543); one comment each filed.

FALLBACK scan, packages/field-agent/src: functions no test names (word match over tests/): usage.extract_usage, agent.report_usage_from, canary._env_float, field_client.status_of and _private_host, agent._resolve_token (+ private helpers).
PROPOSAL (test gap, size S, MEDIUM): tests/test_extract_usage.py for usage.extract_usage + Agent.report_usage_from. Probe on main (read+run):
- dict and SDK-object responses map cache_read_input_tokens to cache_read_tokens; missing usage/model or missing input/output tokens raise ValueError (documented).
- Pin as current behaviour, report as findings: negative counts pass through (the governor 422s them later, so it fails loud); True becomes 1; "7" becomes 7; 3.9 becomes 3 (truncation counts LOW, against the governor's never-count-low rule; the real API sends ints, so reachability unknown); NaN raises ValueError.
- If the truncation or the bool/negative pass-through is judged wrong, the fix is a separate card.
Also: canary._env_float: float("nan") or "abc" in FIELD_CANARY_WORK_EVERY crashes CLI start with ValueError (not probed further).
I will build the extract_usage test once a restock does not name other work (ROLE-LOOP). Evidence is read plus one probe, not a measured run of any new test.
