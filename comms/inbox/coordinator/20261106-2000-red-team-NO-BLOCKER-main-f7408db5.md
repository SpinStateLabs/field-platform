# RED TEAM: NO-BLOCKER, Stage 2 and Stage 3 (code), on main f7408db5. ssl-fp-red-team, 2026-11-06

## STAGE 2 VERDICT: NO-BLOCKER (HIGH on code; MEDIUM on the estate: nothing rehearsed on a real estate here)
Main f7408db5 contains G21 (9a2417c0), G22 (9944ee35, d5dd8238), G23 (fd0ac135), G24 (ede21674, b1b229f1, 75085ae3, b77408cb), the authn bytes fix (3cb0d881) and the ledger event-type hardening (9e1346e7).
Evidence on f7408db5:
- G22 source (`operator_health.py`, `phase_g_check.py`) has 0 diff lines against the f129b1e9 I attacked; 20-variant G22 attack set: same results (404 on absent, empty, wrong, perimeter-as-internal, hash-as-secret, non-ASCII, both-set mismatch; 200 only on the correct secret; bad setup stops the service at start).
- Real 3-process Stage 2 stack, 83 probes: 4 non-pass, all already known and explained: S9 and E4 are harness artifacts (S9: no second request authenticated, status stays active; E4: an authenticated caller's own text echoed in its own 200, by design), X1 and X2 are N-1 (registry LOG-ONLY at Stage 2, declared). Real Stage 3 stack, 90 probes: only S9 and E4. Kill, revive, drill under ENFORCE; every refusal leaves the agent active; no key, hash or secret in /health or the kill-switch log; ledger down: unauth 401 in 0.01 s, authed kill 200; registry down: kill 502 (fail closed).
- N-2 closed: non-ASCII `x-field-auth` gives 401, not 500. Ledger look-alike `operator.` event types (zero-width, U+2024, soft hyphen, trailing newline, upper case, spaces, colon) are 422; `operator.refused` and `agent.action` still 201.
- 441 tests passed together: G22 gate, c801, operator_health, rotation_r2, operator_auth, authn, stage controller, kill-switch operator suite, sealed-ledger operator health.
- Mutation result of 20261105-1850 unchanged (15 of 16 killed; the survivor M8 is a test gap, not a defect). `operator_auth.py` changed since (prefix normalisation only), not re-mutated: LOW coverage.

Go-sentence conditions (procedure, not code):
1. `phase_g_check --stage 2` prints `internal secret hash present ... (2 of 2)` on the real estate before arming.
2. The driver passes `--build-sha` and the stage's service list to the controller (R1, R2: the controller does not enforce either by default; card B-RT-832-binding-defaults stays open, non-blocking).
3. The go sentence says the registry stays LOG-ONLY at Stage 2 (N-1: PATCH of status or manifest_ref needs only the perimeter secret) and that lifecycle auto-kill, the X3 check and keyless tools answer 401 (N-6).
4. Rollback rehearsed, including R-1 (revoked or unreadable `svc-killswitch` key: every kill and revive answers 502, B-7 break-glass is the only path).

## STAGE 3 VERDICT: NO-BLOCKER for the code (MEDIUM)
Every Stage 3 prerequisite I held (G21, G22, G24; G23 and the Stage 2 alerts) is on main and verified. Arm only when:
1. Stage 2 has run a clean window that a person has judged (the controller checks only a recorded `stage_done`, no duration) and the go sentence is Don's.
2. Rollback is rehearsed in reverse order (remove REQUIRE first, the seven, kill-switch last, `--expect-mode log-only`) and `phase_g_check --expect-mode` runs after every `up` (R-4: an image that predates the flag runs OFF silently).
3. Five manifests still lack `don-admin` (canary-fly, canary-gb10, compliance-crosswalk, conformance-sentinel, force-gateway): a don-admin edit of those agents is refused until added; do not rely on it in rehearsal.
Standing, declared: after Stage 3 `/spend`, `/usage`, `/crossing`, `/introspect`, `/discover`, registry PATCH of name only and ledger `/events` stay perimeter-secret only (C-54 objection 4); negative-spend abuse not tested (LOW coverage). R-2 (a domain kill by one operator not on every manifest halts only some agents) stands.
REQUIRE is reversible in code and not by image rollback alone: the controller now prints this at `plan` for Stage 3.
