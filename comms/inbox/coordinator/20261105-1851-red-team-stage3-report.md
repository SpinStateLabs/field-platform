# RED TEAM: STAGE-3 report (REQUIRE on all eight, rollback, irreversibility). ssl-fp-red-team, 2026-11-05 18:51Z
Head tested: main 3804d0b9. Method: route matrix on all eight apps under ENFORCE (in-process), plus a real 3-process Stage-3 stack (ledger, registry, kill-switch all ENFORCE; identities `svc-registry`, `svc-killswitch`) with the same ~90-probe set as Stage 2.

## VERDICT: BLOCKERS (unmet prerequisites; no bypass found in the enforced routes)

| ID | Sev | Finding | Conf |
|----|-----|---------|------|
| B-RT-g21-unbuilt | BLOCKER (policy: G21 implemented before arming; runbook Stage 3 entry 2) | Row B-G21-stage3-identity is open; no code on main. A re-provision that changes owner or manifest_ref still needs `registry_edit` plus alias/list membership, which no job row holds (runbook OPEN ITEM ~1715-1730). Only the unchanged-renewal path (P29) works; test_provision_unchanged_p29 passes. | HIGH |
| B-RT-g22-not-landed | BLOCKER (Stage 2 prerequisite carries over) | See the Stage 2 report: PR 374 open draft. Stage 3 cannot follow an unarmed Stage 2. | HIGH |
| B-RT-g24-absent | BLOCKER (policy) | No stage controller or automatic rollback on main. | HIGH |

## Route matrix under ENFORCE (no creds / bad key / drill-only key), HIGH
Refused 401/403, never 2xx: registry POST /agents, POST attest, PATCH carrying status, manifest_ref, owner or domain; ledger /export /rotate /hold /hold/release /retention/apply; delegation /tokens and /tokens/{id}/revoke; governor PUT caps, rate-limits, policies and POST escalations resolve; federation PUT contracts; lifecycle /sweep; kill-switch /kill, /kill/domain, /revive, /drill. The console forwards only the human's headers, holds no identity of its own and answers 401 without them (180 console tests pass).
Real stack, ENFORCE everywhere: registry PATCH status with perimeter only 401; drill-only key 403; manifest_ref/owner/domain PATCH no creds 401; register no creds 401.
Kill path works under Stage 3 on main (HIGH): kill + revive by `don` 200/200; drill 200 with `restored:true`; the machine verifier drills a canary that names it (200) and is refused (403) on an agent that does not. The runbook's older 502/500 predictions do not reproduce.

## Writes still perimeter-only after Stage 3 (declared, C-54 objection 4; MEDIUM, HIGH)
registry PATCH of `name` only and POST /discover; ledger POST /events (reserved operator keys are stripped at every depth and `operator.*` rows stamped `self_reported`, verified live, but a perimeter holder can still append arbitrary unattributed rows); governor POST /spend and /usage; federation POST /crossing; delegation /introspect. REQUIRE does not authenticate these; only per-agent secrets do. Not probed for value abuse (negative spend amounts): not tested, LOW coverage.

## Operational risks (not bypasses)
- R-1 MEDIUM, HIGH: if the `svc-killswitch` row is revoked or its key unreadable under Stage 3, every kill and revive answers 502 and the agent stays active. Break-glass B-7 is the only path. Include it in the rollback rehearsal.
- R-2 MEDIUM, HIGH: a domain kill by an operator not named on every manifest returns 200 and halts only some agents (per-agent `error` rows). Never rely on one human id for a domain halt.
- R-3 LOW: a non-atomic rewrite of operators.json gave 503 on 46 of 60 kills. The runbook mandates `mv -f` and keygen writes atomically; keep it so.
- R-4 MEDIUM, MEDIUM: image rollback alone. REQUIRE lives in env/.env, read per call. An image that predates the flag ignores it and runs OFF (fail open, no alarm) while compose still says REQUIRE=1; an intermediate image that honours it but sends no daemon identity makes kills fail. Only `phase_g_check --expect-mode` notices; make it mandatory after every `up`.

## Reverse-order rollback (analysis, MEDIUM; not rehearsed on an estate)
Runbook order (remove the flag, recreate the seven first, kill-switch last) keeps the kill-switch ENFORCE until the registry is LOG-ONLY, which is the verified Stage 2 state (kills work). The opposite order is safe only while the kill-switch identity is present; with an unreadable key the still-ENFORCE registry refuses its PATCH and kills fail.

## Irreversibility of REQUIRE
The code path is reversible: removing the flag and restarting returns the service to LOG-ONLY/OFF; mode is never stored in data. Not undone by an image rollback: the env flag, the operators file and keys, retired-hash memory (process-local, resets on restart) and ledger rows already written. Hence "never roll back by image alone". (HIGH on code, MEDIUM on estate behaviour.)

## Mutants
The same 16 as Stage 2: 15 killed, 1 test gap (case-insensitive list match, M8); not a code defect.

## To flip to NO-BLOCKER
G21, G22 and G24 on main, a clean Stage 2 window recorded, rollback rehearsed (including R-1). Re-run on the new head.
