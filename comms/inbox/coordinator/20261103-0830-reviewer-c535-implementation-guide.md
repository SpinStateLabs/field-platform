# C-535 (Lane 9, cloud-reviewer, read-only, no GX10): docs/IMPLEMENTATION.md against main b929f12 (247 lines, sections 1-9)

VERDICT: of 28 statements checked, 17 TRUE, 8 STALE, 3 UNVERIFIABLE. Sections 3 to 8 (environment table, new-agent workflow, security switches, scheduled operations) are accurate: every CLI command and option named exists in source and every variable in section 3 is also in docs/ENVIRONMENT.md. Sections 2, 5 and 9 predate the repository's current state (14 services, public GitHub repo, CI matrix, 8,308 collected tests). No secret read or printed.

OBJECTIONS FIRST: (1) a "what is left to do (as of 2026-08-08)" section is dated by its own heading, so its staleness is expected, but nothing says "historical": a reader takes it as current. (2) I verified commands and options by presence in source (`grep` of command names and `--flags`), not by running them (no GX10, no installed workspace). (3) Default values I did not re-derive are marked. (4) The 2026-08-08 and GB10 verification statements describe a past estate run; not checkable from the repository.

ASSUMPTIONS: main b929f12; 14 service directories; CI at .github/workflows/ci.yml.

TRUE
1. Section 1: Python 3.11 or newer; CI runs 3.11, 3.12, 3.13, 3.14: ci.yml:20-21. HIGH.
2. Section 3: every `FIELD_*`, `FORCE_*`, `ANTHROPIC_*` variable the table names also appears in docs/ENVIRONMENT.md (32 in this file, 92 in that one, none only here). HIGH (script). The table is a subset: 60 variables in ENVIRONMENT.md are not in this guide (the ntfy and posture flags among them); the guide does not say it is partial. See row 21.
3. Section 3 defaults checked against source: `FIELD_ORG_NAME` default "Spin State Labs" (federation_broker engine.py:52), `FIELD_LEDGER_RETENTION_DAYS` compose and Fly 2555 (docker-compose.yml:134, fly.toml:43), `FORCE_TELEMETRY_RETAIN` 10000 (force-gateway store.py `DEFAULT_RETAIN`), `FIELD_LIFECYCLE_EVERY` read by the lifecycle CLI and API (cli.py:450, api.py:68). HIGH. `FORCE_TELEMETRY_WINDOW` default 50: api.py:241-246 falls back to `DEFAULT_TELEMETRY_WINDOW`; the constant's value not read (MEDIUM).
4. Section 3 ports 8001-8013 per service: matches integration/demo/docker-compose.yml:103-118 (C-534 row 1). HIGH.
5. Section 6 commands exist: `field templates --show/--out`, `field validate`, `registry add --manifest-ref`, `governor set-cap --from-manifest`, `delegation mint --granted-by --scope --ttl`: all command names and `--from-manifest`, `--granted-by`, `--manifest-ref` found in source. HIGH (presence).
6. Section 6: the registry refuses an unresolvable `manifest_ref` (POST /agents 422, `registry add` exit 2): consistent with agent-registry README and tests; MEDIUM-HIGH (not re-run).
7. Section 6: `@governed`/`FieldAgent`, `agent.report_spend(cents=)`, `report_usage_from`, `ensure_alive`, `ActionBlocked`, `ActionEscalated`, `AgentKilled`: names checked in packages/field-agent previously (C-17 read); not re-grepped here. MEDIUM.
8. Section 7: `FIELD_SHARED_SECRET` gives `x-field-auth` on all endpoints except `/health`: authn.py:3-19. HIGH.
9. Section 7: federation: `fedbroker keygen`, `add-contract --pubkey`, `sign`, `crossing --direction`, `--signature` exist; a keyless contract refuses every inbound crossing (C-175): confirmed by the C-355 and C-401 PASS reports and the engine. HIGH.
10. Section 8: `lifecycle sweep --roster --markdown`, `--auto-kill-orphans`, `attest render --out --period --signer --sign-key`, `attest verify --pubkey`, `ledger retention check|apply`, `ledger rotate --operator --anchors`, `ledger hold place|release`, `crosswalk run`, `crosswalk serve --every`, `killswitch drill --operator`, `replay run --since --until`: every command name and option found. HIGH (presence; behaviours not run).
11. Section 8: `ledger rotate` needs `FIELD_LEDGER_ANCHOR_KEY`, else 503 and never an unsigned rotation: ledger README and C-13..R-13 reports; MEDIUM-HIGH.
12. Section 9 item 4: ISO/IEC 42001 not yet purchased and ingested; citations blocked by the guard test: crosswalk matrix shows 13 `pending-purchase` citations (C-530 row 11). HIGH.
13. Section 9 item 3: the EU AI Act citations cross-check against EUR-Lex: not re-checked; C-530 notes 23 `pending-text` citations. MEDIUM.
14. Section 3: `FORCE_GATEWAY_MOCK` exactly `1` = mock; other values = real upstream: force-gateway api.py (the `_posture_flag` docstring says it stays exact-match "1" only). HIGH.
15. Section 4: `bash integration/demo/run_demo.sh` exists; "boots seven services": not run. Existence only. MEDIUM.
16. Section 5: the proxy-root smoke `curl -sf localhost:8080/<p>/health`: the Caddyfile routes /registry /ledger ... /crosswalk (integration/demo/Caddyfile:42-76) and the demo compose publishes only :8080 (docker-compose.yml:178). HIGH.
17. Section 3 boot order and the CLI list (`registry ledger delegation governor killswitch sentinel replay crosswalk forcegw fedbroker lifecycle attest field`): each entry point exists; the console is listed in the boot order but has no CLI in that list (`console` is started separately). MEDIUM.
STALE
18. Section 2: the install loop installs twelve services and `field-agent` but not `ops-console` or `claude-approver` (14 service directories exist; C-534 F-C534-1). The second test loop includes ops-console; claude-approver has no test line anywhere in this guide. HIGH.
19. Section 2: "expected: 209 passing as of the field-agent gate": the repository collects 8,308 tests on main b929f12 (C-499 recomputed that figure); 209 is an August milestone. HIGH.
20. Section 5: "Verified 2026-08-08 ... all nine services healthy" and "x86_64 compose run still pending (CI candidate)": CI `compose-smoke` runs on ubuntu-latest (x86_64) in ci.yml:91-93 and later; fourteen services; section 5 should be marked historical. HIGH.
21. Section 5: "GB10 staging copy: `/home/<name>/field-platform-verify/`": an estate path with a real account name in a public file (C-540 F-C540-2 class; line 136). HIGH.
22. Section 8, last line: a Windows user path to the venv (`C:\Users\<name>\.venvs\...`, line 222): same class, F-C540-2. HIGH.
23. Section 9 item 2: "Push the repo to a remote (currently local-only git)": the repository is public on GitHub with 246 branches. HIGH.
24. Section 9 item 5: "CI: GitHub Actions matrix (py 3.11-3.14) + an x86_64 compose run": both exist (ci.yml:20-21, :91). HIGH.
25. Section 9 item 7: "registry writes as ledger events" (built: `registry.registered` etc., agent-registry api.py:235), "`attested_at` field" (built: lifecycle-manager engine.py and agent-registry cli.py read it), "telemetry persistence" (built: force-gateway store.py, SQLite): three of the eight listed gaps are closed. "Force-gateway streaming": no streaming code found in force-gateway api.py (still a gap, MEDIUM). "Outbound federation gating": unclear (the ADR note says outbound is valid for a keyless contract; the item is not re-read). HIGH for the first three.
26. Section 9 item 6: "per-caller identity beyond the shared secret": built (operator auth and signed caller events, F2b); "signing-key rotation/revocation": R1-R3 merged, the rotator (PR 57) is being reworked (C-496): partly built. TLS via a fronting proxy: Caddy is in the compose and Fly files (built). HIGH for the first, MEDIUM for the second.
UNVERIFIABLE FROM THE REPOSITORY
27. "~23 s: boots seven services": a demo timing; "each `<service>/demo.sh` (<60 s each)": not timed.
28. Platform wheel claim "all wheel-installable on x86_64 and aarch64": a packaging fact not re-checked; CI installs on x86_64.

FINDINGS (for cards)
- F-C535-1 MEDIUM-LOW (doc): rows 18-19: add ops-console and claude-approver to the install and test loops; drop "209 passing" or replace with a sentence that does not carry a count (or the CI command).
- F-C535-2 MEDIUM-LOW (doc): rows 20 and 23-26: mark section 5 verification and the whole of section 9 "historical (2026-08-08)" and replace section 9 with a pointer to STATE.md and the task queue, or rewrite it from today's gaps.
- F-C535-3 LOW (public-safety, C-560 family): rows 21-22: replace the two path lines with placeholders.
- F-C535-4 LOW (doc): row 2: say the section 3 table is a subset and point to docs/ENVIRONMENT.md as the full reference.
Same family as C-545, C-549, C-550, C-559: docs that describe a past state without a date caveat.

CONCLUSION: the operational core of the guide (sections 3 to 8) is accurate against source (HIGH, presence-checked; not run). Sections 2, 5 and 9 are stale in ways a new reader will notice at once (a test count 40 times too small, a missing remote, CI "to do") and two lines carry personal paths (HIGH). I do not know the demo timings or the wheel claim.
