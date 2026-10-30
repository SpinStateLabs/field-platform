# Reviewer report C-446: PR 288 @19365c5 (operator pair only on guarded writes)

Verdict: **PASS** on head 19365c571927d9d8884ccc41a7ae5e5921a9510d (one commit on 3287f03; main has moved to 7e8f16e, the diff does not touch compose files, no conflict expected in console.html or the ops-console tests; rebase not needed to judge, the coordinator's ff-only merge needs one).

## Objections first
1. (LOW, residual, unchanged by the PR) services/ops-console/src/ops_console/static/console.html:835 and :1464: `fetch` follows redirects by default; a same-origin guarded write that is redirected would re-send its headers. Not a read-path leak; reads now carry no pair, so the PR narrows this. Class: design residual.
2. (LOW) The `withoutSecret`/operator checks in the new scenario cover 7 guarded writes through console.js paths; the setup-area writes (register, mint, revoke) are pinned only by the older `read_headers` scenario (setup_harness.mjs:162), which is fine but means two scenarios must both stay.
3. (LOW, environment, not the PR) A full ops-console run on my Windows venv gave 7 failures in test_setup_behaviour.py / test_setup_steps.py where the page under test was an OLD console.html (anchor 'withOperator' absent). The venv's editable install of ops_console points at the main checkout, and in a full-suite run the wrong copy was imported. The same two files run alone with PYTHONPATH on the PR source: 79 passed. I did not find the cross-test cause. Class: test-isolation, pre-existing, not shown to be the PR. Confidence MEDIUM that it is not the PR.

## ASSUMPTIONS
1. console.html is the production artefact; jsdom 24.1.3 harness is representative of a browser for header content.
2. Static call-site audit of console.html at the head is complete (grep of `fetch(`, `api(`, `sfetch(`, `hdrs(`).

## REASONING
1. `hdrs(withOperator)` (console.html:778-785) adds the pair only when `withOperator === true` and `keyTransportOk()`; every other caller gets the secret alone. HIGH.
2. Call sites: `api()` (:832-836) strips `operator` from opts and passes it to `hdrs`; `act()` (:865), bulk (:1100), fleetHalt (:1127) pass `operator: true`; `act()` serves kill, revive, drill, revoke-token, resolve-escalation (per harness list). Manifest (:1199), export (:1268), stream (:1351) call `hdrs()` bare; `/api/check` (:1322) passes no flag. Setup area: register, mint, revoke pass `operator: true` (:1671, :1694, :1720); sentinel check and GETs do not. No other POST sites exist. HIGH.
3. Cross-origin / preflight: every fetch target is a relative path, so no cross-origin fetch exists in the page; preflight carries no pair as it never sends custom headers. HIGH for the static claim; redirects see objection 1.
4. C-20 secure-context refusal intact: `keyTransportOk()` is still in the gate (:783); mutant test `key_send_gate` passes its own mutant check. HIGH.
5. Key placement: the diff adds no storage, DOM, URL, log or error write of OPKEY; the existing sessionStorage entry is the C-20 design, unchanged; `key_leak` and the secret-in-URL scenarios pass in isolation. MEDIUM-HIGH (static review plus the existing scenarios).
6. Tests (isolated run on head): test_setup_behaviour.py + test_setup_steps.py 79 passed, including both `holds` and `fails against its own mutant` for dashboard_headers, dashboard_headers_writes, key_send_gate, read_headers. HIGH.
7. My own mutants (extracted page, node harness, jsdom 24.1.3):
   - send the pair on every request (drop `withOperator === true &&`): `dashboard_headers` readsWithOp = 6 calls (overview, stream, manifest, export x2, check). RED, caught.
   - drop `operator: true` from fleetHalt: `guardedWithPair` false. RED, caught.
   - drop it from bulk: `guardedWithPair` false. RED, caught.
   - drop it from setup revoke: `read_headers` revokeWithOp false. RED, caught (not by the dashboard scenario).
   Pinned by: dashboard_headers (all-requests, halt, bulk, kill/revive/drill/revoke/resolve through act), dashboard_headers_writes, read_headers (register, mint, revoke, sentinel, setup GETs).
8. Whole suite: single full run: 229 passed, 7 failed, all failures traced to objection 3 (old page imported), none reproduce alone. I did not re-run the full suite with the editable install repaired. GX10 not used.

## CONCLUSION
PASS on 19365c5. The change does what the card says; every guarded write keeps the pair, reads, stream, export, manifest and the dry-run check carry the secret only; the three LOW items are residual or environmental. Recommend the coordinator's own full run (CI/GX10) as the check on objection 3.
