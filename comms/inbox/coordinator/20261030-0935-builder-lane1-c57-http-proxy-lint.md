# Builder Lane 1: C-57 PR 295 ready for a reviewer card (UNVERIFIED on the GX10)

- PR 295 (draft), branch `test/http-env-proxy-lint-c57`, exact head `b47ee05cd97947aebd738cd26c2406bcf1de9ca3`, one commit on main 3ee2e5d. Tests only: new `tools/tests/test_http_env_proxy_lint_c57.py` and `tools/tests/http_env_proxy_allowlist.txt`; no source file changed.
- Scan: httpx calls without `trust_env=False`, `urllib.request.urlopen`, `build_opener` without `ProxyHandler({})`, over non-test Python. Allowlist = today's sites: 58 keys, 63 sites (card said about 59 httpx plus urllib sites). The list must equal the scan, so it can only shrink (C-56).
- Tests: 21 in the new file. Mutants 10/10 red (listed in the PR body). Whole `tools/tests` suite: 2828 passed, 6 skipped (Python 3.13, cloud).
- NOT run: GX10 16-suite set; CI not read yet. Pushed on Don's explicit go.
- Please judge: (1) the allowlist key is path::function::call, so renaming a function makes the entry stale (fails loudly, on purpose); (2) the scan does not see `requests`, `http.client` or calls through a variable alias of a client; the reviewer's C-55 table lists http.client use in phase_g_check as safe.
- Also: C-451 (my follow-up for PR 288) is built and committed locally on PR 288's head; waiting for PR 288 to merge before I rebase and push. PR 291 follow-ups (P1 hatchling build pin, P2 whole-workflow scan) wait for your cards; I did not touch its head, only corrected its title and body to say "runtime installs".
