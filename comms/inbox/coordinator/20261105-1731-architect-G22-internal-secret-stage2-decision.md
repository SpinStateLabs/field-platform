# DECISION G22: FIELD_INTERNAL_SECRET (C-54) as a Stage 2 prerequisite. Architect, 2026-11-05.

## Honoured record
`20261105-0800-groomer-don-rulings-2.md`, D-12 (Don's own answer): "build the internal-only secret (FIELD_INTERNAL_SECRET, C-54 plan) as a Phase G Stage 2 prerequisite; per-agent secrets later." (HIGH, read.) Plan: `20261030-1610-builder-lane13-c54.md`. Build in flight: draft PR 374 (C-801), open, unmerged, deployed nowhere (gh, 2026-11-05).

## Decision
Stage 2 (G25, REQUIRE on the kill-switch) does not start until ALL of these exist; the Stage 2 go sentence cites each:
1. PR 374 merged: hash-verified `x-field-internal` on exactly the two internal operator routes (`verify_hash`, `rotation_state_route`); services hold `FIELD_INTERNAL_SECRET_SHA256` only; absent, empty or hash-as-secret all answer 404. C-983 conditions closed first: F-C849-5 (refuse an internal secret equal to `FIELD_READ_KEY`; whichever of PR 369/374 merges second adds it), header name pinned by value, secret length bound, runbook line that a bad value stops the service at start.
2. Mode policy per the C-54 plan: ENFORCE with the hash unset => both routes 404 (fail closed); OFF/LOG-ONLY unset => once-per-process WARNING. Recorded: ENFORCE-disables is accepted (without the rotator nobody calls the routes).
3. Holder = the rotator ONLY, by file mount in the rotator container; never an env var, never the shared `*env` anchor, never canary-agent (C-71, D-12). The sender is PR 57's rework (C-496). If PR 57 is not merged at Stage 2 the routes stay disabled by rule 2; acceptable.
4. Deny counter `operator_internal_route_denied` in `/health`, and the observer event `operator.internal_route_denied_changed` if the frozen event set permits; if it does not, the counter ships alone and the event is a recorded follow-up (LOW: not verified).
5. Estate record (Don/coordinator, not code): secret file created on each estate (GB10 and Fly separately), its sha256 set in each service env, nothing printed; the deploy record states present/absent with no fingerprint.
6. v1 is a static secret; rotation is a later slice by the same rotator. Per-agent secrets (C-48 mitigation 1) are a scheduled card after Stage 3, not a Stage 2 gate.

## Rationale
Don ruled it a Stage 2 prerequisite (D-12). Hash verification means a compromised service holds only a hash (answers C-71). It closes reconnaissance of the rotation schedule; it does NOT close the LOG-ONLY write exposure (C-54 objection 4), which only per-agent secrets close. The runbook states that limit.

## Alternatives rejected
Value-compare secret in the shared env anchor (every container holds it: C-71); defer past Stage 2 (contradicts D-12); wait for per-agent secrets (larger build, Don said later); default-open when unset (a silent decoration, C-54 objection 3).

## Risk
PR 374 is dormant by design: merging proves nothing live. A deployed hash with no rotator sender breaks nothing. A wrong hash at install stops the service at start; `phase_g_check` catches it before arming. Two secrets in the env anchor re-creates the C-71 failure; a test greps compose for it.

## Exact done-when
(a) PR 374 merged with the F-C849-5, pin and length conditions closed and mutants killed: skip the check; compare to the hash directly; empty header; hash used as secret; secret equal to perimeter secret; secret equal to read key.
(b) New test `packages/field-core/tests/test_internal_secret_stage2_gate_g22.py`: ENFORCE + hash unset => both routes 404; hash set + correct header => 200; wrong, empty or hash header => 404; a repo grep over `docker-compose*.yml` and `fly*.toml` finds plain `FIELD_INTERNAL_SECRET` in no service env and only the `_SHA256` name; `phase_g_check` gains a `--stage 2` precondition line "internal secret hash present on kill-switch and registry /health" (read-only, ids and counts only).
(c) Runbook Stage 2 checklist (:1471) gains items 1-6 as entry gates.
(d) Not code, recorded by the coordinator at the go point: the secret file exists on the estate. A builder cannot close (d).
