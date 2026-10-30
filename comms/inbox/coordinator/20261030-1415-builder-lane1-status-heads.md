# Builder Lane 1 status: new heads, follow-ups in flight, one decision for Don

NEW HEADS (all UNVERIFIED on the GX10; no GX10 tool in this session):
- PR 316 (C-456 + C-544) head `6ae698fdbfcab597aeab145ffa5b3f0fd980947f`: form-action 'none' and base-uri 'none' added (C-515 F-C515-1). Whole tools suite 3049 passed, 6 skipped. Body states: narrowed, not closed (navigation cannot be blocked by CSP). Needs a delta review of 6ae698f.
- PR 318 (C-476 + C-486 + C-494 + C-547) head `33a8dc71ef688d7934bede2beb4ebef6a9df1e4a`: three commits (take the range or squash: ecd44ac alone has one red test that 33a8dc7 fixes; I pushed ecd44ac after a masked test exit, my error). C-547 F-C547-1 done (the lifecycle client also pins follow_redirects=False; test with a redirecting stub). F-C547-2 left as documented limits. lifecycle-manager 228 passed, lint 75 passed. Rebase onto main b929f12 is a clean cherry-pick (different files).
- PR 319 (C-101, fork): C-546 findings F-C546-1/-2/-3 are being fixed by the same fork, new head to follow. PR 314 (C-457): C-508 findings F-C508-1..4 are being fixed by its fork, new head to follow.
- PR 317 (C-138, half-up per Don's D-31 ruling) and PR 311 (C-474 docs, PASS) unchanged.
IN PROGRESS: C-501 (flaky revoke-failure test: the assertion now requires the revoke-old line and prints the output; what exited 1 in that CI run is NOT known), branch test/renew-token-revoke-fail-reason-c501, ddbeb71, whole tools suite running. C-460 waits for PR 309 to merge.
DECISION FOR DON (I raise it in chat too): for cents in docs Lane 10 recommends half-up (PR 313) but the governor engine FLOORS (`units_to_usd_str`: $0.675 shows as $0.67, estate total 13,550,000 units shows as $1.35). PR 311 follows the engine. Half-up in docs would contradict what the product displays; changing the display is a code change. Until Don rules, PR 311 stands.
BLOCKERS: none.
