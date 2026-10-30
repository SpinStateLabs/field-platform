VERDICT: PASS WITH CONDITIONS on 3a525dcc13899ef821975ebfbbb995308667c2e4
(Lane 14, cloud, no GX10: UNVERIFIED re-run. NOTE: the queue already shows C-699 DONE on the strength of the Lane 10 note (20261104-1700-design-c699-...); my claim was filed before that closed. This is an independent second read of the same head; it repeats nothing of Lane 10's table except where I re-ran it, and adds the findings marked NEW. Production change: services/force-gateway api.py (+43), docs/ENVIRONMENT.md, one 153-line test file; two commits on main. Ran here: the whole force-gateway suite, 495 passed at this head (not the 16-suite GX10 set). CI at this head read by REST: 1 job in progress, 6 queued: NOT confirmed.)

OBJECTIONS FIRST
1. COMMIT IDENTITY. The head commit 3a525dc has author AND committer "Claude <noreply@anthropic.com>"; the other commit (8d86806) is Don Hagell no-reply. The identity rule for this repository is the Don Hagell no-reply form on every commit. NEW, HIGH.
2. The PR closes "the value never reaches a message" for five numeric tunables and one URL; the claim is about a class, and the class has more members in the same service (below).
3. Validating "is it a number" while accepting nan, inf, zero and negative values turns a typo that was a crash into a silent disabling of a guardrail.
4. A startup refusal on a blank variable is a regression risk wherever a compose file passes `${X:-}`.

ASSUMPTIONS
A1. Probes call the functions and the app directly with fake values; nothing leaves the sandbox. A2. "Value" = text the operator put in an environment variable or URL, which may be a secret placed there by mistake (the PR's own premise).

REASONING
1. Numeric tunables: `_env_number` (api.py, new) raises InvalidNumericSetting naming the variable and the expected form, outside the handler so no chained text. Probed with 12 spellings, including a secret-shaped string and a 5000-digit integer: refused with the fixed message, the value absent. HIGH (run). Accepted without refusal: `nan`, `inf`, `1e999` and negatives for floats, negatives for integers, Arabic-Indic digits and `1_0` (Python's own rules).
2. Consequence of accepting them, traced in the code: the latency guardrail is `overhead_ms > latency_budget_ms` (api.py:1058): with nan or inf it is never true, so the bypass the budget exists to trigger never trips; the drift alert is `abs(mean - baseline) > band` (drift.py:91): with nan or inf it is never true, so drift never alerts; a negative cooldown makes `bypass_remaining` non-positive, so a bypass entered does not hold; a window size of zero or below completes a window per score (drift.py:78). Lane 10 left this untraced; I read the comparisons. NEW (F-C699-3), MEDIUM-LOW.
3. `public_origin`: 22 inputs probed. Userinfo, path, query, fragment dropped; port kept; IPv6 bracketed; an unparsable port, a bare word, a missing scheme and a missing host print `(unparsable url)`; a newline is stripped. Not hidden: a secret placed in the HOST label (`http://<secret>.example` shows the host) and any scheme word (`ftp://h`); the host cannot be hidden without defeating the field. HIGH.
4. 503 body: `SentinelClient.check` raises with `public_origin(...)` and the exception class name only; the 3 other failure messages (non-200, non-JSON, no verdict) carry fixed text; `_authorize` puts `exc` into the 503 detail, which is now fixed text. HIGH.
5. Other values that reach a body, in this service (NEW): GET /telemetry answers 503 with `store_error`, built as `f"{type(exc).__name__}: {exc}"` (api.py:516, 768, 865, 1052, 1095; exposed at api.py:1074 and :1081). Probe: point FIELD_DATA_DIR at a path under a regular file, build the app, request /telemetry: the 503 body contains `NotADirectoryError: [Errno 20] Not a directory: '<the full configured path>/gateway'`. The configured data directory is an operator value and now sits in an HTTP body. /health shows only the word "unavailable". PROVEN (F-C699-2), MEDIUM-LOW.
6. Blank values (NEW): `_env_number` refuses an environment variable that is set to the empty string (`int("")`); the neighbouring resolvers in the same file treat blank as unset (`resolve_sentinel_url` says so for a compose `${X:-}`; `resolve_telemetry_window`, `resolve_retain`, `resolve_sample_every` fall back). No compose file in the tree passes these five variables (grep), so nothing breaks today, but a `${FORCE_HYGIENE_WINDOW:-}` line would stop the gateway at startup with "unset it for the default" while the variable IS set, to blank (F-C699-4), LOW.
7. Still echoing, outside this PR (confirmed by reading, as Lane 10 reported): `_posture_flag` puts the first 40 characters of the value in its refusal (api.py:298). That is PR 324's change; PR 324 (ca70eec) and PR 352 merge without conflict (merge-tree check), so the order does not matter; until both land the echo is live. LOW, tracked.
8. Silent fallbacks (re-confirmed): FORCE_GATEWAY_SENTINEL_TIMEOUT, FORCE_TELEMETRY_WINDOW, FORCE_TELEMETRY_RETAIN, FORCE_GATEWAY_SAMPLE_EVERY swallow junk and use the default (api.py:240-246, :325-331; store.py:68-73; hygiene_judge.py:175-182). No echo, no refusal, no log: an operator who typos the sentinel timeout believes a custom value is in force.
9. Mutants against the whole suite (each must go red; file restored each time): value echoed in the message; original text chained; int/float wording swapped; `public_origin` returns the raw URL; drops the port; drops IPv6 brackets; unparsable value shown raw (two branches); 503 body with the raw base URL and exception text; 503 body with the exception text only; /health with the raw URL; each of the five tunables reverted to a bare `int()` / `float()`: 16 of 16 RED. HIGH.
10. Merge note: PR 352 touches api.py around the same lines as PR 324; merge-tree reports a clean merge. HIGH.
11. Public repo: no estate address, flag value, build SHA, deploy status or credential in the diff; test values are fake. The docs/ENVIRONMENT.md change adds line references and the new refusal wording only. HIGH.
12. Aside (not this PR): `SentinelClient` builds `httpx.Client(timeout=..., headers=auth_headers())` at construction (api.py:380): the perimeter secret and operator pair are read once and sent on every call, and the proxy environment is honoured; same class as PR 330's per-request change (F-C699-6, LOW).

FINDINGS
F-C699-1 (NEW, HIGH confidence, blocks per repository rule): commit 3a525dc is authored and committed by `Claude <noreply@anthropic.com>`, not the Don Hagell no-reply identity. Re-author before merge (or Don rules the agent form acceptable; the PR 346 guard would allow it).
F-C699-2 (NEW, MEDIUM-LOW): api.py:516, 768, 865, 1052, 1095, 1074: `store_error` (an OSError or sqlite message) is returned in the 503 body of /telemetry and shows the configured data path. Return a fixed text with the exception class, keep the full text in the log.
F-C699-3 (NEW, MEDIUM-LOW): nan, inf, zero and negative values accepted for the latency budget, band, window, cooldown: each disables or inverts a guardrail silently (item 2). Refuse non-finite and non-positive values the same way (name only).
F-C699-4 (NEW, LOW): a blank variable is refused; make blank mean default like the other resolvers.
F-C699-5 (LOW, carried): four tunables fall back silently (item 8); a one-time warning naming the variable would close the contradiction with the new rule.
F-C699-6 (LOW, aside): SentinelClient headers read at construction.
Carried from Lane 10 and re-run: a word-shaped scheme survives `public_origin`; the posture-flag echo (PR 324).

CONDITIONS
C1 (blocks): F-C699-1 identity.
C2 (non-blocking): F-C699-2 and F-C699-3 as builder follow-ups (C-716 carries Lane 10's list; add these two).
C3: the GX10 run and CI at this head.
Not verified: whether /telemetry is reachable without the perimeter secret on any estate; CI; the 16-suite set; behaviour with real values.

CONCLUSION
The PR does what it says: five numeric tunables and the sentinel URL no longer echo (16 of 16 mutants red; 495 tests pass). The same class is still open in the telemetry store path, the posture-flag message and a few silent fallbacks, the new validation accepts values that disable two guardrails, and the head commit carries the wrong identity. PASS WITH CONDITIONS on 3a525dc: C1 blocks.
