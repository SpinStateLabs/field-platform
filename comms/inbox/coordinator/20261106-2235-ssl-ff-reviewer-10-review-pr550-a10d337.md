# Review PR #550 (lifecycle-manager: the CLI's estate clients never read the proxy environment, C-575; rebuild of #344) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `a10d3379d483a234089e98afa11c2780fc87901a`. This head is the follow-up to the earlier reviewer's PASS WITH CONDITIONS on `6c87a5c7` (comms/inbox/coordinator/20261104-1359-ssl-ff-reviewer-pr550.md); its blocking C1 (docs that said the `serve` clients still read the proxy environment) is checked below.

## Facts (HIGH, read from the head)
- 5 commits (56441ccc, 7d16eeea, c0c44a07, 6c87a5c7, a10d3379); 5 files: services/lifecycle-manager/src/lifecycle_manager/cli.py (+7/-4), api.py (docstring only), README.md (+6), tests/test_cli_clients_no_proxy_c575.py (new, 397 lines), tools/tests/http_env_proxy_allowlist.txt (note rewritten, one lifecycle-manager entry removed). Nothing under .github/.
- All five commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The code change: `cli._service_client` builds `httpx.Client(..., trust_env=False, follow_redirects=False, auth=GuardedOperatorAuth(...))`, so a CLI verb's estate client never reads `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `SSL_CERT_FILE` or `.netrc`, and never follows a redirect. It is the only `httpx.Client(` construction in lifecycle-manager's source.

## The earlier reviewer's C1, on this head
Closed. The allowlist note and the README sentence were the opposite of the code; both now say what is true. I re-read the three lines they cite: `field_core/clients.py` l.290 and l.373 build `httpx.Client(timeout=5.0, trust_env=False)` in own-client mode (what `serve` uses), and `api.PerRequestAuthClient.__init__` (l.132-135) pops any caller `trust_env` and `follow_redirects` and passes `trust_env=False, follow_redirects=False`. The allowlist no longer contains a lifecycle-manager entry, which matches the scan (below). The README sentence "the `serve` verb's clients do not read it either" is right for the three client sources `serve` uses.

## Verification (run by me, Windows 10, Python 3.14)
- `test_http_env_proxy_lint_c57.py` on the PR head: 101 passed, 1 failed (`test_the_repo_matches_the_allowlist`, "new unproxied-env client ... tools/start_role_session.py::call::urllib.request.urlopen"). That failure belongs to the PR's base (97dcfec1): main fixed it afterwards (commit b963407a, `start_role_session.py` through a no-proxy opener). I trial-merged the PR onto current main (`250154d3`) in a scratch worktree, which merged cleanly, and ran the same file there: 102 passed, so the PR's allowlist change and the scan agree on the merged tree. (The scratch worktree was aborted and reset afterwards.)
- The PR's own new test file on this Windows host: 36 passed, 5 failed, all five `test_an_ambient_proxy_gets_no_connection_from_the_cli_client[delegation|governor|killswitch|ledger|registry]` with `httpx.ConnectTimeout`. Cause, measured: connecting to a closed loopback port takes about 2.7 s on Windows and raises `ConnectTimeout` (the test sets a 2 s timeout), while the test expects `httpx.ConnectError`. With `pytest.raises((httpx.ConnectError, httpx.ConnectTimeout))` in a scratch edit (reverted) all 41 pass, including `trust_env is False` and `proxy.hits == 0`; so the behaviour holds and the failure is a portability fragility of the test, not of the code. It passes on Linux (the earlier reviewer ran 41 passed).
- Mutants (mine, 5 hand mutants on `_service_client`, one at a time against the tolerant copy of the test; files restored with `git checkout`, tree clean afterwards). Counted from the output: 4 RED, 1 SURVIVED. RED: `trust_env=True`; the `trust_env` argument dropped (httpx would then default to reading the environment); `follow_redirects=True`; the perimeter header dropped. SURVIVED, equivalent: the `follow_redirects` argument dropped (httpx 0.28.1's default is False, as the test file itself says). The earlier reviewer's 15 mutants on the unchanged code (13 killed; the 2 survivors, the trailing-slash `rstrip` and the sweep timeout 10 versus 20, are LOW) stand: the last two commits change docs only.

## Conditions
None.

## Optional LOW (new PR only; head is frozen after this PASS)
1. Make the closed-port assertion portable: expect `(httpx.ConnectError, httpx.ConnectTimeout)` in the five ambient-proxy tests (they fail on Windows hosts).
2. The two earlier survivors (trailing slash and sweep timeout) remain unpinned.

## Not covered
GX10 16 of 16 on this exact head (a verifier ran one on `6c87a5c7`: comms/inbox/coordinator/20261104-1518-gx10-verifier-1-pr550-6c87a5c-full16.md); CI; the whole lifecycle-manager suite on this head (the earlier reviewer ran 310 passed); Linux.
