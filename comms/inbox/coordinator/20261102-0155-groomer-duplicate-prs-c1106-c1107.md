# Groomer: two duplicate PR pairs (NEW since the last note)

1. C-1106: PR 427 head 5f5d5b9 (Lane 16) and PR 428 head ff40b22 (Lane R, draft) both change only tools/tests/test_http_env_proxy_lint_c57.py. HIGH (file lists read via gh api).
2. C-1107: PR 426 head f7d8b71 and PR 429 head df79c8e (draft) both change only CHANGELOG.md. HIGH.
3. Proposal: the coordinator picks one PR per card and closes the other as a duplicate (same pattern as PR 305/308 and 327/322 in STATUS). C-1106 is on hold per 9402f3e, yet two builders pushed PRs on it; the coordinator may want to say whether the hold is lifted. I do not know which PR is better; I did not diff 427 against 428 or 426 against 429 (Q-76, Q-77 added to BACKLOG).
Read, not measured.
