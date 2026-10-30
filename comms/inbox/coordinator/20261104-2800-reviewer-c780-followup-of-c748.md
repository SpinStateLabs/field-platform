VERDICT: PASS WITH CONDITIONS on the design note 20261030-1700-design-force-field-mcp.md as ruled (D1-D8) against main 63e91b2 (UNVERIFIED: cloud reviewer; routes read from source by syntax tree and by reading; no service run)

Follow-up of my own C-748 report. For each discrepancy it listed: verified at file:line on main, and what it needs changed (the prompt, the design note, the route-coverage test spec, or the tier counts 49 and 8). Method: counted every route decorator in the 13 services (ops-console excluded by D2): 79 routes = 42 GET + 32 POST + 4 PUT + 1 PATCH. The note's tiers sum to 77 (42 R + 7 Q + 8 W1 + 20 W2).

OBJECTIONS FIRST
1. The count does not close: 79 routes in code, 77 in the tiers. The two missing are `claude-approver POST /halt/{field_agent_id}` (claude_approver/api.py:10, EXCLUDED by note item 7, fine) and `force-gateway POST /v1/messages` (force_gateway/api.py:873), which is in NO tier and in no EXCLUDED line of the note (a search of the note for the route or the gateway's messages path finds only the ops-console exclusion). It sends a caller-chosen request to the real model API with the platform's key and spends tokens (it meters to the governor), so it is a write-class tool at least. The coverage test would go red until it is handled, which is the test's job, but the note's counts and its tier table are silent. PROVEN by the count. NEEDS: design note (name the tier or EXCLUDED), counts.
2. PATCH-with-status is still Tier 2 (W1) in the note: registry `PATCH /agents/{id}` at agent_registry/api.py:255 changes status, and the handler maps a status change to kill, revive or decommission (api.py:257-265; a decommission is terminal, api.py:306). That is the kill-switch's own authority by another route. With D4 (Tier 3 never in the server) this means v1 would expose a kill path through W1 that the note excludes through W2. PROVEN. NEEDS: design note decision (move PATCH to W2, or forbid `status` in the tool's input schema at Tier 2), counts (W1 8 to 7 and W2 20 to 21 if moved), route-coverage spec (the tool's schema test).

Verified and needing NO change to the note (the note already rules them):
3. Missing route in the prompt: spend-governor `POST /escalations/{escalation_id}/resolve` at spend_governor/api.py:436-447 (multi-line decorator, guarded by guard_escalation at :282 and :446). The note lists it in W2 and says the enumeration must read app.routes (note section 5). Only the PROMPT is stale. HIGH.
4. `/check` and `/regwatch/check` are not read-only: sentinel record_action meters each allowed action with POST /spend (conformance_sentinel/engine.py:92-94); crosswalk regwatch "A change SETS a stale flag" (compliance_crosswalk/api.py:153-160). The note puts both in W1 (D3 ruled Tier 2). Only the PROMPT is stale. HIGH (the metering is now proven in code; at C-748 I had it from a document).
5. The operator identity pair as its own secret class: the note covers it (item 6 and the two entry points, the read process never loads the pair or the write flag). Eight services use the operator layer (agent-registry, delegation-authority, federation-broker, kill-switch, lifecycle-manager, ops-console, sealed-ledger, spend-governor; each api imports operator_auth or operator_health). No change.
6. `POST /spend` and `/usage` as W2: spend_governor/api.py:334 and :485; the note keeps them in W2. No change.
7. `claude-approver POST /halt`: excluded by the note; the route is the kill-switch's outbound target. No change.
8. Streaming and HTML routes of ops-console (`GET /api/stream` at ops_console/api.py:448, the page at `/`): ops-console is excluded wholesale by D2. No change.

Needing a change to the route-coverage test SPEC:
9. The hidden operator routes `POST /operator/verify-hash` and `GET /operator/rotation-state` are registered with include_in_schema False (operator_health.py:710-712 inside install_routes at :680) and exist only when the operator layer is armed and a perimeter secret is set. The note's spec collects routes from app.routes (which includes hidden routes) but builds apps "with stub dependencies": if the stub apps do not arm the layer, the two routes never appear and the test cannot notice that a service gains them. NEEDS: the spec to arm the layer in the test build, or to record an EXCLUDED entry for these two paths per service (they are a hash oracle: see my C-701 and C-700 reports). Which services call install_routes was not established by my search (no call in the api files; it is reached through field-core). NOT VERIFIED.

Verified, minor:
10. attestation-reporter `GET /pack` and `/pack.html`: no ledger append or outbound write found in the api file or the package (a search for append and note calls); the note's R tier (all GETs) holds for them. MEDIUM (search, not a trace).

ASSUMPTIONS
A1 The ruled note (D1-D8) is the design of record; the prompt is superseded where they differ. A2 "Route" = a decorator with a literal path. A3 main at 63e91b2.

REASONING
1. Counts: 42 + 32 + 4 + 1 = 79 by syntax tree over the 13 services; tiers 42 + 7 + 8 + 20 = 77; difference = /halt (excluded) and /v1/messages (untiered). Per-method check: the note's R is exactly the 42 GETs; its POSTs are 7 Q + 7 W1 + 16 W2 = 30 of the 32 in code, again the two above; its PUTs are 4 (three in spend, one in federation) = all 4 in code; the one PATCH is in W1. HIGH.
2. Each file:line above read on main. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The note is right on four of the six discrepancies I raised and already rules them; two need a note decision (the PATCH tier, the untiered /v1/messages route) with count changes, and one needs a spec clarification (hidden operator routes).
- C1 (decision for Don, counts change): PATCH-with-status tier. Option A: move to W2 (excluded in v1; counts 49 / 7 / 21). Option B: keep in W1 but refuse `status` in the tool schema (counts unchanged; test the schema).
- C2 (design note): give `force-gateway POST /v1/messages` a tier (W2 or EXCLUDED with a reason); counts become 49 / 8 / 20 plus the new entry, or 49 / 8 / 21.
- C3 (spec): arm the operator layer in the coverage test build or add the two hidden paths as EXCLUDED per service.

FINDINGS
F-C780-1 MEDIUM, services/force-gateway/src/force_gateway/api.py:873 (POST /v1/messages in no tier). PROVEN by count.
F-C780-2 MEDIUM, services/agent-registry/src/agent_registry/api.py:255-265 (PATCH status = kill/revive/decommission, tiered as W1). PROVEN.
F-C780-3 LOW-MEDIUM, packages/field-core/src/field_core/operator_health.py:680-712 (hidden routes absent from the note and conditional on arming). PROVEN for the registration; which services install them not established.
F-C780-4 INFO, tasks/lane-prompts/force-field-mcp-designer-builder.md (stale on the escalation route and the two tier mislabels; superseded by the ruled note). HIGH.

NOT VERIFIED: which services install the operator routes; per-route side effects of every GET and POST (only the ones named above); the builder PRs against the note (other cards).
