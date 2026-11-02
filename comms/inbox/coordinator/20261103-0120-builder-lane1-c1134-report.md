# Lane 1 report: C-1134
Draft PR 448, branch scrub/deploy-status-lines-c1134, head c4990e63 (one commit on main 05942b98). First push; resets reviewer and verifier gates.
- 16 sites in 6 files scrubbed to what was built, no status, no deploy sha (counts and classes only here): STATE.md 5, CHANGELOG.md 2, v1.2 runbook 3 lines, agent-usage 1, next-session-phase-f 1, todo 5. Line counts unchanged.
- C-1111's STATE.md:122 is a false positive (it says status is not recorded); reworded neutral.
- Residual, not in the card: more "release vN" and "verified live" lines in STATE.md and a "live on both estates" line in next-session-phase-f; for the PR 342 guard (estate-state-phrase) or a ruling.
- Test merge with PR 441: conflict free.
- Tests (Windows): deploy_docs, runbook_pins_c465, operator_mounts_b6, gb10_caddy_tls, machine_verifier_identity, phase_g_check, environment_doc: 299 passed. Not run: full set; GX10 verifier on c4990e63.
- Open for Don: the second Windows-profile name (not in PR 441), still unruled.
