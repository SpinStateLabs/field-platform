# RED TEAM: STAGE-2 report (kill-switch REQUIRE). ssl-fp-red-team, 2026-11-05 18:50Z
Head tested: main 3804d0b9 (own checkout, read-only). Evidence (not in repo): D:\dev-cache\rt (stage2_harness.py, s2extra.py, mut*.py).

## VERDICT: BLOCKERS (unmet prerequisites; no exploitable hole found in the REQUIRE code)

| ID | Sev | Finding | Conf |
|----|-----|---------|------|
| B-RT-g22-not-landed | BLOCKER (policy: D-12, architect G22 decision) | FIELD_INTERNAL_SECRET / `x-field-internal` is not on main (0 hits in code). PR 374 is an OPEN DRAFT (b97d35fc). Repro: stack with FIELD_SHARED_SECRET only; `POST /operator/verify-hash {"operator_id":"don","key_sha256":<hash>}` with only `x-field-auth` answers 200 `matched:current, matchable_now:true`; `GET /operator/rotation-state` likewise. Under ENFORCE any perimeter holder is answered. | HIGH |
| B-RT-g24-absent | BLOCKER (policy: Don guardrail "G23/G24 on main") | No stage controller on main: `stage_transition`/`stage_aborted` exist only as AlertClass definitions in field_core/alerts.py and in docs; tools/ holds only phase_g_check.py. No automatic rollback on abort. | HIGH |

## Attacks run
Real 3-process stack: ledger + registry LOG-ONLY, kill-switch ENFORCE, perimeter secret on; about 90 probes; every refusal also asserts the agent stayed active.
- PASS (HIGH): no creds 401; id only / key only 401; wrong key, unknown id, id/key mismatch, revoked id, drill-only scope, stored HASH presented as the key, id case change, key case change: all 403. Unauth domain kill / revive / drill: 401.
- Header smuggling (HIGH): duplicate id or key header, comma-joined, non-ASCII, tab, 65-char id, 257-char key, empty key, obs-fold line: 400. Underscore header names ignored (401). CL+TE / TE variants: no smuggled second request authenticated. x-forwarded-*, forwarded, `x-field-operator-on-behalf-of`, `x-field-kill-origin` without creds: 401.
- Path tricks never kill: `/kill/a/`, `//kill/a`, upper case, `%00`, `%6bill`, `/health/../kill/a`, `;`. 60 parallel unauth kills: all 401.
- Alias confusion (HIGH): id `don` vs a manifest listing only an alias held by another row: 403; alias operator vs list naming `don`: 403; `*` scope does not bypass authorized_operators; alias used as id header: 400.
- Replay (HIGH): bearer replay works while the key is valid (declared limitation); after the row is revoked in the file the replay is 403 on the next request.
- 422 echo (HIGH): the kill-switch 422 never repeats caller text (extra field, wrong type, list body, malformed JSON, key-shaped values). An authenticated caller sees its own reason/operator in the 200 report and its path agent id in a 404 (by design, LOW).
- Operators file (HIGH): every one of 16 corrupt variants answers 503 with the agent still active: missing, empty, directory, binary, all-revoked, `[]`, `null`, truncated, duplicate JSON key, `Active`, uppercase or padded hash, duplicate operator_id, 5000-deep nesting, NaN, format 3. BOM+CRLF and `\u0064on` escapes parse and authenticate. A Cyrillic-o row never matches an ASCII header.
- Mode switching (HIGH, in-process): REQUIRE unset/blank = OFF; `0/false/no/off` (any case, padded) = LOG-ONLY when a registry path is set; any other value (`enforce`, `2`, `disabled`, `none`, `tru`, unicode digits) = ENFORCE; REQUIRE=1 with registry unset or `0` = 401/503, never open. Mode is read per call.
- Outbound (HIGH): the halt-signal client sends no operator headers and uses trust_env=False (no HTTP_PROXY bypass).
- FIELD_SHARED_SECRET (HIGH): only /health is open; `/health/` and encoded variants do not bypass.
- Failure paths (HIGH): ledger down: unauth refusal 401 in 0.00 s, authed kill still 200 (audit row lost, `ledger_note_failures` counted, kill took 6.2 s). Registry down: authed kill 502, nothing changes.
- Secret hygiene (HIGH): no key, hash or perimeter secret in /health or in the kill-switch log (scanned).
- Ledger forgery (HIGH): a perimeter-only POST /events with reserved operator keys (top level and nested) is stored with them stripped; `operator.refused` rows are stamped `self_reported: true`.

## Non-blocking findings
- N-1 MEDIUM, HIGH, DECLARED: at Stage 2 the registry is LOG-ONLY, so any perimeter-secret holder can `PATCH /agents/{id}` status (revive a killed agent) or `manifest_ref` (swap the authorized_operators list) with no operator credential (repro: both 200). Stage 2 protects only the kill-switch routes. The go sentence should say so.
- N-2 LOW/MEDIUM: non-ASCII `x-field-auth` gives 500 (TypeError in `hmac.compare_digest(str,str)` in the authn middleware). Fails closed, but an unauthenticated caller can raise 500s and tracebacks. Fix: compare bytes.
- N-3 MEDIUM: refusal evidence is capped: 56 of 62 `operator.refused` rows were dropped in a 60-request flood (counted in `dropped_refused_records`; never blocks a kill).
- N-4 LOW: an authenticated caller can send `x-field-kill-origin` to skip the outbound halt signal (the kill and its ledger row still happen).
- N-5 LOW: the format 1 loader silently drops a row whose id has a lone surrogate instead of failing the file (fail closed for that identity; contradicts "one bad row = unavailable").
- N-6 LOW: lifecycle auto-kill, the X3 check and keyless tools answer 401 at Stage 2 (documented, runbook ~1481).
- N-7 LOW: verify-hash is an online hash oracle for a perimeter holder (needs a guessed 160-bit key hash); closed by G22.

## Mutation testing (16 hand mutants of operator_auth.py, kill-switch api, registry PATCH)
KILLED 15: registry-unavailable fails open; revive, drill and domain-kill guards dropped; authorized_operators skipped in kill; unknown REQUIRE value = off; duplicate headers first-wins; revoked accepted; scope check skipped; key not checked; hash-prefix match; registry-unset => open; registry PATCH status unguarded under ENFORCE; empty-list ordering (unauth allowed); incomplete-credential check.
SURVIVED 1 (test gap, the code is correct): M8, `check_authorized` made case-insensitive (operator `Don` would satisfy a list naming `don`); 300 tests still pass. Needs a test that a case-different id is refused by a manifest list. Non-blocking.
Note: M7, M9, M13 first looked like survivors only because `packages/field-core/tests/test_operator_auth.py` was not in my first set; re-run with it, all three were killed.
Baselines on unmutated main: ops-console operator tests 180 passed; field-core operator + registry + delegation + lifecycle p29 675 passed; kill-switch + field-core operator suites 238-300 passed.

## To flip to NO-BLOCKER
G22 merged (PR 374 plus the architect conditions and the `phase_g_check --stage 2` line) and G24 on main. Re-run on the new head; the code paths above need re-testing only if operator_auth.py, kill-switch api or registry PATCH change. G21 is not a Stage 2 item.
