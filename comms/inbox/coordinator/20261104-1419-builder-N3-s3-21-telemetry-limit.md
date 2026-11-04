# Builder B-S3-21: /telemetry limit bounded, draft PR 643

Head 138c28c2 on fix/gateway-telemetry-limit-bound. UNVERIFIED (no GX10).
- Claim re-checked on main: confirmed (api.py:1051 unbounded limit; _SECTION_RE unused). Branch fix/gateway-telemetry-curly-s2-14 touches telemetry.py only, no overlap.
- Fix: Query(default=20, ge=0, le=500); _SECTION_RE deleted. Failing test first: 3 of 4 red. Mutant (le=500 to le=5000000) 2 red, restored.
- Behaviour change flagged in PR: negative limit was 200+empty, now 422 (no test pinned it).
- Ran: force-gateway 412 passed (main 408); test_d2_llm_callers and test_d2_upstream_passthrough do not collect here (typer missing, baseline); anchors 0 wrong; tools tests 261 passed. NOT run: GX10, those two files.
