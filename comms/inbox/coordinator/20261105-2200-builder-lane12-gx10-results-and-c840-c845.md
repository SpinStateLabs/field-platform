# GX10 results and the C-840 / C-845 updates (builder Lane 12)

All runs are FULL on the exact head, 16 "== " suites, 0 failed|error lines.

| PR | card | head | GX10 |
|---|---|---|---|
| 374 | C-801 | 09abbe36 | green (reported in the previous note) |
| 369 | C-772 | 57a356b3 | green (includes the C-859 C1 change: the two internal operator routes are always write-only) |
| 361 | C-397 slice 1 | 7525a936 | green |
| 351 | C-724 | 31e92bee | docs only; run started, result in the next note |

## PR 361: C-840 F-C840-1 closed
The double-quoted branch of the dynamic-key rule (`"[^"]*"`) had a surviving widening mutant (`".*"`). Added the row `github["a" || "event"]` to the flagged list; mutant M10 (branch widened to `".*"`) KILLED. Double-quoted strings are not GitHub expression strings, so this was defence only. 132 passed in the file; M1-M9 unchanged.

## PR 366: C-841 F-C841-1
Same finding as C-777 F-C777-1 (the HTTP route's 422 echoes the value; the PR pins the library message only). Not changed; the route fix is a production change in compliance-crosswalk api.py, still waiting for a card or for PR 325 to land.

## PR 351: C-845 closed (head 31e92bee)
- F-C845-1: section 3 names the Fly in-machine path as well as the compose network (integration/fly/Caddyfile:27-28). I wrote "the demo layout", not an estate name.
- F-C845-2: all answer codes listed (401, 404, 413 above MAX_VERIFY_BODY = 1024, 422, 503) with their lines.
- F-C845-3: section 1 says the rotation tool's own auto-revert renames `operators.json.prev` back (a generation decrease), what the below-high-water rule does to a running service, and that I did not trace a reverted PROMOTE.
- F-C845-4: ranges corrected (452-460, 467-524, observer 12-14, 57-62, Fly Caddyfile 21-41).
- F-C845-5: "registry side" reworded to "the parser that reads a key". NOT done: linking the runbook from an index (STATE.md or packages/field-core/README.md are touched by other open PRs); the coordinator may add the link. MAX_OPERATOR_IDS = 64 is out of this runbook's scope.
