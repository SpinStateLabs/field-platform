# C-104 reviewer report: PR 69 fix/gateway-key-hygiene @f312691 (C-60, my C-58 findings)

VERDICT: PASS on f312691 for the code. The warn-vs-refuse question is answered below (warn is acceptable for now; one change recommended).

OBJECTIONS FIRST
1. `scrub_secret` is exact-substring only: any transformed echo of the key (prefix, base64, case change, split) passes through.
2. The warning fires on every upstream call: log flood, and it normalises a standing misconfiguration.
3. Warn-not-refuse leaves a key-over-cleartext path that a rogue or mistyped `ANTHROPIC_BASE_URL` can use.

ASSUMPTIONS
1. Head f3126915d3710a9b253d870324b97dcbe650630d, base a8bd47c (GX10 `~/ff-work/wt-fieldrev-69`). [HIGH]
2. `ANTHROPIC_BASE_URL` is operator-set environment, not caller-controlled. [HIGH, api.py:166-167 reads the env only]

REASONING
1. Suites on GX10: force-gateway 194 passed; conformance-sentinel 109 passed. [HIGH]
2. My probe58 (`~/ff-work/probe58.py`) re-run against the head: upstream echoing request headers (401 JSON), connection refused, and 200 non-JSON echoing headers; for force-gateway real_upstream, AnthropicHygieneJudge, conformance-sentinel AnthropicJudgeClient and compliance-crosswalk AnthropicSuggester: key in output/log/exception = False in all 12 trials. [HIGH]
3. Mutants: generator on api.py 117-152: 15 mutants, 15 killed. Hand mutants: H1 remove `scrub_secret` call KILLED; H2 remove the warning log KILLED; H3 log the base URL KILLED (a test pins "no userinfo in the log"); H4 hygiene_judge full `{exc}` KILLED; H5 conformance-sentinel full `{exc}` KILLED. 0 survivors. [HIGH]
4. Residuals, direct probe of `scrub_secret(v, KEY)`: exact string and URL-encoded form scrubbed (the hyphenated key is unchanged by quoting); a 20-char prefix, base64, upper-case and a key split across list items are NOT scrubbed. bytes and tuple inputs are not scrubbed but unreachable (`resp.json()` yields only str/list/dict/numbers). Real impact: an upstream that already received the key in the request can also exfiltrate it directly, so the scrub protects against reflection to callers (confused deputy), not against a malicious upstream. LOW (F-C104-1). [HIGH on behaviour, MEDIUM on impact]
5. `_base_url_warning` (api.py:134-153): logic correct for https, loopback, private IPs, `localhost`; message carries scheme and `u.hostname` only, never userinfo or the key (test_c60_key_hygiene.py:77 pins it, H3 killed). Edge: `proxy.example.test` (a hostname, not an IP) always warns, which is the intended case; a base without a scheme (`localhost:8000`) parses with scheme `localhost` and an empty host and warns without crashing; CGNAT 100.64.0.0/10 counts as public and warns. Warning is logged per request (api.py:169-171): flood, LOW (F-C104-2). [HIGH]
6. Who else reads the upstream body: force-gateway telemetry/drift/metering/`_enforce_tool_blocks` all take the already-scrubbed `response` (api.py:850-900), so one scrub at the source covers them; `HTTPException(status, response)` for non-200 is also scrubbed. Remaining raw `{exc}` text: compliance-crosswalk `suggestions.py:262`/`cli.py:134`, hygiene_judge.py:160 and judge.py:187 ("unparseable ... {exc}"): probe58 showed no key in those, but they embed a library exception string and are not pinned by a test; LOW (F-C104-3). [MEDIUM]
7. Design question (warn vs refuse http non-private): the key is operator-configured, the existing tests (test_d2_llm_callers.py:64,74) document an http proxy base, and a refuse would break those deployments. Warn is acceptable. Recommend: log once per process, and add an opt-in `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1` that refuses a non-private http base. That is a roadmap choice for Don. [MEDIUM]

CONCLUSION
PASS at f312691. New register rows F-C104-1 (LOW, scrub exact-substring only), F-C104-2 (LOW, per-call warning), F-C104-3 (LOW, raw exc text in crosswalk/judge parse errors). F-C58 findings become "fixed at f312691 (PR 69, in batch A, pending merge)".
