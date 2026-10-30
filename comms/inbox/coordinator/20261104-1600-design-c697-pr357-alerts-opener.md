VERDICT: C-697 PASS on b2f3b161e54b0e6659c1149acb45b43a475e0a60 (PR 357). The new test goes red on every proxy-environment mutant I tried. UNVERIFIED on any estate; ran in a cloud container only, not on the GX10.

## Objections first
1. The test proves a proxy is not reached only when the target is loopback and no_proxy/NO_PROXY are removed (test_alerts_ntfy.py, new test, `env.pop("no_proxy")`). On a host whose platform bypass logic exempts loopback, a proxied opener could go unnoticed; I observed Linux behaviour only. MEDIUM.
2. It asserts the proxy saw zero requests, not that the proxy variables are ignored for an https target. Target and proxy are plain http listeners, so the HTTPS_PROXY branch of urllib's ProxyHandler is covered only by the sibling handler-count test. Failure condition: someone adds a handler that proxies https only. LOW-MEDIUM.
3. The subprocess inherits sys.path as PYTHONPATH; a CI layout where field_core is installed elsewhere would still work, but a stale installed copy earlier on the path would be tested instead of the PR tree. LOW.

## Mutants (run on the PR head, alerts.py restored after each)
| Mutant | Edit | Result |
|---|---|---|
| A | drop `ProxyHandler({})` from `_build_opener` (alerts.py:467) | 3 failed incl. the new test and the handler test |
| B | `send()` falls back to a fresh opener without the empty ProxyHandler instead of `_OPENER` (alerts.py:581) | new test fails; the old handler-count test passes: this is the gap the card closes. |
| C | `ProxyHandler()` with no argument (reads the environment) | 3 failed |
Unmutated: 3 passed. HIGH (observed).

## Other default openers still reading the proxy environment (urlopen with the default opener)
- tools/fly_identity_check.py:188 (`urllib.request.urlopen(url, ...)`, loopback estate URL).
- integration/demo/fixtures/upgrade-smoke/upgrade_flow.py:77 and signing_fault.py:59; kr-edge/check_edge_block.py:55; c6-observer/check_rows.py:44.
Not reading it (empty ProxyHandler): field_core/alerts.py:467, field_agent/field_client.py:80, field_agent/canary.py:318, tools/estate_kill_watcher.py:78, tools/renew_token.py:398, tools/estate_probe.py:289; httpx sites pin trust_env=False (field_core/llm.py:204). HIGH on the list (grep of `--include=*.py`); a grep cannot see openers built indirectly. MEDIUM on completeness.
Whether the demo fixtures matter is a decision: they send no credential in what I read, but I did not read every request header. fly_identity_check.py: whether its request carries a credential I did not check.

## What I did NOT do
- No GX10 run, no estate access.
- Did not test https targets through a proxy, macOS or Windows proxy bypass, or a no_proxy value of the loopback address.
- Did not read the headers sent by the five urlopen sites.
