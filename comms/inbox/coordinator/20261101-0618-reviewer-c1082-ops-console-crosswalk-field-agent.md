VERDICT: AUDIT (no PR head, no merge gate) on main acaf5f241f: 0 HIGH. ops-console 15 findings (1 MEDIUM), compliance-crosswalk 13 (2 MEDIUM, one a carried doc finding), field-agent 15 (1 MEDIUM). No fail-open of a FieldClient verdict was found. The three MEDIUM code findings are a default-open write path on the console CLI (F-OPS-9), a NaN confidence that clears the suggestion floor (F-CW-1), and a proxy-environment path for the shared secret in every SDK client (F-FA-6).

# C-1082 reviewer report (Lane 14, cloud, read audit): services/ops-console, services/compliance-crosswalk, packages/field-agent on main acaf5f24

UNVERIFIED: cloud run, no GX10, no mutants (the card says none). Nothing was edited; probes ran on made-up data against a detached worktree of main acaf5f24 (made-up secret strings, local listeners, proxy variables unset first).

## OBJECTIONS FIRST

1. The three audits were produced by three read-only sub-agents that I briefed and that each wrote one section below; I did not read the three scopes line by line myself. What I did myself: re-read the code behind the top finding of each scope and confirmed it against main (F-OPS-9: ops_console cli.py:28-44 has no host check and field_core authn.py `install` skips every check when no secret is set; F-FA-3: field_agent liveness.py:65-69 puts `resp.text` in the error; F-FA-6: all five `httpx.Client(...)` calls in field-agent leave `trust_env` at its default; F-CW-1: suggestions.py:203 `max(0.0, min(1.0, float(...)))` returns 1.0 for NaN, the same clamp I probed in the sentinel's floor under C-1079; F-CW-3: evidence_pack.py:194 puts `agent_id` raw into a markdown line). The rest of each section is the sub-agent's probe or read; "PROBED" means the sub-agent ran it, and the probe scripts are in /tmp/claude-0/m1082-{ops,cw,fa}/ on this host, not in the repo. Treat un-reconfirmed lines as MEDIUM confidence until a builder's test reproduces them.
2. The card asks "does it fail closed". For ops-console the answer is "not by default": F-OPS-9 is a documented default (authn off without a secret) that the CLI does not guard. That is a decision for Don, not only a builder card.
3. Failure conditions for "these three are sound": (a) the console is started on a non-loopback host with no secret (F-OPS-9); (b) a model or peer returns NaN, an oversize body or an unexpected shape and the code takes it as good (F-CW-1, F-FA-3, F-FA-4); (c) a document names a symbol that was renamed and a reader trusts it (seven stale doc locations in the crosswalk).
4. Steelman: every reply these services parse comes from a peer on the same estate behind the perimeter, the SDK's `FieldClient` cap and proxy fix exist and hold, and most findings are defence in depth. I do not claim a remote exploit for any of them.
5. Overlap: the sub-agents read only the first lines of each earlier report, so a NEW tag can be a re-discovery. The ops-console agent marks five findings CARRIED because main lacks the PR 348 proxy hardening; PRs 359 and 409 (field-agent read caps) were not audited, only named.

## ASSUMPTIONS

A1 Main is acaf5f24 (fetched at review time, shallow clone; read through a detached worktree).
A2 The perimeter secret is armed on a served estate; the findings that depend on it say so.
A3 Earlier reports are summarised by their own text and not repeated.
A4 A probe by a sub-agent is real only for the data it names; a value I did not see run is MEDIUM confidence.

## REASONING AND FINDINGS

The full per-finding detail follows as three sections, each with: earlier coverage, what was read and not read, findings with file:line, severity, confidence, PROBED or READ, the tests grepped, and the one-line killing test (proposed builder cards, not code).

---- SECTION 1: services/ops-console ----

# Audit: services/ops-console on main acaf5f24 (card M1082, read-only)

Method: read the code, ran probes on made-up data (stub upstream clients, FastAPI TestClient, one real uvicorn on loopback). Probe scripts: /tmp/claude-0/m1082-ops/p1.py to p6.py. Nothing in git was touched.

Key fact for the carried findings: main acaf5f24 does NOT contain the PR 348 proxy hardening (no `_seg`, no `_relay`, no relay_5xx in `services/ops-console/src`; `git log` for the service ends at 5808a5cd). So the C-523 / C-644 / C-651 findings below are CARRIED, and each is shown again on this commit.

## Earlier coverage
(first 15 lines of each; 18 reports under comms/inbox/coordinator matched `ops-console|console`)
- 20261028-2359 reviewer-c91: PR 25 brand CSS and CI external-reference guard; first pass over console.html XSS and secret handling (R-05).
- 20261029-0030 reviewer-c200: console.html sinks all via esc()/textContent, 79 esc-removal mutants; CSV formula guard F-C200-1; operator pair sent on every fetch F-C200-4; no CSP.
- 20261029-0230 reviewer-c237: PR 112, Declared row that the shared secret is typed and sent on plain http (decision "document now, gate later").
- 20261029-0400 reviewer-c239: PR 117, tests pinning the manifest symlink guard; one surviving mutant (race case).
- 20261029-0525 reviewer-c284 pt1: PR 140, symlink loop in manifest ref/dir now 404 (api.py:204,216).
- 20261029-0535 reviewer-c284 pt2: PR 143, each manifest containment check and the signed operator.refused append pinned by tests.
- 20261029-2800 reviewer-c171: server side of api.py, 114 mutants, 26 survivors; console holds no operator identity.
- 20261030-0850 builder-c221: PR 288, operator pair only on guarded writes (hdrs(withOperator)).
- 20261030-2323 reviewer-c904 / 20261102-2200 design-c515 / 20261102-2300 reviewer-c515 / 20261106-0900 reviewer-c567-c458: PR 316 Caddy CSP and headers (form-action, base-uri, Cache-Control no-store vs stream no-cache). Edge config, not this service's code.
- 20261101-0210 design-operator-key: design note on the operator key in the page (sessionStorage, no script-src, keyTransportOk).
- 20261102-0300 reviewer-c446: PR 288 review; F-C446-1 (=== true strictness held by an anchor), F-C446-2 (redirect re-sends headers; closed by C-451, now on main at console.html:836,1465).
- 20261102-2430 reviewer-c523: re-audit of api.py; F-C523-1 unquoted path ids, -2 half pair test gap, -3 upstream error body relayed, -4 open class (ServiceClient URL building).
- 20261104-0400 reviewer-c644 / 20261104-0530 reviewer-c651: PR 348 review (encode ids, no 5xx body relay); F-C644-1..4, F-C651-1..4 (bulk/halt/overview still relay bodies; non-JSON loses status).
- 20261107-0200 reviewer-c936: PR 348 delta; says F-C523-1/-2/-3 fixed ON THE PR (not on main); F-C936-1 `%2F` decode, -2 DEBUG log of body, -3 halt row error text.
- I read only the first 15 lines of each (and extracted their F-ids by grep), not the bodies. "NEW" below means: not in those lines or F-id lists.

## Read
- Read in full: services/ops-console/src/ops_console/api.py (1-753), cli.py (1-46).
- console.html (1,936 lines): read 1-16 (head), 255-275 (operator bar), 740-1386 (dashboard script: storage, hdrs/api, every innerHTML/insertAdjacentHTML site, bulk/halt, drawer, manifest, export, platform, harness, stream), 1387-1538 (setup block helpers, sfetch, describe, scrub, opstate), 1700-1936 (revoke, check, attest, ledger, registry, findings). Grep for sinks across the whole file (innerHTML, insertAdjacentHTML, eval, new Function, document.write, outerHTML, setAttribute, location, href, Storage, Blob/createObjectURL).
- Read from field_core (context only): authn.py 1-60, operator_auth.parse_headers and mode(), operator_health http_refusal/note_refused/health_fields.
- Tests checked by grep (names in each finding): tests/test_ops_console.py, test_console_features.py, test_ops_console_c184.py, test_operator_auth_g_ops_console.py, test_console_identity_c14.py, test_operator_health_g_ops_console.py, test_dashboard_escaping.py, test_setup_behaviour.py, test_halt_banner_counts_c19.py, test_manifest_loop_c269.py.
- NOT read: console.html lines 17-254 and 276-739 (CSS and static markup; only grepped for sinks), 1539-1699 (setup route/step builders, doRegister/doMint bodies); SPEC.md, README.md, demo.sh, pyproject.toml; the test bodies other than the lines quoted; tests/*.mjs harnesses; the Caddyfiles; field_core beyond the bits above (`/operator/verify-hash` and `/operator/rotation-state` routes the console inherits were only checked for 401 without the secret).

## Findings

### F-C1082-OPS-1 | MEDIUM-LOW | conf HIGH | PROBED | CARRIED (F-C523-1)
api.py:664, 669, 674 (kill/revive/drill), :738 (revoke), :744 (resolve), and :422 (`/usage/{agent_id}` in the overview) put the path id into the upstream URL unquoted; only :495, :513, :686, :719 use `quote(..., safe="")`.
Probe (stub upstream, made-up ids): `a%3Fx%3D1` reaches the kill-switch as `/kill/a?x=1`; `a%23frag` as `/kill/a#frag`; `%2E%2E` as `/kill/..`; revoke `t%3Fq%3D1` as `/tokens/t?q=1/revoke`; resolve likewise. The operator pair is forwarded on that rewritten request. Registry-supplied ids at :422 do the same.
Class: caller-controlled text changes the upstream route and query. Fails open (the request still goes out).
Tests: grep `quote|%3F|%2F|%23` in the six test files finds nothing for these routes; test_ops_console_c184.py pins only the manifest guard.
Kill test: one parametrized test posting ids with `?`, `#`, `..` to each of the 5 write routes and the overview usage call, asserting the upstream path equals the percent-encoded id.

### F-C1082-OPS-2 | MEDIUM-LOW | conf HIGH | PROBED | CARRIED (F-C523-3, F-C644-1, F-C651-1)
Upstream error bodies are echoed to the browser: api.py:660 (`_proxy`, detail=data), :583 (events, export), :515 (manifest registry error), :712-713 (halt, registry body in text), :374 and :564 (`Section.error` `status N: {data}`, rendered on the page by `unavail`), :689-690 and :729 (bulk and halt rows).
Probe: stub upstream answering 500/503 with a marker string; marker present in the console answer on kill (500), bulk (200 envelope), halt via registry 503 (502), agent detail, overview, platform, events (500), export (500), check (500): 9 of 9 routes tried.
The tests pin the opposite behaviour: test_ops_console_c184.py:201 `test_an_upstream_error_status_and_body_pass_through_unchanged`, :230 likewise for the ledger.
Kill test: for every proxied route, stub a 503 whose body holds a marker and assert the marker is absent from the answer (and make c184:201 assert the fixed text).

### F-C1082-OPS-3 | MEDIUM-LOW | conf HIGH | PROBED | NEW
api.py:709 `if not domains:` treats an explicit `domains: []` as "every domain" (model: api.py:160-161 allows `list[str] | None`). Probe: registry with two domains, POST /api/fleet/halt `{"domains": []}` with confirm HALT: kill-switch received `/kill/domain/d1` and `/kill/domain/d2`. Also `domains: [""]` is forwarded as `/kill/domain/` (:717-719). A caller that filtered down to nothing halts the whole fleet. Gated by the typed HALT and, under ENFORCE, the operator pair, so this is wrong-scope, not an auth bypass.
Tests: grep `"domains": \[\]|domains.*\[\]` in tests: none; halt tests use `["finance"]` or the default (test_console_features.py:330, test_halt_banner_counts_c19.py:167,180).
Kill test: POST halt with `domains: []` and with `[""]` and assert 422 and zero upstream calls.

### F-C1082-OPS-4 | LOW | conf HIGH | PROBED | NEW
No size or content limits on write bodies: `operator`, `reason` (api.py:134-137, 149-150, 157), `agent_ids` items (:148), `domains` items (:160), `resolved_by` (:141) have only `min_length=1`. Probe: a 2,000,000-character `operator` was accepted and forwarded upstream; bulk `agent_ids: ["", "  ", "a/../b", "a?b"]` produced `/kill/`, `/kill/%20%20`, `/kill/a%2F..%2Fb`, `/kill/a%3Fb` (bulk is quoted, but blank ids are forwarded). `domains` is unbounded (the list has no max_length), unlike agent_ids (100).
Tests: grep `max_length|2_000|blank` in tests: none; test_console_features.py:313 checks only an empty `operator`.
Kill test: bodies with a 10k-char operator/reason, blank or whitespace ids, and 101 domains each answer 422.

### F-C1082-OPS-5 | LOW-MEDIUM | conf HIGH | PROBED | NEW
Upstream answer shape is trusted, so one odd row turns an "unavailable" section into a 500 for the whole answer, against the module promise (api.py:9-10). Probes: registry row without `agent_id` (api.py:422 `agent['agent_id']`) gives /api/overview 500; registry returns a dict gives 500; governor 200 with a list (`data.get` at :423) gives 500; export with a non-dict payload or row (:622-627) gives 500; manifest with `manifest_ref` an int or list, or a non-dict registry record (:516-521) gives 500 "Internal Server Error". The same code runs inside `/api/stream` (:471), so the stream also dies.
Tests: grep `KeyError|without agent_id|manifest_ref.*123` none; test_ops_console_c184.py:217 covers registry error statuses only.
Kill test: parametrized malformed-upstream bodies for overview, stream (frames=1), export and manifest, each asserting 200 with the section `available: false` (or a fixed 502), never a 500.

### F-C1082-OPS-6 | MEDIUM-LOW | conf MEDIUM | PROBED (the 500) + READ (the page)
console.html:1337-1338 `refresh()` swallows every error; the stream path (:1372-1378) only flips the label to "POLL 5s". After F-5 (or any overview failure) the page keeps showing the last agents, "LEDGER: INTACT" and the old "as of" stamp (:1074) with no staleness banner. On a kill-switch console a frozen "INTACT / active" view is a wrong-but-calm display.
Tests: grep `stale|as of|unreachable` in dashboard_xss_harness.mjs and test files: no scenario where the overview call fails.
Kill test: jsdom scenario where /api/overview answers 500 after one good load; assert a visible "data is stale" element and that LEDGER no longer reads INTACT.

### F-C1082-OPS-7 | LOW-MEDIUM | conf HIGH | PROBED | NEW
api.py:459-465: the stream cap is checked in the handler but the counter is incremented only when the generator starts (:465). Under concurrent connects the cap is exceeded. Probe (real uvicorn on loopback, made-up stubs, `max_streams=3`, 200 simultaneous GET /api/stream): 4 and 7 accepted in two runs (cap 3); the counter returned to 0 afterwards. Each stream runs `_build_overview` every 2 s, which is 5 + N upstream calls (N = agents, sequential at :422), so the overshoot multiplies upstream load.
Tests: test_console_features.py:355-365 test the cap only with sequential requests (`max_streams=0`, then `1`).
Kill test: start the app on a real server, open cap+10 streams at once, assert at most cap answer 200.

### F-C1082-OPS-8 | LOW-MEDIUM | conf HIGH (echo) / LOW (likelihood) | PROBED | NEW
`Section.source` = `GET {client.base}{path}` (api.py:371, 373, 556, 563; `source` also in the JSON export at :606) returns the configured upstream base URL to every caller who holds the shared secret. Probe: `FIELD_*_URL`-style base `http://opuser:HUNTER2@127.0.0.1:1` (made up): the string `HUNTER2` appears in /api/overview. Even without userinfo it publishes internal service addresses in the JSON, while the page's own `scrub()` (console.html:1425-1429) exists to keep those out.
Tests: test_ops_console.py greps `source` only for its presence.
Kill test: build the app with a base URL carrying userinfo and assert that no response body (overview, platform, export, detail) contains the userinfo or the base, only a service name.

### F-C1082-OPS-9 | MEDIUM | conf HIGH | PROBED | NEW (the authn default is Declared; the missing guard on the CLI is not)
With `FIELD_SHARED_SECRET` unset, authn is a no-op (field_core/authn.py `install`), and with no operator mode set (`_operator_kw`, api.py:648-653) a write needs no identity at all. Probe: no env, POST /api/agents/a1/kill without any header: 200 and forwarded to the kill-switch. `console serve --host 0.0.0.0` with no secret starts, prints only the URL, exit 0 (cli.py:30-44; probe patched `uvicorn.run`). Anyone who can reach the port can kill, revive, halt the fleet.
Tests: grep `0.0.0.0|--host|non-loopback` in tests: none; test_console_identity_c14.py:197-212 covers only the own-identity refusal.
Kill test: `serve` with a non-loopback host and no secret exits non-zero (or logs a refusal), and a loopback host still starts.

### F-C1082-OPS-10 | MEDIUM-LOW | conf HIGH | READ | CARRIED (declared; C-237 / D-29, C-200)
console.html:745, 826-828, 780: the perimeter secret is kept in sessionStorage and sent as `x-field-auth` on every request, including over plain http to a non-loopback host; only the operator pair is gated by `keyTransportOk()` (:764-768, :783). The "gate later" half of the ruling is not on main.
Tests: grep `field-secret` finds only setup_harness.mjs; no test asserts the secret is withheld on an insecure origin.
Kill test: jsdom run with an http, non-loopback origin asserts `x-field-auth` is absent and the secret is not stored (or the Declared row is updated and the test pins today's behaviour).

### F-C1082-OPS-11 | LOW | conf HIGH | PROBED | NEW
`/health` is an open path (authn.py `OPEN_PATHS`, api.py:404-407) and merges `op_health.health_fields()`. Probe with the secret set, ENFORCE and a missing roster file (made-up path): unauthenticated 200 returns operator_mode, roster hash prefix and row count fields, `last_registry_error` (`operator registry unreadable: FileNotFoundError`), refusal and break-glass counters. No path or key value, but it is operator-posture reconnaissance for an unauthenticated caller.
Tests: test_operator_health_g_ops_console.py:79-98 test the fields but never with `FIELD_SHARED_SECRET` set.
Kill test: with the secret set, unauthenticated /health returns only an allow-list of keys (ok, service, version).

### F-C1082-OPS-12 | LOW-MEDIUM | conf HIGH | PROBED | CARRIED (F-C644-3)
api.py:97-109 turns any `resp.json()` failure into `(0, str(exc))`, so an upstream 200 with a non-JSON body becomes a console 502 with the parser message although the action may have landed (probe: kill answered 200 empty-style body gives `502 {"detail":"Expecting value..."}`). A 3xx is relayed as the console's own status (probe: upstream 302 gives console 302 with nested detail, api.py:660). The page then shows "Refused: ..." for a kill that may have succeeded.
Tests: test_ops_console_c184.py:171, :207 pin the status-0 / exception-text behaviour as correct.
Kill test: upstream 200 with a plain-text body on kill: assert the status is preserved or the answer says "outcome unknown, check the ledger", and that a 3xx maps to 502.

### F-C1082-OPS-13 | LOW | conf HIGH | PROBED | NEW
Errors echo stored or caller text: the manifest refusals return the registry-set `ref` verbatim (api.py:523-525), e.g. an absolute path outside the dir (`/run/secrets/k.yaml`, made up) and a NUL-containing ref; the agent 404 echoes the caller id (api.py:498; probe `<b>x`). All are JSON and the page escapes them (console.html:1211, :1194), so no XSS; the issue is that a registrant-chosen path is reflected to any secret holder. The containment-before-existence order is correct (probe: `../x.yaml` and an outside symlink both 403, same text).
Tests: test_ops_console_c184.py asserts the refusals; no test asserts `ref` is withheld.
Kill test: assert a 403 for an outside absolute ref contains neither the ref nor any path component.

### F-C1082-OPS-14 | LOW | conf MEDIUM | READ | CARRIED (F-C523-2, test gap only)
api.py:645 `if op and key` forwards only a full pair; a header with only one of the two is dropped under OFF and refused under ENFORCE. Code is right; no test sends exactly one header: grep `HEADER_KEY|operator-key` in test_operator_auth_g_ops_console.py, test_console_identity_c14.py, test_ops_console_c184.py shows only full pairs and the "don, evil" 400. A mutant `op or key` would pass. I did not run a mutant.
Kill test: send id-only, key-only and empty-id-with-key to each guarded route under OFF and ENFORCE; assert nothing is forwarded and ENFORCE answers 401/400.

### F-C1082-OPS-15 | LOW | conf MEDIUM | READ | NEW
console.html:837, 1201, 1270: the dashboard treats every 401 as "shared secret missing" and opens the secret bar, including a 401 `operator credentials required` from `_operator_kw` under ENFORCE (api.py:649-652); the setup block tells the two apart (:1469, :1483-1488). The export path puts the raw reply text into an alert (:1271, :1278), so a proxy HTML error page or any upstream text shows whole. Both are text, not markup (alert, esc()), so no injection. All 25 innerHTML/insertAdjacentHTML sinks I read take esc() or constants; test_innerhtml_audit_c457.py and dashboard_xss_harness.mjs cover that class.
Tests: grep `Export refused|resp.text` none; no dashboard test sends a 401 for an operator refusal.
Kill test: jsdom: a guarded write answering 401 `operator credentials required` shows a sign-in hint and does not open the secret bar; an export failure shows a fixed message.

## Not verified
- Browser behaviour of console.html (not run in a browser; F-6, F-10, F-15 are READ for the page half). No jsdom or Chromium run.
- The Caddy edge (CSP, no-store, stream Cache-Control), covered by the PR 316 reports; not read.
- Whether downstream services re-check the body `operator` against the header pair (kill-switch uses `bind_body_operator`, seen by grep only, not run).
- Guard-to-read gap in the manifest route: `guarded_manifest_path` returns a resolved path, then `read_text` and `ManifestResolver(...).resolve_detail` read it again (api.py:521-532). A symlink swapped between check and read is not covered by tests (C-239 simulates the race inside the guard only). READ, not run, so not listed as a finding.
- Whether any finding above was already raised in a report body: I read only the first 15 lines of each earlier report plus their F-ids. NEW could be a re-discovery.
- The inherited `/operator/verify-hash` and `/operator/rotation-state` routes (field_core), the `/docs` and `/openapi.json` pages (401 without the secret; open when no secret).
- CSV export: the formula-lead guard works on the probed cases (`=`, `@`, `-`, `+` prefixed with `'`); a leading newline is not in `CSV_FORMULA_LEADS` (api.py:229) and I did not test spreadsheet behaviour.
- Full test suite of the service was not run.

---- SECTION 2: services/compliance-crosswalk ----

# Audit: services/compliance-crosswalk on main acaf5f24 (read-only worktree /tmp/claude-0/wt1079)

Probe scripts: /tmp/claude-0/m1082-cw/p1.py ... p4.py (made-up data only, TestClient / injected fakes, no network, no real key).

## Earlier coverage
(first 15 lines of each of the 6 matching reports in origin/comms comms/inbox/coordinator, plus targeted greps; reports were NOT read in full)
- 20261029-0300 C-232: 100-mutant round on evidence_pack/regwatch/staleness on 10fb197; found signer-newline injection (since fixed by C-252/C-389 in `_checked_signer`); noted "signed" means a name only.
- 20261029-0715 C-297: PASS on PR 151 (named-signer wording, header line); two LOW test gaps on header sentence and `Signer:` line.
- 20261029-1500 R-16: README/SPEC wording vs code (13 controls, 16/52 recounted); F-R16-1 stale LIMITS sentence about FC-E-04 (not carried: README:309 now says none cites).
- 20261103-0130 C-530: ADR Pack 07 vs src; F-C530-1 (ADR design elements read as built: model-drafted prose, retrieval corpus, per-tenant isolation) -> CARRIED, see F-C1082-CW-12.
- 20261103-1830 C-587: PR 332 wording of FC-F-01/FC-L-02 `evidence_kind` and engine `_evidenced` string; PASS.
- 20261104-0700 C-654: PR 335 ADR note; its note is NOT on main acaf5f24 (the ADR carries only the two 2026-10-29 notes).
Not covered by any of the six (per grep for FC-E-03, ledger_event_types, nan, collect_evidence, reviewed_by, last_check): everything in Findings except -12 and part of -2.

## Read
Read in full: src/compliance_crosswalk/{api.py, engine.py, evidence_pack.py, staleness.py, cli.py, regwatch.py, suggestions.py, self_manifest.yaml}; README.md (1-382); SPEC.md (1-65); demo.sh; docs/adr/ADR_Pack_07_Compliance_Crosswalk.md (all); docs/runbooks/v1.2-deploy-rollback.md lines 660-715 (+ grep hits for crosswalk); docs/ENVIRONMENT.md crosswalk rows (lines 34-82 grep); docs/ARCHITECTURE.md lines 25, 110, 204.
Read in part: mapping.py (lines 1-135 plus grep; the 13 control bodies were counted by import, not read line by line); spend-governor api.py status/caps routes; field_core authn.py, llm.py header; STATE.md lines 78-84; tasks/todo.md 845-856; integration/demo/docker-compose.yml (crosswalk service, tmpfs/read-only, FIELD_CROSSWALK_EVERY), Caddyfile line 75, fly entrypoint.sh line 65.
Tests: greped only (symbol/value greps named in findings); test bodies opened only for names. Test files checked: all 15 in services/compliance-crosswalk/tests plus services/force-gateway/tests/test_d2_llm_callers.py (grep).
NOT read: self_manifest.py, __init__.py, pyproject.toml, tests bodies, docs/capstone-evidence/*, IMPLEMENTATION.md, ROADMAP.md, CHANGELOG.md, root README.md (crosswalk mentions there not checked), the sealed-ledger/registry/delegation services beyond route-existence greps, field_core.validation internals, field_core.clients internals. Suite not run.

## Doc claims checked
Counts recomputed by import: 13 controls, 4 frameworks, 52 entries, 16 cited / 23 pending-text / 13 pending-purchase; FC-E-04..06 cite nothing.

| # | Claim (doc:line) | Symbol / location | Exists | Meaning matches |
|---|---|---|---|---|
| 1 | 13 controls, 16/52 cited (README:297, SPEC:15-17, api.py:104) | mapping.CONTROLS | yes | yes (probe p2) |
| 2 | INGESTION_LOG records what was read (README:13) | mapping.py:51 | yes | yes |
| 3 | guard test test_adversarial_no_ungrounded_citations (README:16) | test_crosswalk.py | yes | yes |
| 4 | routes POST /crosswalk, /crosswalk/markdown, GET /controls, /frameworks, /staleness, /health, POST /pack, /regwatch/check (README:33-43) | api.py | yes (route list probed) | yes |
| 5 | /health carries `every` (README:36) | api.py:125 | yes | yes |
| 6 | POST /pack 200 {markdown, pack}; 422 blank/missing signer, unknown body key; 409 {message, flags, affected_controls} (README:37-40) | api.py:165-197 | yes | yes (probed 422/409 shapes) |
| 7 | x-field-auth on every route but /health when FIELD_SHARED_SECRET set (README:46-47) | field_core/authn.py | yes | yes |
| 8 | `create_app(stale_store=None, fetcher=None, every=0)`, every never read from env (README:61-65) | api.py:64 | yes | yes |
| 9 | stale file `$FIELD_DATA_DIR/crosswalk_stale_flags.json` (README:63) | staleness.py:153-156 | yes | yes (default dir is "." when unset) |
| 10 | CLI verbs and options block (README:67-76, SPEC:56-58) | cli.py | yes (run, frameworks, pack, regwatch check/check-file/status/set-stale/clear, serve; also `version`, `suggest`, `self-manifest`, `--host` not in README block) | yes |
| 11 | "With --agent-id (CLI) or agent_id without sources (API), live evidence is collected" (README:78-81) | api.py:136-144 vs :165-176 | yes | NO: only POST /pack collects; POST /crosswalk and /crosswalk/markdown with agent_id and no sources report "evidence not collected (offline run)" (probe p1) |
| 12 | manifest REQUIRED; resolver `field_core.clients.resolve_manifest`; registry `manifest_ref` (README:52-60, api.py:41-48) | clients.py:514; agent-registry models.py:29 | yes | yes; plan item A3 in tasks/todo.md:852 yes |
| 13 | CROSSWALK_SUGGEST off\|mock\|anthropic, default OFF, unknown -> off (README:94) | suggestions.py:212-217 | yes | yes |
| 14 | CROSSWALK_SUGGEST_FLOOR 0.8 (README:97) | suggestions.py:220 | yes | partly: nan/inf/1e9 clamp to 1.0, see F-1 |
| 15 | "anthropic path requires a governor cap ... no unmetered LLM calls" (README:102-103) | cli.py:122-141 | yes | NO (overstated): only the `crosswalk suggest` CLI, only checks governor /status answers 200 (cap exists); crosswalk records no spend; library `suggest()` has no gate |
| 16 | self-manifest declares USD 5 daily (README:103) | self_manifest.yaml spend_cap | yes | yes |
| 17 | pack: three-part citation, "Signature is the action..." disclaimer (README:104-109) | evidence_pack.py:39-42, 224-240 | yes | yes |
| 18 | named-signer, no crypto signature, `Signer: NAME` + blank date, JSON `signer` text (README:110-114) | evidence_pack.py:196, 303-305, 311 | yes | yes |
| 19 | corpus `corpus-2026-08-08`; flag hard-blocks pack, exit 3, no override; clear logs reviewer+timestamp (README:116-121) | staleness.py:50, evidence_pack.py:154-161, cli.py:186 | yes | yes |
| 20 | regwatch inventory: OSFI 1 page, NIST 1 page, EU official ELI + 2 mirrors, ISO no-source (README:129-136) | regwatch.inventory() | yes | yes (probe p2) |
| 21 | anchors Principle 1.1/1.2/2.1/3.6; GOVERN 1.6...; MANAGE 2.4; Article 12/14 (README:150-152) | regwatch.inventory() anchors | yes | yes (p2: 1.1,1.2,2.1,3.6; GOVERN 1.6,2.1,2.3,6.1; MANAGE 2.4) |
| 22 | statuses baseline/unchanged/changed/unreachable/no-source; apply_mark; flagged_at kept (README:140-147) | regwatch.py:344-441, staleness.py:229 | yes | yes |
| 23 | C-255 missing-identifier flag, flagged again after clear (README:157-164) | regwatch.py:377-383 | yes | yes |
| 24 | exit codes 0/3/2, standing flags `STALE (standing)`, `flag_active` (README:178-187) | cli.py:245-255, regwatch.py:443-451 | yes | yes |
| 25 | thread lock + fcntl.flock/msvcrt, sidecar `.lock`, 30 s, StoreLockTimeout, unique temp + os.replace (README:188-199) | staleness.py:61-216 | yes | yes |
| 26 | egress: httpx, 20 s, https every hop, 8 MB, UA `field-platform-crosswalk/<version>`, no platform header (README:200-203) | regwatch.py:89-91, 235-277 | yes | yes |
| 27 | scheduler daemon thread, first tick after interval, exceptions swallowed; default 86400 in compose and Fly (README:204-207) | api.py:78-96, regwatch.py:666-703; docker-compose.yml:132, fly entrypoint.sh:65 | yes | yes |
| 28 | no clear route, /staleness GET-only (README:208-211) | api route list | yes | yes (p1) |
| 29 | conftest makes default client factory raise; CROSSWALK_LIVE_FETCH=1 live test (README:212-213) | tests/conftest.py, test_regwatch.py:894 | yes | yes |
| 30 | check-file: refusals list, `via: manual:<NAME>`, `file_sha256`, no HTTP route, last_check untouched (README:214-237, 288) | regwatch.py:531-659 | yes | yes |
| 31 | Manual procedure step 2 GB10: `docker cp /tmp/osfi-e23.html` into the container (README:247-249) | integration/demo/docker-compose.yml:92-100 (read_only root, tmpfs /tmp) | yes | NO (stale): runbook v1.2-deploy-rollback.md:688-690 (C-323) says docker cp does not place a file into a tmpfs and streams it with `docker exec -i ... cat >` instead |
| 32 | signer gate: empty, >200 chars, control/format/line-break refused, "a name you can see on one line"; 422 over HTTP (README:274) | evidence_pack.py:104-135 | yes | partly: refuses Cc/Cf/Zl/Zp only; U+3164, U+2800 and "." accepted (F-9) |
| 33 | "Evidence verdicts come from real artifacts - Enforced in code" (README:271) | engine.py:127-175, api.py:174-176 | yes | NO (overstated): `sources` in the request body is used as-is (README:80-81 says so), FC-E-03/FC-F-01/FC-L-02 return True without an artifact (F-4, F-5) |
| 34 | named-signer header text pinned by test_evidence_pack.py (README:275) | test_evidence_pack.py:115 | yes | yes (C-297: prefix only) |
| 35 | README Enforced-vs-Declared test names (README:281-286, 288): 14 named tests + `test_run_every_*` | tests/*.py | yes (all 14 found by `def` grep) | yes by name; bodies not read |
| 36 | FC-F-01, FC-L-02 declaration-only (README:300-301) | engine.py:174-175 | yes | yes |
| 37 | FC-E-04..06 keys, evidenced null, detail text, none cites anything, "every other manifest now shows 10/13 declared" (README:302-314) | engine.py:76-107, 130-133 | yes | yes (self manifest: 10 of 13, probe p4) |
| 38 | cites "ADR-0074" (README:302, SPEC:15) | no ADR-0074 file in repo (only STATE.md:78 "Harness ADR-0074") | no | unresolvable in-repo (LOW, F-11) |
| 39 | OSFI 403 to honest UA (README:315-323) | live behaviour | not checkable | not verified |
| 40 | Anthropic suggester routing FORCE_GATEWAY_URL > ANTHROPIC_BASE_URL, `x-force-passthrough: judge`, tested in force-gateway test_d2_llm_callers.py (README:375-382) | field_core/llm.py:7-14; test file lines 20-127 | yes | yes (grep; bodies not read) |
| 41 | ENVIRONMENT.md:34 ANTHROPIC_API_KEY -> suggestions.py:168 | suggestions.py:168 | yes | yes |
| 42 | ENVIRONMENT.md:43 CROSSWALK_SUGGEST -> suggestions.py:212 | yes | yes | yes |
| 43 | ENVIRONMENT.md:44 CROSSWALK_SUGGEST_FLOOR 0.8, "clamped; empty or non-numeric falls back to 0.8"; "1.0 makes all suggestions review-required in practice" -> :221 | suggestions.py:221-225 | yes | NO: "nan" parses and clamps to 1.0 (no fallback); at floor 1.0 a confidence of exactly 1.0, or NaN/inf from the model, still becomes a candidate (F-1) |
| 44 | ENVIRONMENT.md:45 CROSSWALK_SUGGEST_MODEL -> :166 ; :56 FIELD_CROSSWALK_EVERY -> cli.py:351 ; :58 FIELD_DATA_DIR "'.' in crosswalk staleness store"; :59/:64/:82 service URLs | suggestions.py:166, cli.py:351, staleness.py:154, api.py:223-225, cli.py:128 | yes | yes |
| 45 | ARCHITECTURE.md:204 store file + zero-byte `.lock` sidecar, cleared by name on CLI | staleness.py | yes | yes |
| 46 | runbook :671-678 /regwatch/check + /staleness `last_check` snippet; :710-714 StoreLockTimeout after 30 s, exit 1 | api.py, staleness.py:65-136 | yes | yes (exit 1 not run) |
| 47 | SPEC:21-33 evaluate(), CLI collector, 422 blank signer / 409, `last_check` on /staleness, FIELD_CROSSWALK_URL | engine.py, api.py | yes | yes |
| 48 | ADR Pack 07 ADR 1 "drafts evidence-pack prose" (:12), ADR 3 "Retrieval over a version-pinned corpus ... per-tenant isolation" (:48, :51) | no such code (grep tenant: none; pack text is generated by code) | no | NO, CARRIED F-C530-1 (F-12) |

Stale or wrong (doc file:line): README.md:78-81 (#11); README.md:247-249 (#31); README.md:271 (#33); README.md:102-103 (#15); docs/ENVIRONMENT.md:44 (#43); README.md:302 and SPEC.md:15 (#38); docs/adr/ADR_Pack_07_Compliance_Crosswalk.md:12, :48, :51 (#48, CARRIED). Total 7 doc locations (6 new, 1 carried).

## Findings

Fail-closed summary by path: `generate_pack` signer gate, stale block, `evaluate` on odd manifests (p3: 4 odd shapes, 700-deep nesting all 200, no crash) and regwatch (any fetch error -> unreachable, never changed) fail closed. Exceptions: F-6, F-7.

**F-C1082-CW-1** suggestions.py:203 (`max(0.0, min(1.0, float(...)))`), :256, :270 (`confidence < floor`). MEDIUM, confidence HIGH, PROBED.
NaN, Infinity or the string "nan" returned by the model clamps to 1.0 (`min(1.0, nan)` is 1.0), so it passes the 0.8 floor and becomes a `candidate`. With the deterministic mock, NaN passes `nan < floor` (False) and a candidate with confidence NaN (serialised `null`) is emitted. Probe p2: real `AnthropicSuggester` with a fake client and a made-up key, framework valid, confidence NaN/"nan"/Infinity -> `candidate` 1.0; 0.3 -> review-required. Floor env: "nan"->1.0, "-1"/"0"->0.0 (gate off), "1e9"->1.0. Fail-open on the one gate the ADR leans on (still labelled SUGGESTION ONLY). Untested: grep `nan|NaN` in test_suggestions.py: none (matches only in test_crosswalk.py/test_regwatch.py, unrelated); test_d2_llm_callers.py only covers routing.
Kill test: add a suggestions test where the suggester returns NaN/inf/"nan" confidence and assert status "unmapped - review required" (reject non-finite in `suggest_one` and `suggest`).

**F-C1082-CW-2** engine.py:21 (`ledger_event_types: dict[str,int]`). LOW, confidence HIGH, PROBED. CARRIED (PR 394 per card; not in the six reports found; NOT fixed on main).
POST /crosswalk and POST /pack with `sources.ledger_event_types {"MADE-UP-KEY":"x"}` -> 422 with `loc [..., "ledger_event_types","MADE-UP-KEY"]` and `input` echoed (p1). FastAPI default also echoes the whole request body in `input` for a missing field (missing signer echoes manifest and sources). Caller's own input; no secret path or server value. Test: grep `ledger_event_types` in tests = test_crosswalk.py only, no 422 shape test.
Kill test: POST /pack with a non-int `ledger_event_types` value and assert the 422 body contains neither the key nor the value.

**F-C1082-CW-3** evidence_pack.py:194 (`agent_id`), :254 (gap detail), engine.py:151 (ledger reason). MEDIUM-LOW, confidence HIGH, PROBED.
The signer is sanitised (C-252/C-389) but `agent_id` and caller-supplied `sources.ledger_verify.reason` are written into the pack Markdown raw. p1: `agent_id="x\n\n## Signature\n\nSigner: Mallory\n\nDate: ..."` -> pack has an extra `## Signature` / `Signer: Mallory` block before the real one; `reason` with newlines injects `## Fake heading` and `Signer: Mallory` into Gaps. Same class as the C-232 signer finding. Tests: grep `agent_id` in test_signer_sanitise_c252.py / test_evidence_pack.py: no control-char case.
Kill test: pack generation with a newline in agent_id or in ledger_verify.reason must be refused (422) or rendered on one escaped line, asserted by counting `## Signature` headings == 1.

**F-C1082-CW-4** engine.py:167-175 (FC-E-03), :174-175 (FC-F-01, FC-L-02). MEDIUM-LOW, confidence HIGH, PROBED.
With manifest `{}` (declared False) and any one non-None source (`tokens=[]`), FC-E-03, FC-F-01, FC-L-02 return `evidenced=True`, and `evidenced_count` is 3 (p4). No artifact is read for these; FC-E-03 returns True even with 0 escalation events. The pack table prints `evidenced: yes` next to `declared: no`. README:300-301 and the detail strings disclose "declaration-only", but README:271 says verdicts "come from real artifacts" and the Markdown pack table has no such marker. Tests: grep `FC-E-03` / `shadow_escalate` in test_crosswalk.py checks counts only; no declared=False + evidenced case.
Kill test: assert evidenced is not True for a control whose manifest path is not declared (return None for declaration-only controls), asserted on the pack table.

**F-C1082-CW-5** api.py:174-176, evidence_pack.py:142-152. MEDIUM-LOW, confidence HIGH, PROBED.
`sources` in a POST /pack body is used as-is and the pack records neither that evidence was caller-supplied nor where it came from. p1: a forged `ledger_verify {ok:true}`, token, cap, kill event produces `evidenced: yes` on 10 controls in a pack handed to a named signer. Documented at README:80-81 but contradicted by README:271. With the shared secret unset (default, authn.py) anyone reaching the port can do this.
Kill test: pack JSON and Markdown must carry an `evidence_provenance` of collected / supplied / none, pinned by a /pack test with body `sources`.

**F-C1082-CW-6** evidence_pack.py:264-266, staleness.py:165-166. MEDIUM-LOW, confidence HIGH, PROBED.
A missing store file (wrong FIELD_DATA_DIR, default ".", or a fresh volume) is an empty state, and the pack prints "No active stale flags." with `last_check` null. p3: FIELD_DATA_DIR pointing at a nonexistent dir -> POST /pack 200. A pack can ship although regwatch has never run or the flags live in another directory (README:371 admits a workstation flag does not block an estate). Tests: grep `last_check` in test_evidence_pack.py/test_pack_api.py: not asserted on pack text.
Kill test: when `last_check` is null the pack Markdown must say "corpus never checked" instead of "No active stale flags." (pinned in test_evidence_pack.py).

**F-C1082-CW-7** api.py:186-187 (`except ValueError` -> 422 `str(exc)`), staleness.py:167-171, :302. LOW, confidence HIGH, PROBED.
Store problems are fail-closed but misreported: corrupt JSON -> JSONDecodeError (a ValueError) -> 422 `Expecting property name...` blaming the client; a flag naming an unknown framework -> 422 `unknown framework`; a flag `{}` or a bad `flagged_at` in `/staleness` -> 500 (p3); GET /staleness on corrupt file 500. No pack ships. Untested: grep `JSONDecodeError|corrupt|not json` in tests: none.
Kill test: /pack with a corrupt stale file must return 5xx (not 422) and no pack, and /staleness must return a JSON error body.

**F-C1082-CW-8** api.py:227, :234-237 (`agent_id` interpolated into internal URLs). LOW-MEDIUM, confidence HIGH, PROBED (URL construction only, httpx mocked, no network).
`collect_evidence` (reached by POST /pack with agent_id and no sources, and by the CLI) puts `agent_id` into path and query unencoded, with `auth_headers()` attached (shared secret, operator headers). p2: `agent_id="a&limit=1/../../escalations"` -> `.../events?agent_id=a&limit=1/..`, and `/caps/a&limit=1/../../escalations` normalises to `/escalations` on the governor. Host cannot change (fixed base), but path and query can be redirected inside each internal service; a 200 dict makes FC-E-02 evidenced. Also `e["event_type"]` KeyError / non-list payload -> 500 outside the try (:229-230). Tests: grep `collect_evidence` -> test_pack_api.py monkeypatches it away; its body is untested.
Kill test: unit-test `collect_evidence` with `agent_id` holding `/`, `&`, `..` and assert it is refused or percent-encoded in all four URLs.

**F-C1082-CW-9** evidence_pack.py:109, :129-134; regwatch.py:582. LOW, confidence HIGH, PROBED.
Signer gate refuses Cc/Cf/Zl/Zp only. p1: U+3164 (Hangul filler), U+2800 (braille blank), "." and "---" and a lone combining mark are accepted as the signer; the check-file name rule requires a letter or digit but the pack signer does not. README:274 says "a name you can see".
Kill test: signer with no letter or digit (and invisible fillers) is refused 422/exit 2, test in test_signer_sanitise_c252.py.

**F-C1082-CW-10** staleness.py:254-257. LOW, confidence HIGH, PROBED.
`StaleStore.clear` only checks non-blank: `reviewed_by="\x1b[31m.\n"` is accepted and stored raw in history (p1), unlike check-file `--fetched-by` (regwatch.py:572-585). The clear is the one human gate on stale packs (README:119). Tests: grep `reviewed_by|reviewed-by` -> blank case only (test_staleness.py), no control-char case.
Kill test: `clear` applies the same plain-name rule as `_named_human` and refuses control, invisible or no-alnum names, asserted via CLI exit code.

**F-C1082-CW-11** README.md:102-103, cli.py:122-141. LOW-MEDIUM, confidence MEDIUM, READ.
"No unmetered LLM calls" is a presence check of a governor cap by the CLI `suggest` only (`# pragma: no cover`, never tested): any 200 from `/status/compliance-crosswalk` passes, whatever the spend state; crosswalk itself posts no spend/usage (grep: none); metering depends on the gateway path being configured (FORCE_GATEWAY_URL), otherwise the call goes straight upstream. Library `suggest()` has no gate.
Kill test: a CLI test with a fake governor returning a blocked status must exit non-zero, and the README line reworded to what is checked.

**F-C1082-CW-12** docs/adr/ADR_Pack_07_Compliance_Crosswalk.md:12, :48, :51. MEDIUM (doc), confidence HIGH, READ. CARRIED from C-530 F-C530-1; still on main (the PR 335 note is not on acaf5f24).
ADR text still reads as built: model-drafted evidence-pack prose, retrieval over a version-pinned corpus, per-tenant isolation (grep `tenant` in src and tests: none; pack text is code-generated).
Kill test: docs card adds a dated "not built" note per element, and a test greps the ADR for that note.

**F-C1082-CW-13** engine.py:124. LOW, confidence HIGH, PROBED (on /crosswalk).
`declared_detail` embeds `repr(value)[:120]` of the manifest value; a manifest value carrying a token (probe: made-up `?token=MADE-UP` in a kill-switch endpoint) is echoed in the response and in the pack JSON `controls[].declared_detail` that goes to auditors (Markdown shows it only for undeclared gaps). Truncation at 120 can cut mid-token.
Kill test: pack JSON `declared_detail` contains the path and presence only, never the manifest value (assert a made-up secret string is absent).

Untested branches (grep evidence): GET /controls (grep `/controls` in tests: none); POST /crosswalk/markdown (only referenced in route-list tests: test_regwatch_api.py, test_regwatch_check_file.py); CLI commands `run`, `frameworks`, `suggest`, `self-manifest`, `status`, `set-stale` (grep of `"run"|"frameworks"|"suggest"|"self-manifest"|"status"|"set-stale"` in `invoke` calls: none; `clear` only via subprocess in test_regwatch.py:533); `collect_evidence` body; FC-E-06 `per-session`/`per_session` period variants (grep: none in tests); AnthropicSuggester (pragma, routing only in force-gateway test).

Counts: HIGH 0, MEDIUM 2 (F-1, F-12 doc, carried), MEDIUM-LOW 4 (F-3, F-4, F-5, F-6), LOW-MEDIUM 2 (F-8, F-11), LOW 5 (F-2 carried, F-7, F-9, F-10, F-13). Total 13; PROBED 11, READ 2.

## Not verified
- Suite not run; no live service, no network; collect_evidence probed with httpx mocked, AnthropicSuggester with a fake client.
- Whether the 16 cited passages say what the table claims (R-16 objection 1; needs source texts).
- OSFI 403 and live-host behaviour (README:287, :315-323); runbook exit-1 on StoreLockTimeout not run.
- mapping.py control bodies beyond counts; field_core.validation and clients internals; root README, CHANGELOG, ROADMAP, capstone-evidence, IMPLEMENTATION mentions of the crosswalk.
- Whether PR 394's fix exists on another branch (only main acaf5f24 checked); the earlier reports were read for 15 lines plus greps, so overlap with F-4 and F-2 is judged from greps only.
- Windows (`msvcrt`) lock path; Fly/GB10 deployment settings beyond compose and entrypoint greps.

---- SECTION 3: packages/field-agent ----

# field-agent audit, main acaf5f24 (packages/field-agent)

## Earlier coverage
- 20261029-0200 reviewer-c102 (PR 68): FieldClient env-proxy removal and 64 KiB read cap (C-41 findings 1, 2); PASS. Not repeated.
- 20261029-0625 reviewer-c289 (PR 144): pins for canary `_drain` (chunked/oversize/non-positive length), heartbeat-age boundaries, federation arg checks; one gap (chunked-test did not pin its guard, later fixed by C-299 at test_pins_c145.py:96-101).
- 20261029-1600 reviewer-r17: mutation of canary.py, agent.py, federation.py (87 mutants, 12 survived); NOT mutated or read line by line: bootstrap, liveness, usage, cli, _transport. Records F-C48-1/D-12 (canary 0.0.0.0 + marker header).
- 20261104-1530 reviewer-c704 (PR 359): canary read cap; says heartbeat path (liveness.py) is unbounded and echoes body (READ, not probed).
- 20261104-2200 reviewer-c736 (PR 359): cap pinned; F-C736-1 byte-bound not time-bound; F-C736-2 httpx clients in bootstrap/federation/liveness/usage unbounded (stated, not probed).
- Open PRs: 359 adds canary.py read cap + test_canary_response_cap_c106.py + a FieldClient cap pin. On MAIN the FieldClient cap already exists (field_client.py:161-163) but has no test; the canary cap does not exist. 409 (SDK read cap): not read; I did not open the PR.

## Read
READ in full on acaf5f24: src/field_agent/{field_client,_transport,errors,canary,liveness,bootstrap,federation,agent,usage,cli,actions}.py; field_core/errors.py `upstream_error` only.
Tests: grepped (symbols named per finding) in packages/field-agent/tests/*.py; opened no test body fully.
NOT read: `__init__.py`, SPEC.md, README.md, examples/, demo.sh, conftest.py, field_core.authn.auth_headers, conformance_sentinel.governed.Governor (the SDK's sentinel path: its error/echo/read behaviour is unaudited), server-side validation in governor/kill-switch, PRs 359 and 409 diffs, docs/ENVIRONMENT.md beyond 3 rows.
Probes: /tmp/claude-0/m1082-fa/probe.py and probe2.py (local 127.0.0.1 listeners, made-up data, made-up secret strings, proxy env unset first). No file in the worktree was changed.

## Findings
Fail-closed summary (PROBED/READ): FieldClient.check/killed/report_usage/guard fail closed on every non-200, transport, parse, oversize (probe P10: 64 KiB+ reply and 50k-deep JSON both gave BLOCK), redirect cases. FieldAgent/Governor path fails closed by raising. No fail-open of a verdict found except F-8 (config-only). Echo/size problems below are all on the httpx clients.

**F-C1082-FA-1** MEDIUM-LOW, conf HIGH, PROBED. canary.py:357 and :359 `resp.read()` / `exc.read()` unbounded; also `count()` :384 takes `len(body)` of an unbounded list. Probe: 8,000,000-byte JSON reply from a loopback listener was returned whole by `urllib_call`. Addressed by PR 359 (size only; PR not audited). Test that kills it: "urllib_call against a listener sending 1 MiB returns the response_too_large marker and reads at most cap+1 bytes". Tests checked: grep `urllib_call` in tests (test_canary_agent.py:376,411, test_canary_operator_headers.py:98): no oversize case.

**F-C1082-FA-2** LOW-MEDIUM, conf HIGH, PROBED. CARRIED (F-C736-1), still on main. Read has per-operation timeout only: canary.py:357, field_client.py:161. Probe: FieldClient(timeout=0.5).killed() against a listener dripping 16 bytes at 0.3 s returned in 4.5 s. Kill: "a reply dripped past a total deadline returns failure (killed()=True / transport_error) within timeout+epsilon". Grep `drip|monotonic|deadline` in tests: not run against canary tests; test_field_client*.py has no such case (grep of `timeout` not done; READ for the gap).

**F-C1082-FA-3** MEDIUM-LOW, conf HIGH, PROBED. CARRIED (C-704 obj 1, C-736 F-2), not fixed by PR 359 per its reports. liveness.py:65-69 non-200 puts the whole `resp.text` in HeartbeatUnreachable, and the body is read unbounded. Probe: 3,000,000-byte 500 reply gave a 3,000,052-char exception message. This is the halt-deciding path of the canary (canary.py:275). Kill: "heartbeat non-200 error message contains the status and no body byte, and a 3 MB reply is not fully read". Tests grepped: `resp.text|\.text|trust_env` in tests: none for liveness (test_bootstrap_errors_c503.py covers bootstrap only).

**F-C1082-FA-4** MEDIUM-LOW, conf HIGH, PROBED. usage.py:330-336 and :367-373: non-200 puts `resp.text` into UsageReportError; 404 puts `.json()["detail"]` (any JSON type) or whole text into NoSpendCapError. Probe: 2,000,000-byte 404 text gave a 2,000,000-char NoSpendCapError; a JSON `detail` object arrived as a dict in `args[0]`. cli.py:533 prints it to stderr. The same C-503 class that bootstrap.py fixed with `upstream_error`. Kill: "usage.report/spend non-200 and 404 messages are `what returned N` only, str-typed, body-free". Tests grepped: `NoSpendCapError` (test_field_agent.py:139-140) asserts the class only, not the message; no body-echo test.

**F-C1082-FA-5** MEDIUM-LOW, conf HIGH, PROBED. federation.py:329-331: reasons/clause_id from the broker verdict echoed unbounded (probe: 100,021-char message from one 100 KB reason), and `reasons` that is not iterable (JSON 5) raises a bare TypeError, not CrossingBlocked, so `fieldagent cross` (cli handles CrossingBlocked/ValueError/OSError/YAMLError, federation.py:387-394) ends in a traceback. :313 echoes `str(exc)` of the transport error. :318 body echo is capped at 300 (probe: 376 total, fine). :321 reads the body unbounded. Fail-closed (an exception, never ALLOW). Kill: "a verdict with non-list reasons raises CrossingBlocked, and a 100 KB reason is truncated in the message". Tests grepped `reasons` in test_federation_sdk.py: only list fixtures (:185,203,233).

**F-C1082-FA-6** MEDIUM, conf HIGH, PROBED. Env-proxy exposure for every httpx client: liveness.py:42, usage.py:300, federation.py:229, agent.py:51 (sentinel client), bootstrap.py:93. httpx.Client keeps `trust_env=True`; probe: with a made-up HTTP_PROXY set, the client gains a proxy mount (0 mounts without it), and AuthedClient (_transport.py:260-262) adds the shared secret header to every request, so the secret goes to the proxy. Same class as C-41 finding 1, fixed only in field_client.py:80. Kill: "with HTTP_PROXY/ALL_PROXY set, every SDK client built with client=None has no proxy mount (trust_env False)". Tests grepped `trust_env`, `HTTP_PROXY|HTTPS_PROXY|ALL_PROXY`: only test_field_client_proxy_c53.py (FieldClient).

**F-C1082-FA-7** LOW-MEDIUM, conf HIGH, PROBED. liveness.py:70: a 200 that is not JSON, or lacks fields, raises JSONDecodeError / pydantic ValidationError, not HeartbeatUnreachable. Callers that `except AgentKilled` to halt (errors.py docstring contract; cli.py:458, :475) get a traceback instead of the halt path (canary catches Exception, canary.py:276, so it is safe). Pydantic text also echoes input values. Fail-closed by crash. Kill: "heartbeat 200 with invalid body raises HeartbeatUnreachable". Tests grepped `ValidationError`: none.

**F-C1082-FA-8** LOW-MEDIUM, conf HIGH, PROBED. agent.py:83-86 and :173-176: `heartbeat_max_age=float('nan')` makes the staleness test always False, so after one successful poll the kill-switch is never polled again (probe: 1 heartbeat call over 3 checks vs 3 with 0.0). Config-only; no validation in `__init__` (:42-66). Kill: "FieldAgent(heartbeat_max_age=nan or negative or bool) raises ValueError". Tests grepped `heartbeat_max_age`: test_field_agent.py:188 (0.0), test_pins_c145.py:226 (30.0), federation :375.

**F-C1082-FA-9** MEDIUM-LOW, conf HIGH, PROBED. bootstrap.py:164: `DelegationToken.model_validate(resp.json())` on a malformed 201 raises ValidationError whose text carried the made-up `secret` and `token_id` values (probe: both present). cli.py:555 catches only BootstrapError, so the traceback prints them. Also :130 `resp.json()` ValueError uncaught (probe: bare ValueError). Kill: "mint with a 201 body of wrong shape raises BootstrapError and the message contains no body value". Tests: test_bootstrap_errors_c503.py:26,32 cover non-201 only.

**F-C1082-FA-10** LOW, conf HIGH, PROBED. field_client.py:229-236 `_private_host` uses ip.is_private, which accepts link-local (169.254.x) and 0.0.0.0; the secret then goes over plain http (probe: both accepted with a secret). Kill: "FieldClient refuses a secret over http to link-local and unspecified addresses". Test grep `private|loopback` in test_field_client.py: :153 `test_secret_needs_https_or_private_host` only checks one public and loopback.

**F-C1082-FA-11** MEDIUM-LOW, conf MEDIUM, READ. _transport.py:260-262 AuthedClient attaches the secret to any URL; no https-or-private-host rule (FieldClient has one, field_client.py:138). A `FIELD_*_URL` env var (liveness.py:36, usage.py:294, federation.py:223, bootstrap.py:112,146) set to a public http URL gets the secret in clear. Kill: "AuthedClient refuses to attach x-field-auth to a plain-http non-private URL". Tests grepped `FIELD_SHARED_SECRET`: none for this.

**F-C1082-FA-12** LOW, conf HIGH, PROBED. canary.py:226-232 (halt body) and :363 (urllib_call): `except ValueError` misses RecursionError. Probe: a 40,000-deep JSON body to POST /halt with the marker header gave no reply and no halt (traceback in the handler); an 8 MB-class deep reply to urllib_call raised RecursionError although the docstring says no message/exception leaks (x3-check would end in a traceback). FieldClient catches it (field_client.py:171). Kill: "deep-JSON halt body gets a defined reply; deep-JSON reply to urllib_call returns the non_json marker". Tests grepped `RecursionError`: none.

**F-C1082-FA-13** LOW, conf MEDIUM, PROBED. agent.py:112-127 / usage.py:303-323: counts are not validated; probe sent input_tokens=-5 and output_tokens=True to the governor. FieldClient.report_usage rejects both (field_client.py:201-203). The governor's own checks were not read. Kill: "FieldAgent.report_usage rejects negative/bool/non-int counts before any request".

**F-C1082-FA-14** LOW, conf MEDIUM, READ. cli.py:494-509: `fieldagent check` documents exit 2 = ESCALATE; click usage errors (missing argument, bad option) also exit 2 (general knowledge), so a wrapper cannot tell ESCALATE from a malformed call. Fail-closed either way. Kill: "a usage error exits with a code other than 0, 1 and 2, or a test pins and documents the overlap". Tests grepped `exit_code == 2`: no match in the two files checked.

**F-C1082-FA-15** LOW, conf HIGH, READ + grep. field_client.py:161-163 (cap, `raw = b""`) has no test on main: grep of `65536|64 \* 1024|too_large|oversize` in test_field_client.py and test_field_client_proxy_c53.py: no match. Addressed by PR 359 (pin). Kill: "a 64 KiB+1 reply to check() gives BLOCK and reads at most cap+1 bytes".

CARRIED, unchanged (not re-derived): canary 0.0.0.0 bind with marker-only header (canary.py:73-74, :219, :243, :480; F-C48-1/D-12; DECLARED in the module docstring :28). The 403 body echoes only the fixed header name and halted flag (:220); no caller input is echoed.

## Not verified
- PR 359/409 behaviour; whether they change any line cited here.
- Governor (conformance_sentinel) response echo, size bounds, test gaps: not read.
- Server-side limits that may make F-13 harmless.
- F-11, F-14: not run. Click exit-code claim is from general knowledge.
- Thread-safety of FieldClient._escalated (field_client.py:147, :224) and its unbounded growth: noticed, not tested.
- Untested-branch list is by grep only, for the symbols named; no coverage tool was run and the full suite was not run.

---- CONCLUSION ----

1. No HIGH finding. The first fixes by value: F-OPS-9 (refuse a non-loopback `serve` with no secret; a Don decision on the default), F-FA-6 (`trust_env=False` on every SDK client, as FieldClient already has), F-CW-1 (a NaN confidence is refused, not clamped to pass), then the unbounded error bodies in field-agent (liveness, usage, bootstrap) and the seven stale doc locations in the crosswalk.
2. Carried and still open on main: the PR 348 proxy hardening items for ops-console (five findings), the canary unbounded read (PR 359), the engine.py:21 `ledger_event_types` key echo in the crosswalk 422 (PR 394, marked LOW).
3. Everything above is READ or probed on made-up data; none of it is GX10 or estate evidence.

## NOT VERIFIED

- Whole-scope line-by-line reads (see each section's "Read" and "Not read"): ops-console console.html markup and CSS, the sentinel Governor path (already under C-1079), PRs 359 and 409, SPEC/README/examples of field-agent.
- That each sub-agent finding reproduces under a builder's test; the probe scripts are not committed.
- Any browser behaviour of console.html.
