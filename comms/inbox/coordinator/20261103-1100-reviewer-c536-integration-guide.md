# C-536 (Lane 9, cloud-reviewer, read-only, no GX10): docs/INTEGRATION.md against packages/field-agent and the services, main b929f12 (268 lines)

VERDICT: the guide is accurate about the SDK and the operator steps. Of 24 statements checked: 18 TRUE, 4 PARTLY TRUE or STALE, 2 UNVERIFIABLE. Every class, method, exception, CLI command and option the guide names exists; the exception hierarchy, fail-closed behaviour and clause names match the code. Defects: a deploy-status sentence in a public file (a rule violation), the gateway example omits what enforce mode requires, a demo timing that disagrees with the implementation guide. No secret read or printed.

OBJECTIONS FIRST: (1) I checked names, signatures and documented behaviour by reading source; I did not run the SDK, the demo or the examples (no GX10, no installed workspace). (2) "Fail closed" statements describe code paths; whether the estates behave that way is not checkable here. (3) The guide documents defaults for services I did not each re-read (rows 3-4).

ASSUMPTIONS: main b929f12; SDK = packages/field-agent/src/field_agent (agent.py, errors.py, bootstrap.py, cli.py, liveness.py, usage.py, federation.py, _transport.py).

TRUE
1. Section 1: the SDK adds no server power; its local capability is refusal: agent.py raises ActionBlocked, AgentKilled, UsageReportError; decisions come from the sentinel, governor and kill-switch clients. HIGH.
2. Section 1: the cooperative-perimeter limit is stated plainly and the Enforced-vs-Declared table exists in packages/field-agent/README.md. HIGH.
3. Section 2: the environment variables (`FIELD_SENTINEL_URL` 8004, `FIELD_GOVERNOR_URL` 8006, `FIELD_KILLSWITCH_URL` 8005, `FIELD_FEDERATION_URL` 8010, registry 8001 and delegation 8003 for bootstrap) match the compose URLs (integration/demo/docker-compose.yml:103-118) and the clients. HIGH.
4. Section 2: `FIELD_SHARED_SECRET` is read per request so a secret exported later is honoured: `_transport.py:3` ("`auth_headers()` is read at CALL time"), `:11`, `:24`. HIGH.
5. Section 2 and 4: `FieldAgent(agent_id, token_id=..., heartbeat_max_age=...)`, `governed`, `check`, `ensure_alive`, `heartbeat`, `checkin`, `report_usage`, `report_usage_from`, `report_spend`, `cross`: agent.py:28-215. HIGH. A zero-argument callable for `token_id` is accepted (documented in section 3; the constructor signature was read, the callable path not run). MEDIUM-HIGH.
6. Section 3: operator CLIs: `field validate`, `governor set-cap --from-manifest`, `governor set-policy --allowed-model --token-rate-limit`, `fieldagent mint --granted-by --scope --ttl-seconds`: field-agent cli.py:130-137 (mint, `--ttl-seconds` default 3600), spend-governor cli (`set-policy` with those options). HIGH.
7. Section 3: `field_agent.bootstrap.register(...)` and `.mint(...)` exist and `bootstrap` is not re-exported from the package root: bootstrap.py; `__init__` exports. MEDIUM-HIGH (bootstrap signature read in an earlier audit, C-17).
8. Section 3.1: DOA roster refusals: 503 when the roster cannot be read, 403 `D.grantor`, 422 `D.scope`, 422 `D.manifest_expired` (PROVISIONAL): delegation_authority/api.py:15-26; `D.grantor` defined in field_core conformance.py:42. HIGH.
9. Section 3.1: `max_spend_usd` stamped on each token and enforced by the sentinel as `E.spend_cap` (v1.2 D1e): sentinel engine `_token_ceiling` (engine.py:415-464). HIGH.
10. Section 3.1: roster under `/data`, never `/data/manifests` (read-only volume on the GB10): a deployment instruction; consistent with the ENVIRONMENT.md and runbook text. MEDIUM.
11. Section 4: BLOCK raises `ActionBlocked` with `.verdict`; sentinel unreachable is `ActionBlocked` with clause `E.kill_switch` "failing closed": conformance_sentinel/governed.py:98-99. HIGH.
12. Section 4: a log_only sentinel answers ALLOW and shadow-ledgers the true outcome; `FIELD_SENTINEL_MODE=enforce` to see real BLOCKs: mode.py:3-8. HIGH. (An unrecognised value now refuses to start, C-169; the guide does not say so: row 19.)
13. Section 4: every ALLOW is metered to the governor in either mode and an agent with no cap is not metered: engine `_meter` (engine.py:378-413). HIGH.
14. Section 5: `report_usage` prices tokens from a dated price book in exact integer units (1e-7 USD) and returns `rogue_model`, `rogue_burst`, `unpriced`: spend-governor usage.py:8-9 and the price book. HIGH (names), MEDIUM (the 1e-7 unit not re-derived).
15. Section 5, strict reporting: failed report raises `UsageReportError`, a 404 raises `NoSpendCapError`: errors.py:30-37 (`NoSpendCapError` subclasses `UsageReportError`). HIGH.
16. Section 6: `ensure_alive` raises `AgentKilled`; `heartbeat()` observer form; `checkin()` is the POST that writes `last_seen`; `HeartbeatUnreachable` subclasses `AgentKilled`: agent.py:192-215, errors.py:18-26. HIGH.
17. Section 6: no background thread in the SDK: the only threading import in packages/field-agent/src is canary.py (the canary agent's own server, not the SDK hook). HIGH.
18. Section 7: the failure table matches the exception classes (`BootstrapError` errors.py:38). HIGH. Section 8: the examples (`01_actions.py` to `05_rest_api.sh`, `agent_template.py`, `run_all.sh`), `packages/field-agent/demo.sh`, `integration/demo/agent/invoicing_agent.py` and `docs/capstone-evidence/field-agent-run.log` all exist; the 5th draft at 96% story is in invoicing_agent.py:30-31. HIGH. `field-rest.ps1` and `Get-FieldHeartbeat` exist (tools/field-rest.ps1:143). HIGH.
PARTLY TRUE OR STALE
19. Section 4 states the sentinel mode default `log_only`; since C-169 an unrecognised `FIELD_SENTINEL_MODE` value refuses to start instead of reading as log-only: add one sentence (the guide's troubleshooting says "look for conformance.shadow_block events" only). LOW-MEDIUM. MEDIUM-HIGH confidence (read mode.py:35-47).
20. Section 5: the gateway example `POST {GATEWAY}/v1/messages` with only `x-field-agent-id` and `x-force-preset`: true for observer mode. With `FORCE_GATEWAY_ENFORCE` on (v1.2 F1) the gateway answers 401 without `x-field-token` as well and 403 or 503 on the sentinel's verdict (force-gateway api.py:25-47, :553-586); the guide never says so. Also the table's "gateway meters `except: pass`" is the gateway's best-effort metering (api.py ~503-530, "metering is best-effort here"), which is accurate in spirit. MEDIUM.
21. Section 3.1 (lines 131-132): "Both estates run pre-v1.2 images with the variable unset, so this is Declared there until Don deploys.": a statement of the estates' deployed state in a public document (the Lane rules forbid deploy status). Lines 182 ("placing it on the estates is Don's step") and 208 ("a pre-v1.2 estate") are milder instances. HIGH that it is deploy-status wording; I cannot say whether it is still true. Class only; no value. MEDIUM severity (public-safety rule).
22. Section 8: "`run_demo.sh` (~30s)" while docs/IMPLEMENTATION.md section 4 says "~23 s": the two guides disagree; neither is measured here. LOW.
UNVERIFIABLE FROM THE REPOSITORY
23. Demo timings (row 22) and "a committed real run" content: the log exists; I did not re-read it against the SDK.
24. Section 5 table "trust" and "coverage" columns: design statements, not checkable.

FINDINGS (for cards)
- F-C536-1 MEDIUM (public-safety, doc): row 21: remove the estate deploy-state sentences (INTEGRATION.md:131-132 and soften :182, :208) or restate them as design facts ("with the variable unset, a mint behaves as before"); same class as C-514 and F-L10-308-1.
- F-C536-2 MEDIUM-LOW (doc): row 20: add the enforce-mode headers (`x-field-agent-id` plus `x-field-token`, and `x-field-action`) and the 401/403/503 answers to the gateway example, with a pointer to the gateway README.
- F-C536-3 LOW (doc): row 19: one sentence that an unrecognised `FIELD_SENTINEL_MODE` refuses to start (C-169).
- F-C536-4 LOW (doc): row 22: reconcile the demo timing with IMPLEMENTATION.md or drop it.

CONCLUSION: INTEGRATION.md matches the SDK and operator code on every name, exception, command and clause I checked (HIGH). Its defects are three small doc gaps and one deploy-status sentence that a public file should not carry (HIGH). I do not know whether the estates still run the older images the sentence names.
