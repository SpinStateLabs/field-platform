# C-115 reviewer report: PR 74 fix/gateway-followups @eb7c72108342945de7b9bc552f9e46c194c9ac8e (C-112, my C-104 recommendations)

VERDICT: PASS on eb7c721. One MEDIUM-LOW coverage gap (F-C115-1) and two LOW test/scope notes; none blocks.

OBJECTIONS FIRST
1. `REQUIRE_TLS_ENV` guards only the gateway's own upstream call; the judges and every `field_core.llm` caller send the key to `anthropic_base_url()` over any scheme, unchecked and unwarned.
2. A 20-character prefix scrub may redact legitimate text; a longer-than-prefix match leaves the key tail only if the full-key form fails to match first.
3. The scrub is still a reflection reducer: any transformation outside {key, standard base64, 20-char prefix} passes.

ASSUMPTIONS
1. Head eb7c72108342945de7b9bc552f9e46c194c9ac8e, one commit on main 45a36f5 (GX10 `~/ff-work/wt-fieldrev-74`). [HIGH]
2. Anthropic API keys have the shape `sk-ant-api03-` plus about 90 random characters. [MEDIUM: general knowledge, not in repo]

REASONING
1. Suites on GX10: force-gateway 208 passed; conformance-sentinel 109 passed; compliance-crosswalk 160 passed, 1 skipped. [HIGH]
2. probe58 re-run on the head: 12 trials (4 callers x upstream-echo-401, connection-refused, 200-non-JSON-echo), 0 trials with the key in output/log/exception. [HIGH]
3. Mutants: generator on api.py 118-212: 23 mutants, 23 killed. Hand mutants (force-gateway suite): W1 drop base64 form KILLED; W2 drop prefix form KILLED; W3 warn every call KILLED; W4 TLS flag never refuses KILLED; W5 TLS flag on any non-empty value KILLED (3 tests); W6 shortest-first KILLED; W8 dict keys unscrubbed KILLED; W7 prefix threshold `>= MIN_PREFIX_SCRUB + 4` -> `>= 1` SURVIVES (a 20-23 char key boundary is unpinned; a shorter key makes the prefix equal the key, equivalent). LOW (F-C115-2). [HIGH]
4. Scrub coverage probe (a 106-char key shaped like a real one): exact, 20-char prefix, standard base64 of the key (offset-aligned), nested dict key/list value: scrubbed. NOT scrubbed: base64 of a larger blob containing the key (`x-api-key: <key>` encoded, or any offset not a multiple of 3), the key's last 30 characters, a middle 20-character slice, a key split across list items. Other transforms (case, hex, reversal) are outside the three forms by construction (api.py `_secret_forms`); my detector only looks for raw and standard-base64 windows, so it cannot confirm those, I only claim they are not handled. The code comment admits this. [HIGH on the tested cases]
5. Prefix false positives: with the real shape in 2, the first 20 characters are 13 fixed characters plus 7 random ones; chance that ordinary text contains the same 7 random characters is about 1/64^7, roughly 2.3e-13 per position (calculation: 64^7 = 4.4e12). Probe: text containing the 13-char `sk-ant-api03-` alone is NOT altered. Only a test or lab key with a common 20-char prefix would be over-redacted. [MEDIUM]
6. Class-name error texts: hygiene_judge.py:160, judge.py:187, suggestions.py:262, cli.py:134 now print `type(exc).__name__`; probe58 clean; the cli line is `pragma: no cover`, so not testable in CI (the 14 new tests plus one changed assertion in test_suggestions.py cover the others). [HIGH]
7. REQUIRE_TLS reach (objection 1): `hygiene_judge.py:122` and `judge.py:143` build their client from `field_core.llm.anthropic_base_url()` (FORCE_GATEWAY_URL > ANTHROPIC_BASE_URL > default) and `anthropic_headers(key)` sends `x-api-key`; neither the warning nor the refusal runs on these paths. The gateway's `real_upstream` is the only call guarded. So with `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM=1` an http non-private `ANTHROPIC_BASE_URL` still gets the key from the judges and any other `field_core.llm` user. MEDIUM-LOW (F-C115-1). [HIGH: read, not live-probed]
8. Recommendation on making the flag default: NOT yet. Reason: existing tests document an http proxy base (test_d2_llm_callers.py:64,74), and a default-on refusal would break the judges and any such deployment at upgrade. Do: (a) move the check into `field_core.llm` so every key-bearing call is covered, (b) set the flag to 1 in the GB10 and Fly compose, where the base is https or private, (c) revisit the default at the next minor version. Don's call. [MEDIUM]

CONCLUSION
PASS at eb7c721. Fix card suggestion: F-C115-1 (extend the TLS check to `field_core.llm`), F-C115-2 (pin the 20-23 char key boundary), F-C104-1 residual (base64-of-blob, tail and split echoes) stays as documented in the code. F-C104-2 (warn once) and F-C104-3 (class-name errors) fixed at eb7c721.
