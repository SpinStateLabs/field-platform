# Continuation prompt — Phase G (authenticated operators), then E

Continue the FIELD platform v1.2 build with **Phase G**. FORCE protocol: no flattery, objections first, cite sources, show reasoning, tag confidence; verify before claiming.

Read first: `STATE.md` ("PHASE F GATE — CLOSED 2026-09-14"), `tasks/todo.md` (REVISION 2.1 rules, arming table, "Phase G — authenticated operators", reversibility row G), `docs/runbooks/v1.2-deploy-rollback.md` §2/§4/§5, `tasks/agent-usage.md`.

Where things stand (verify read-only first): `main` on `origin` and `gb10` at the commit that closed the F gate. GB10 runs 1eeb8b5 with A7–A11 + A7b (keyring + REQUIRE) armed; Fly runs release v9 (19701f4) with A7–A11 armed; self-agents provisioned on both (tokens expire 2026-10-14). Switches live in GB10 `integration/demo/.env` (never print it) and Fly secrets. Scripts: `D:\claude-session-scripts\` (gb10-*.sh, fly-arm-f.sh, fgate_checks.py) with copies in `~/field-backups/` on the GB10. Off-box public keys and fingerprints: `C:\Users\donal\.field-local\backups\`.

Phase G per the plan: Don generates his operator key on his own machine (the session never sees it; the registry stores its sha256); guarded writes require `x-field-operator` + `x-field-operator-key` on kill/revive/drill/attest/decommission/rotate/hold/mint; `authorized_operators` enforced; the ledger records the authenticated id; the session verifies the refusal paths live on the canary (no key 401, wrong key 403, mismatch 403) and Don performs the positive path (D16). Irreversible: "image rollback until operator keys are required" — ask before crossing.

Still needs Don: Anthropic credits (D1), D3, D5, D7, D12, D14, D15, D16, Netlify secret, ssl SKILL.md hook-2 re-upload, plugin 0.1.2 reinstall, vt token 035e4087 (expires 2026-09-19), self-agent token renewal before 2026-10-14, `FORCE_GATEWAY_SENTINEL_TIMEOUT=60` before A12.

Rules that bit this session: secrets never through the session; canary-only mutation; temp on D:; one reviewer per stream; put "run tests in the foreground" in every brief; `docker exec -i` for stdin; Windows-style local paths for `fly ssh sftp` and `attest.exe`; rebuild the admin-profile images on every GB10 deploy; force-recreate a service after placing a key it reads; allow the gateway's own `gateway.refused` events in the F-gate collateral list.
