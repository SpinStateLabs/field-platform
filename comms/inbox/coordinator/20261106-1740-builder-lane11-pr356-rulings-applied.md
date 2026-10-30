# Builder Lane 11: PR 356 rulings applied (head 2958366)

- Don's answers (2026-11-05, asked in the session): (1) refuse inet_aton short forms everywhere; (2) refuse `metadata` and `metadata.google.internal`; (3) keep accepting IPv6 scope ids.
- PR 356 head 29583669dd88188e5f945faeffcaab04d5184212 (on a9be069; no force-push). GX10 (wt-c880, runbatch c880): 16 "== " suites, 0 failed or error lines (core+sealed-ledger 2036, tools 3300).
- Built: hosts.py (non-canonical numeric spelling refused before the name rule; METADATA_NAMES), the three stdlib copies lose the inet_aton normalisation, tests flipped on purpose (test_hosts_c489, test_llm_c117: `0x7f000001`, `2130706433`, `0x7f.1`, `0xa000001` now refused), renew_token.py runbook pins (token-renewal.md x4) moved to the new hash.
- Effect on PR 368: the MCP corpus case `http://127.1` and its nine siblings now agree with core (the C-880 C1 red test should go green on a scratch merge: not re-run by me, not verified).
- Mutants (red): short forms accepted again; metadata allowed; a copy accepting short forms.
- Reviewer attack: any caller that passes a short form on purpose (grep config defaults and demo env files for `0x7f`, `127.1`: I did not scan non-Python files); the metadata deny-list is exactly two names (no `instance-data`, `metadata.goog`), per the ruling.
- Not verified: Python 3.11/3.13/3.14; GitHub CI; the PR 356 + PR 368 merge.
