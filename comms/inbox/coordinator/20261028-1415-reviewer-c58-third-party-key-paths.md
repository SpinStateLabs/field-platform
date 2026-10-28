# C-58: secrets handling in the third-party-key paths (teammate-don-reviewer, 2026-10-28)

main c8ecba7. Probe on the GX10 (~/ff-work/probe58.py): DUMMY key `sk-ant-DUMMY-PROBE-KEY-0123456789`, a local fake upstream, no real key and no network; all loggers at DEBUG captured (httpx/httpcore included). Each path was driven through three upstream behaviours: (a) 401 whose JSON body ECHOES the request headers (worst case), (b) connection refused, (c) 200 non-JSON body that echoes the headers. For each I searched the returned value, the raised exception, its full traceback and the captured log text for the key.

## Results
| Path | (a) echoing 401 | (b) refused | (c) non-JSON echo |
|---|---|---|---|
| force-gateway api.py:114-135 `real_upstream` | KEY IN RETURNED BODY | clean | clean |
| force-gateway hygiene_judge.py:99-160 `AnthropicHygieneJudge.judge` | clean | clean | clean |
| conformance-sentinel judge.py:126-190 `AnthropicJudgeClient.judge` | clean | clean | clean |
| compliance-crosswalk suggestions.py:158-196 `AnthropicSuggester.suggest_one` | clean | clean | clean |
| claude-approver core.py/client.py | NOT PROBED (the `anthropic` SDK is not installed in my venv): read only | | |

## Findings
1. MEDIUM-LOW (conditional, PROVEN under the worst case): `real_upstream` returns `(resp.status_code, resp.json())` and the gateway hands that body to the calling agent unfiltered (api.py:114-135, call sites ~805, ~834, ~847). If the upstream ever echoes the request headers (a rogue or debugging `ANTHROPIC_BASE_URL`, a header-echoing proxy), `x-api-key` reaches the agent and whatever telemetry stores the response. Real Anthropic does not echo. The enabling condition is configuration, not an attacker, but the gateway is exactly the component whose job is to keep that key from agents. Fix: allow-list the response fields the gateway returns (id, type, role, model, content, stop_reason, usage, error.type/message), or at least scrub any string containing the key before returning or storing; add a test with this fake upstream.
2. LOW: `ANTHROPIC_BASE_URL` has no scheme or host check (api.py:~125: `os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")`). `http://` or a non-Anthropic host receives `x-api-key` in clear. Same pattern as #56's https-only rule. Require https (loopback http only in tests) and warn on a host other than api.anthropic.com.
3. LOW: the three client classes build `f"judge upstream unreachable: {exc}"` (hygiene_judge.py:135, judge.py:161) and ledger/return it in verdict reasons. For httpx transport errors `str(exc)` carries the request URL; a base URL with userinfo (`https://user:pass@host`) would leak that secret. The key itself never appears (headers are not in exception text; probe clean). Use the class name only, as claude-approver does.
4. CLEAN by probe and by reading: no key in a log line (httpx logs the URL and status only), exception text, traceback, or return value of the three judge paths, including when the upstream echoes headers (they return only status codes and fixed strings: `judge upstream returned 401`).
5. claude-approver (reading only, UNVERIFIED by probe): the key comes from a mounted file read per call (`read_api_key`, config.py:77); errors are labelled by class name and status only (`_exc_label`, core.py:102-107; the comments at :325 forbid `str(exc)`); a grep of the package finds no `str(exc)`, `{exc}`, `exc_info` or `log.exception`; the key is compared by `hash(key)` in memory only. Good pattern; the other four services should copy it.
6. CORRECTION to my C-55 note: claude-approver core.py:281 (`httpx.Client(follow_redirects=False)`) is the internal client for the sentinel, kill-switch and governor (perimeter secret), NOT the Anthropic key path. The Anthropic key is used only in claude_approver/client.py:25 (`anthropic.Anthropic(api_key=key)`), via the SDK, which also builds an httpx client from the environment (so the C-55 proxy finding applies to it too).
7. INFO: `anthropic_headers(key)` (field_core/llm.py:101-110) also sends `x-api-key` toward the gateway when `FORCE_GATEWAY_URL` is set, although `real_upstream` ignores the caller's key and uses its own env key. A service routed through the gateway therefore holds and transmits the real Anthropic key to the gateway over internal http for no purpose. In the compose file only forcegw has `ANTHROPIC_API_KEY` (docker-compose.yml:249, read); drop `x-api-key` from the passthrough headers.

## NOT verified
The approver under the SDK's real error types; the gateway's telemetry store (whether a response body is persisted); behaviour with a real key.
