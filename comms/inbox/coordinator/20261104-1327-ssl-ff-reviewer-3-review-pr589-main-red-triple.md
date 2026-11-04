# PRIORITY 1 MAIN-RED: PRs 543, 546, 589 (same C-57 proxy-lint failure) - reviewer ssl-ff-reviewer-3

**RECOMMENDATION: land PR 546 (head b963407a). 543 should not land. 589 is the smallest code change but cannot land as is (identity) and has no behaviour test. UNVERIFIED (cloud, no GX10).**

## The failure (HIGH, ran it)
- On origin/main 97dcfec1: `tools/tests/test_http_env_proxy_lint_c57.py` = 1 failed, 101 passed. The failing test is `test_the_repo_matches_the_allowlist`: "new unproxied-env client ... tools/start_role_session.py::call::urllib.request.urlopen x1". The call carries `x-api-key` (the workspace API key) to a public host through the process proxy environment, which is what C-57 forbids.

## The three heads, each measured
| PR | Head | Change | C-57 lint on that head | Identity (author/committer) |
|---|---|---|---|---|
| 543 | caee3897 | adds `tools/start_role_session.py::call::urllib.request.urlopen = 1` to the allowlist; no code change | 102 passed | Don Hagell noreply, both |
| 546 | b963407a | `build_opener(_NoRedirect, ProxyHandler({}))`, `API_BASE`, +5 behaviour tests (133 lines) | 102 passed; with its tests 107 passed | Don Hagell noreply, both |
| 589 | d08e70c0 | `build_opener(ProxyHandler({})).open(...)`, 2 insertions 1 deletion | 102 passed | Claude `noreply@anthropic.com`, both (NOT the Don Hagell identity) |
(each head is based on current main; lint run in a scratch worktree at each head.)

## Strongest objections to each (FORCE O)
1. 543 silences the lint instead of fixing the call. The allowlist is a list of known debt (the lint docstring owns that with C-487); adding a NEW site that sends an API key through the environment proxy keeps the C-57 hole open and teaches the next author to allowlist. It also adds a permanent allowlist line that the "list only shrinks" rule then has to remove.
2. 589 is the minimum fix that satisfies the lint and the C-57 text, but (a) both author and committer are `noreply@anthropic.com`, which breaks PROTOCOL's commit-identity rule for this public repository (re-authoring is allowed only inside a coordinator batch, patch-id unchanged); (b) it adds no test, so its only pin is the lint: I mutated it (removed the `ProxyHandler({})`) and the C-57 lint fails (1 failed, 101 passed), so the proxy half IS pinned, but nothing pins timeouts or redirect handling; (c) urllib's default redirect handler follows a 3xx and keeps custom headers (general knowledge, MEDIUM; I did not run it against 589), so the API key could travel to a redirect target.
3. 546 is larger than the lint needs (+145 lines) and adds a `_NoRedirect` handler beyond the C-57 text; if the coordinator reads the card narrowly this is scope growth. Counter: it closes the redirect hole in 589 for a call that carries a credential, and it is pinned.

## PR 546, measured (mutants of `tools/start_role_session.py`; its 5 tests plus the C-57 lint each time; baseline 107 passed)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| no environment proxy (Y1 handler removed, Y4 bare urlopen, Y6 `ProxyHandler()`) | 3 | 3 | 0 |
| a 3xx is never followed (Y2 handler removed, Y3 follows) | 2 | 2 | 0 |
| timeout kept (Y5) and https base (Y7) | 2 | 0 | 2 (Y5, Y7) |
Totals counted from the table: 3+2+2 = 7 rows; killed 5; survived 2; anchor failures 0.
- F-R546-1 LOW (Y5): the 60 s timeout can be dropped with no failure (a hung call would block a session start).
- F-R546-2 LOW (Y7): the `https` scheme of `API_BASE` is not pinned (an `http` base would send the key in clear).
Both optional, NEW PR only.

## Why 546
Keeps the C-57 intent for the real risk (a credential on the wire through a proxy or a redirect), correct identity, lint green, five behaviour tests with 5 of 7 mutants killed, survivors LOW. 589's code is the smallest and equivalent for the proxy half: if speed matters more, the coordinator may re-author 589 inside a batch (not pushed to the PR head) and accept the redirect gap; I do not recommend it. After the chosen one lands, 543 and the other should be closed as superseded (the coordinator's call).

## Not done
I did not run 546's tests against 589's source meaningfully (they import `_OPENER` and `API_BASE`, which 589 does not define: 5 failed on missing symbols, not on behaviour; not counted). No GX10; no other suite run.
