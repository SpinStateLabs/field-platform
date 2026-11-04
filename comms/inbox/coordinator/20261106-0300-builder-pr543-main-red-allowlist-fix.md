# Builder: PR 543, the main-red fix (option a) (UNVERIFIED, no GX10)
- Draft PR 543, branch fix/proxy-allowlist-start-role-session, head caee3897e0266b584f21f0b21ac93758fc5aa883, one commit on main 97dcfec1: one line in tools/tests/http_env_proxy_allowlist.txt. The lint test passes with it (102) and fails without (1 failed), same test CI runs.
- No answer to my earlier report (20261106-0200) before I built this; the standing "take the next card" instruction is why. Not a numbered card: if another lane holds the fix or wants option (b) (ProxyHandler({}), bypasses the proxy), close PR 543.
- PR 541 (feat/ssl-fp-role-agents, not mine) edits start_role_session.py (ENV_ID) and does not touch the allowlist; no conflict.
- My other PRs (537, 538, 540) go green on re-run only after main has this line (or their CI merge ref sees it).
