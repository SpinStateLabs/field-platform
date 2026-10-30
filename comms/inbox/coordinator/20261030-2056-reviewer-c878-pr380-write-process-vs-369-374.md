VERDICT: PASS WITH CONDITIONS on 75513276a225fe511a6d893eed35249ee5fc75ff
Card C-878. PR 380 (field-mcp) read against PR 369 @ 57a356b38ffc8c6aeabe4e4e020c4f691d25300e and PR 374 @ 09abbe365eb9512757fa0634067e5c9a778369fa. Cloud reviewer, no GX10: output UNVERIFIED until re-run.

OBJECTIONS FIRST
1. PR 380 has one key per service (`FFMCP_<SVC>_KEY`, config.py:74-78), sent as the one perimeter header for reads, the audit append and writes (client.py:63). It has no notion of a read key or a full key. Once PR 369 lands and a service sets a read key, the read process cannot use it for seven Tier 1 tools (F-C878-1), so an adopter must give the read process the full key, which defeats the tier split.
2. "Nothing in the read process can change platform state" (README:3) is true of the tools, not of the key the process holds. With one key per service, the read process holds whatever the adopter configured, and nothing in PR 380 steers it to a read key.
3. The write path decides nothing about which key authorises which write; it sends the same key plus an optional operator pair. If the operator pair is unset the write goes with the perimeter key alone (tools.py:151-152; same point as my C-871).
4. Docs contradict the code: docs/ENVIRONMENT.md:47 says "No Tier 2 tools exist in this build" while catalog.py:89-110 has seven.

ASSUMPTIONS
A1. Heads as named. A2. No GX10, no docker; tests run on the PR 380 worktree only. A3. PRs 369 and 374 are unmerged, so this is a forward-compat review. A4. Probe used dummy keys in a scratch app, not a real service.

REASONING
1. Which key authorises which write. PR 369 authn.py:13-24, 143-150: the full key (`FIELD_SHARED_SECRET`) authorises everything; a read key is accepted only on GET/HEAD/OPTIONS of a path not write-only. All seven Tier 2 routes are POST or PATCH, so each needs the full key (HIGH). My probe on 369's middleware with a read key: GET 200, POST 401; with the full key: all 200 (HIGH, probed).
2. Tier 1 POSTs. catalog.py:114-118 lists seven read-only POSTs (crosswalk x3, replay x2, introspect x2). Under 369 a read key gets 401 on every one (probe above, POST /crosswalk 401). So the read process either cannot serve these tools or must hold the full key (HIGH).
3. Audit append. audit.py:49 sends POST /events to sealed-ledger with the ledger's configured key. Under 369 that must be the full ledger key. The write process therefore holds the full ledger key even for a Tier 2 call to another service (HIGH). Expected, but undocumented.
4. Internal secret (PR 374). The two internal routes need `x-field-internal` (operator_health.py, PR 374 diff). Can the internal secret reach a Tier 2 tool? No: (a) field-mcp never reads or sends `FIELD_INTERNAL_SECRET*` or `x-field-internal` (grep over src, tests, README: no match); (b) both routes are in EXCLUDED for eight services (catalog.py:126-128, 173-178); (c) paths are built from static templates, and an argument is one segment of `[A-Za-z0-9._:@+~-]`, quoted with safe="" (client.py:27, 44-50), so an argument cannot make `/operator/...` (HIGH, read; test_route_coverage pins the exclusion). PR 369 also puts both routes in INTERNAL_PATHS, so a read key never reaches them (authn.py:41).
5. Merge. `git merge-tree` of 380 with 369 and with 374: clean (both touch docs/ENVIRONMENT.md only in different rows). PR 375 was not fetchable by that name here: not checked.
6. Tests at 380: test_tier2, test_client, test_config 98 passed. Full suite and mutants.py not re-run (UNVERIFIED).

FINDINGS
F-C878-1 (MEDIUM-HIGH, blocks turning on per-tier keys, not blocks 380): seven Tier 1 POST tools cannot work with a 369 read key. Either add them to a documented "needs full key" set or accept that the read process holds the full key. config.py:74-78; catalog.py:114-118; PR 369 authn.py:148. Confidence HIGH.
F-C878-2 (MEDIUM, blocks nothing): no read-key variable. Add `FFMCP_<SVC>_READ_KEY` for the read process and use the full key only in the write process, or state that one key is used. config.py:78.
F-C878-3 (MEDIUM): stale doc, ENVIRONMENT.md:47 "No Tier 2 tools exist in this build". Fix before merge. Blocks the docs claim only.
F-C878-4 (LOW): `destructive_hint=False` on every tool incl. Tier 2 (server.py:41) and a blank-operator write path (tools.py:151) carried from C-871.
F-C878-5 (LOW): a test that sends a request through a 369 middleware with a read key for each of the seven Tier 2 and seven Tier 1 POST routes would pin F-C878-1; none exists.

CONDITIONS
C1 (blocks): fix ENVIRONMENT.md:47.
C2 (does not block 380): decide F-C878-1/-2 before PR 369 is released to any deployment that runs field-mcp.
C3 (does not block): internal secret needs no field-mcp change.

NOT VERIFIED: full suite, mutants, CI at this head, PR 375, real-service behaviour.

CONCLUSION
The write process can reach neither internal route and uses no internal secret. Per-tier keys are not modelled in field-mcp, and under PR 369 the seven read-only POST tools would need the full key.
