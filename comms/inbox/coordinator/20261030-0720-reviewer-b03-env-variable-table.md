# B-03: every environment variable the services read (grep/AST, report only)

Main 1bae4fa. Scope: Python under `packages/*/src` and `services/*/src` (16 components). Method: an AST pass over every `os.environ.get`, `os.environ[...]`, `os.getenv`, and `env.get`/`env[...]` on a name bound from `os.environ`, resolving module-level string constants (for example `ENV_TOPIC = "FIELD_NTFY_TOPIC"`) and following the small helper functions that wrap `os.environ.get` (`_env`, `_env_float`, `_env_id`, `_float_env`, `service_url`, ...). A cross-check of every `"FIELD_*" "FORCE_*" "CLAUDE_*" "ANTHROPIC_*" "CROSSWALK_*"` string literal in src found 92 names; 84 were captured by the AST pass and the other 8 I added by hand (ops-console `env=` helper arguments, a typer `envvar=`, and the four `FIELD_NTFY_*` constants read through `alerts.py:329-332`). Total 92 variables. HIGH for the list; MEDIUM that none is missed (a read through a computed name, such as a prefix loop, would not appear: I saw no such loop in `grep "os.environ"`).

"Documented" below means the exact name appears in some `.md` file outside `tasks/` and `comms/`; it does not mean the meaning, default and accepted values are explained (see findings). "Default" is the literal second argument where it is a constant: `''` is an empty-string default, `(none)` a one-argument read, `(via helper)` a default set inside a helper, `<expr>` a non-constant default, `(required: KeyError)` a bare index. Variables read in several places show the first read (alphabetical by file); "reads" is the number of read sites found.

## Findings
1. Six variables appear in no `.md` file (UNDOCUMENTED): `CROSSWALK_SUGGEST_MODEL` (suggestions.py:165; present in `.env.example`), `FIELD_CANARY_AGENT_ID`, `FIELD_CANARY_HOST`, `FIELD_CANARY_PORT`, `FIELD_CANARY_WORK_EVERY` (all canary.py:479-482, not in any compose, script or yml either), `FORCE_HYGIENE_BASELINE_WINDOWS` (api.py:772; present in `.env.example`). HIGH.
2. Documented only in a changelog or a spec, not in an operator-facing README or runbook: `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM` (CHANGELOG.md only; read in field-core llm.py:181 and force-gateway; it is a security setting), `FIELD_LEDGER_CRASH_AT` (sealed-ledger SPEC.md only; a crash-injection hook in store.py:520, read in production code). HIGH.
3. Security-relevant switches with an empty-string default or no default that fail open when unset (read-only observation from the table; each is covered by the C-241 required-posture overlay or not): `FIELD_SHARED_SECRET`, `FIELD_OPERATOR_REQUIRE`, `FIELD_LEDGER_REQUIRE_SIGNING`, `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE`, `FORCE_GATEWAY_ENFORCE`, `FIELD_DOA_ROSTER` (the six in PR 129); not in PR 129: `FIELD_KILL_ENDPOINT_ALLOWLIST`, `FIELD_LEDGER_CALLER_KEYRING`, `FORCE_GATEWAY_TOOL_CHECK`, `FIELD_SENTINEL_MODE`, `FIELD_SENTINEL_JUDGE` (see my C-274 report, F-C274-1). HIGH for the list.
4. The table does not say which variables are read by which process when several components read the same name; the component column lists them. `FIELD_DATA_DIR` is read by 10 components, `FIELD_LEDGER_URL` by 9. HIGH.
5. Truthy parsing differs by variable (for example `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE` arms only on 1/true/yes/on, `sealed_ledger/api.py:167`, while `FORCE_GATEWAY_TOOL_CHECK` is "exactly 1", `force_gateway/api.py:289`). A real README table should carry the accepted values per variable; this grep table cannot supply them. HIGH for the two examples, unknown for the rest.

## Proposed card (not queued)
D3: add `docs/ENVIRONMENT.md` generated from this table with columns variable, component, default, accepted values, security impact, and a CI test that fails when a variable read in src is missing from it (the AST pass above is about 80 lines; I can hand it over). Done when the six UNDOCUMENTED names are in the file and a mutant (add an `os.environ.get("FIELD_X")` to any service) goes red.

## Table (92 variables)
|variable|component|first read (file:line)|default|reads|documented in|
|---|---|---|---|---|---|
|`ANTHROPIC_API_KEY`|compliance-crosswalk,conformance-sentinel,force-gateway|compliance-crosswalk/src/compliance_crosswalk/suggestions.py:168|(none)|4|integration/fly/README.md, docs/INTEGRATION.md (+8)|
|`ANTHROPIC_BASE_URL`|field-core,force-gateway|field-core/src/field_core/llm.py:91|'https://api.anthropic.com',(via helper)|2|packages/field-core/README.md, docs/IMPLEMENTATION.md (+3)|
|`CLAUDE_APPROVER_AGENT_MAP`|claude-approver|claude-approver/src/claude_approver/config.py:232|''|1|services/claude-approver/README.md|
|`CLAUDE_APPROVER_AGENT_MAP_FILE`|claude-approver|claude-approver/src/claude_approver/config.py:231|''|1|services/claude-approver/README.md|
|`CLAUDE_APPROVER_API_KEY_FILE`|claude-approver|claude-approver/src/claude_approver/config.py:62|''|1|services/claude-approver/README.md|
|`CLAUDE_APPROVER_ENVIRONMENT_ID`|claude-approver|claude-approver/src/claude_approver/config.py:58|''|1|services/claude-approver/README.md|
|`CLAUDE_APPROVER_HALT_WAIT_SECONDS`|claude-approver|claude-approver/src/claude_approver/config.py:54|(via helper)|1|services/claude-approver/README.md|
|`CLAUDE_APPROVER_POLL_SECONDS`|claude-approver|claude-approver/src/claude_approver/config.py:50|(via helper)|1|services/claude-approver/README.md, services/claude-approver/SPEC.md|
|`CLAUDE_APPROVER_TOOL_MAP`|claude-approver|claude-approver/src/claude_approver/config.py:257|''|1|services/claude-approver/README.md|
|`CROSSWALK_SUGGEST`|compliance-crosswalk|compliance-crosswalk/src/compliance_crosswalk/suggestions.py:212|''|1|services/compliance-crosswalk/README.md (+1)|
|`CROSSWALK_SUGGEST_FLOOR`|compliance-crosswalk|compliance-crosswalk/src/compliance_crosswalk/suggestions.py:221|''|1|services/compliance-crosswalk/README.md|
|`CROSSWALK_SUGGEST_MODEL`|compliance-crosswalk|compliance-crosswalk/src/compliance_crosswalk/suggestions.py:165|<expr>|1|**NONE**|
|`FIELD_ATTEST_SIGNER`|attestation-reporter|attestation-reporter/src/attestation_reporter/signing.py:159|(none)|1|docs/runbooks/v1.2-deploy-rollback.md, services/attestation-reporter/README.md (+1)|
|`FIELD_ATTEST_SIGN_KEY`|attestation-reporter,sealed-ledger|attestation-reporter/src/attestation_reporter/signing.py:160|(none)|2|docs/runbooks/v1.2-deploy-rollback.md, services/attestation-reporter/README.md (+1)|
|`FIELD_ATTEST_URL`|ops-console|ops-console/src/ops_console/api.py:358|'http://127.0.0.1:8013'|1|docs/IMPLEMENTATION.md, services/attestation-reporter/README.md|
|`FIELD_BUILD_SHA`|field-core|field-core/src/field_core/authn.py:26|'',(none)|2|integration/demo/README.md, integration/fly/README.md (+5)|
|`FIELD_CANARY_AGENT_ID`|field-agent|field-agent/src/field_agent/canary.py:479|'canary-gb10'|1|**NONE**|
|`FIELD_CANARY_HEARTBEAT_EVERY`|field-agent|field-agent/src/field_agent/canary.py:483|0.0|1|packages/field-agent/SPEC.md, docs/IMPLEMENTATION.md (+1)|
|`FIELD_CANARY_HOST`|field-agent|field-agent/src/field_agent/canary.py:480|'0.0.0.0'|1|**NONE**|
|`FIELD_CANARY_PORT`|field-agent|field-agent/src/field_agent/canary.py:481|<expr>|1|**NONE**|
|`FIELD_CANARY_WORK_EVERY`|field-agent|field-agent/src/field_agent/canary.py:482|5.0|1|**NONE**|
|`FIELD_CONSOLE_MAX_STREAMS`|ops-console|ops-console/src/ops_console/api.py:364|'8'|1|services/ops-console/README.md|
|`FIELD_CROSSWALK_EVERY`|compliance-crosswalk|compliance-crosswalk/src/compliance_crosswalk/cli.py:348|typer envvar|1|docs/IMPLEMENTATION.md, docs/runbooks/v1.2-deploy-rollback.md (+3)|
|`FIELD_CROSSWALK_URL`|ops-console|ops-console/src/ops_console/api.py:350|'http://127.0.0.1:8008'|1|docs/IMPLEMENTATION.md, services/compliance-crosswalk/README.md (+1)|
|`FIELD_DATA_DIR`|agent-registry,claude-approver,compliance-crosswalk,delegation-authority,federation-broker,force-gateway,kill-switch,lifecycle-manager,sealed-ledger,spend-governor|agent-registry/src/agent_registry/api.py:121|'','.','./var'|12|integration/fly/README.md, docs/ARCHITECTURE.md (+12)|
|`FIELD_DELEGATION_URL`|compliance-crosswalk,conformance-sentinel,delegation-authority,field-agent,incident-replay,lifecycle-manager|field-agent/src/field_agent/bootstrap.py:75|'http://127.0.0.1:8003'|7|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+2)|
|`FIELD_DOA_ROSTER`|delegation-authority,lifecycle-manager|delegation-authority/src/delegation_authority/cli.py:373|'',(none)|3|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+6)|
|`FIELD_EXPORT_ROOT`|sealed-ledger|sealed-ledger/src/sealed_ledger/api.py:462|''|1|docs/runbooks/v1.2-deploy-rollback.md, services/kill-switch/README.md (+1)|
|`FIELD_FEDERATION_URL`|federation-broker,field-agent|field-agent/src/field_agent/federation.py:59|'http://127.0.0.1:8010',<expr>|2|packages/field-agent/README.md, packages/field-agent/SPEC.md (+4)|
|`FIELD_GATEWAY_URL`|force-gateway|force-gateway/src/force_gateway/cli.py:24|'http://127.0.0.1:8009'|1|packages/field-core/README.md, docs/IMPLEMENTATION.md (+2)|
|`FIELD_GOVERNOR_URL`|claude-approver,compliance-crosswalk,conformance-sentinel,field-agent,force-gateway,spend-governor|field-agent/src/field_agent/usage.py:73|'http://127.0.0.1:8006',(none),(required: KeyError)|8|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+4)|
|`FIELD_JUDGE_CONFIDENCE_FLOOR`|conformance-sentinel|conformance-sentinel/src/conformance_sentinel/judge.py:201|''|1|services/conformance-sentinel/README.md (+1)|
|`FIELD_JUDGE_MODEL`|conformance-sentinel|conformance-sentinel/src/conformance_sentinel/judge.py:133|<expr>|1|services/conformance-sentinel/README.md|
|`FIELD_KILLSWITCH_URL`|claude-approver,field-agent,kill-switch,lifecycle-manager|field-agent/src/field_agent/canary.py:497|'http://127.0.0.1:8005',(required: KeyError)|5|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+3)|
|`FIELD_KILL_ENDPOINT_ALLOWLIST`|kill-switch|kill-switch/src/kill_switch/api.py:269|''|1|packages/field-agent/README.md, packages/field-agent/SPEC.md (+6)|
|`FIELD_LEDGER_ANCHOR_KEY`|sealed-ledger|sealed-ledger/src/sealed_ledger/api.py:202|(none)|1|integration/fly/README.md, docs/IMPLEMENTATION.md (+4)|
|`FIELD_LEDGER_ARCHIVE_DIR`|sealed-ledger|sealed-ledger/src/sealed_ledger/api.py:191|''|1|docs/IMPLEMENTATION.md, services/sealed-ledger/README.md|
|`FIELD_LEDGER_CALLER_ID`|field-core|field-core/src/field_core/clients.py:103|''|1|docs/runbooks/token-renewal.md, services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_CALLER_KEY`|field-core|field-core/src/field_core/clients.py:104|''|1|docs/runbooks/token-renewal.md, services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_CALLER_KEYRING`|sealed-ledger|sealed-ledger/src/sealed_ledger/api.py:176|(none)|1|docs/runbooks/v1.2-deploy-rollback.md, services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_CRASH_AT`|sealed-ledger|sealed-ledger/src/sealed_ledger/store.py:520|(none)|2|services/sealed-ledger/SPEC.md|
|`FIELD_LEDGER_OBSERVE_EVERY`|lifecycle-manager,sealed-ledger|lifecycle-manager/src/lifecycle_manager/api.py:374|'',(none)|3|services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_OBSERVE_HEALTH`|sealed-ledger|sealed-ledger/src/sealed_ledger/operator_observer.py:547|(none)|2|services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_READ_CONCURRENCY`|sealed-ledger|sealed-ledger/src/sealed_ledger/store.py:1477|'1'|1|services/sealed-ledger/README.md, services/sealed-ledger/SPEC.md|
|`FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE`|sealed-ledger|sealed-ledger/src/sealed_ledger/api.py:167|''|1|docs/runbooks/v1.2-deploy-rollback.md, services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_REQUIRE_SIGNING`|sealed-ledger|sealed-ledger/src/sealed_ledger/api.py:152|''|1|docs/runbooks/v1.2-deploy-rollback.md, services/sealed-ledger/README.md (+2)|
|`FIELD_LEDGER_RETENTION_DAYS`|sealed-ledger|sealed-ledger/src/sealed_ledger/retention.py:52|(none)|1|integration/fly/README.md, docs/IMPLEMENTATION.md (+3)|
|`FIELD_LEDGER_SIGN_KEY`|attestation-reporter,sealed-ledger|attestation-reporter/src/attestation_reporter/signing.py:160|(none)|2|docs/runbooks/v1.2-deploy-rollback.md, services/sealed-ledger/README.md (+1)|
|`FIELD_LEDGER_URL`|agent-registry,compliance-crosswalk,conformance-sentinel,field-agent,field-core,force-gateway,incident-replay,sealed-ledger,spend-governor|field-agent/src/field_agent/canary.py:502|'','http://127.0.0.1:8002',(none),(required: KeyError)|11|docs/ARCHITECTURE.md, docs/IMPLEMENTATION.md (+7)|
|`FIELD_LIFECYCLE_EVERY`|lifecycle-manager,sealed-ledger|lifecycle-manager/src/lifecycle_manager/api.py:374|'',(none)|3|docs/IMPLEMENTATION.md, services/lifecycle-manager/README.md (+2)|
|`FIELD_LIFECYCLE_ROSTER`|delegation-authority,lifecycle-manager|delegation-authority/src/delegation_authority/cli.py:373|'',(none)|3|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+4)|
|`FIELD_LIFECYCLE_URL`|ops-console|ops-console/src/ops_console/api.py:356|'http://127.0.0.1:8012'|1|docs/IMPLEMENTATION.md, services/lifecycle-manager/README.md|
|`FIELD_MANIFEST_DIR`|agent-registry,conformance-sentinel,field-core,ops-console|field-core/src/field_core/clients.py:451|'.',(none)|5|packages/field-core/README.md, docs/IMPLEMENTATION.md (+9)|
|`FIELD_NTFY_BASE_URL`|field-core|field-core/src/field_core/alerts.py:346|(none)|1|docs/runbooks/ntfy-alerts.md|
|`FIELD_NTFY_TOKEN`|field-core|field-core/src/field_core/alerts.py:81|(const, read via env mapping)|1|docs/runbooks/ntfy-alerts.md|
|`FIELD_NTFY_TOKEN_FILE`|field-core|field-core/src/field_core/alerts.py:80|(const, read via env mapping)|1|docs/runbooks/ntfy-alerts.md|
|`FIELD_NTFY_TOPIC`|field-core|field-core/src/field_core/alerts.py:78|(const, read via env mapping)|1|packages/field-core/README.md, docs/runbooks/ntfy-alerts.md|
|`FIELD_NTFY_TOPIC_FILE`|field-core|field-core/src/field_core/alerts.py:77|(const, read via env mapping)|1|packages/field-core/README.md, docs/runbooks/ntfy-alerts.md|
|`FIELD_OPERATOR`|delegation-authority,field-core,kill-switch,lifecycle-manager|field-core/src/field_core/operator_auth.py:355|''|7|docs/runbooks/token-renewal.md, docs/runbooks/v1.2-deploy-rollback.md (+2)|
|`FIELD_OPERATOR_KEY`|delegation-authority,field-core,kill-switch,lifecycle-manager|field-core/src/field_core/operator_auth.py:358|''|6|docs/runbooks/token-renewal.md, docs/runbooks/v1.2-deploy-rollback.md (+2)|
|`FIELD_OPERATOR_KEY_FILE`|delegation-authority,field-core,kill-switch,lifecycle-manager|field-core/src/field_core/operator_auth.py:356|''|4|docs/runbooks/token-renewal.md, docs/runbooks/v1.2-deploy-rollback.md (+2)|
|`FIELD_OPERATOR_REGISTRY`|field-core|field-core/src/field_core/operator_auth.py:278|''|1|docs/runbooks/v1.2-deploy-rollback.md, services/kill-switch/README.md (+1)|
|`FIELD_OPERATOR_REQUIRE`|field-core|field-core/src/field_core/operator_auth.py:262|''|1|docs/runbooks/token-renewal.md, docs/runbooks/v1.2-deploy-rollback.md (+3)|
|`FIELD_ORG_NAME`|federation-broker|federation-broker/src/federation_broker/engine.py:56|<expr>|1|docs/IMPLEMENTATION.md, services/federation-broker/README.md (+2)|
|`FIELD_PRICE_BOOK`|field-core|field-core/src/field_core/pricing.py:191|(none)|1|services/spend-governor/README.md (+1)|
|`FIELD_REGISTRY_URL`|conformance-sentinel,field-agent,field-core|field-agent/src/field_agent/bootstrap.py:41|'http://127.0.0.1:8001',(required: KeyError)|4|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+4)|
|`FIELD_REPLAY_URL`|incident-replay|incident-replay/src/incident_replay/cli.py:25|'http://127.0.0.1:8007'|1|docs/IMPLEMENTATION.md|
|`FIELD_SELF_AGENT_ID`|field-core|field-core/src/field_core/llm.py:99|(via helper)|1|services/force-gateway/README.md (+1)|
|`FIELD_SELF_TOKEN_ID`|field-core|field-core/src/field_core/llm.py:100|(via helper)|1|services/force-gateway/README.md (+1)|
|`FIELD_SENTINEL_JUDGE`|conformance-sentinel|conformance-sentinel/src/conformance_sentinel/judge.py:192|''|1|docs/capstone-evidence/sentinel-scorecard-s2.md, services/conformance-sentinel/README.md (+1)|
|`FIELD_SENTINEL_MODE`|conformance-sentinel|conformance-sentinel/src/conformance_sentinel/mode.py:32|''|1|docs/INTEGRATION.md, docs/runbooks/token-renewal.md (+4)|
|`FIELD_SENTINEL_URL`|claude-approver,conformance-sentinel,force-gateway|claude-approver/src/claude_approver/config.py:90|'http://127.0.0.1:8004',(none)|4|docs/INTEGRATION.md, docs/IMPLEMENTATION.md (+4)|
|`FIELD_SHARED_SECRET`|field-agent,field-core|field-agent/src/field_agent/canary.py:496|'',(none)|3|integration/fly/README.md, packages/field-agent/examples/README.md (+28)|
|`FIELD_WITNESS_ESTATE_WATCHED`|lifecycle-manager|lifecycle-manager/src/lifecycle_manager/engine.py:179|''|2|services/lifecycle-manager/README.md|
|`FIELD_WITNESS_EVERY`|lifecycle-manager|lifecycle-manager/src/lifecycle_manager/engine.py:175|''|2|docs/runbooks/v1.2-deploy-rollback.md, services/sealed-ledger/README.md (+2)|
|`FIELD_WITNESS_FLY_SECRET_FILE`|sealed-ledger|sealed-ledger/src/sealed_ledger/witness.py:259|''|1|docs/runbooks/v1.2-deploy-rollback.md, services/sealed-ledger/README.md|
|`FORCE_GATEWAY_BYPASS_COOLDOWN`|force-gateway|force-gateway/src/force_gateway/api.py:779|'10'|1|services/force-gateway/README.md|
|`FORCE_GATEWAY_ENFORCE`|force-gateway|force-gateway/src/force_gateway/api.py:285|(none)|1|docs/adr/ADR_Pack_10_FORCE_Gateway.md, docs/runbooks/v1.2-deploy-rollback.md (+3)|
|`FORCE_GATEWAY_LATENCY_BUDGET_MS`|force-gateway|force-gateway/src/force_gateway/api.py:776|'250'|1|services/force-gateway/README.md (+1)|
|`FORCE_GATEWAY_MOCK`|force-gateway|force-gateway/src/force_gateway/api.py:230|(none)|1|docs/IMPLEMENTATION.md, services/force-gateway/README.md (+1)|
|`FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM`|field-core,force-gateway|field-core/src/field_core/llm.py:181|''|2|CHANGELOG.md|
|`FORCE_GATEWAY_SAMPLE_EVERY`|force-gateway|force-gateway/src/force_gateway/hygiene_judge.py:176|''|1|services/force-gateway/README.md (+1)|
|`FORCE_GATEWAY_SENTINEL_TIMEOUT`|force-gateway|force-gateway/src/force_gateway/api.py:302|''|1|docs/runbooks/v1.2-deploy-rollback.md, services/force-gateway/README.md (+1)|
|`FORCE_GATEWAY_TOOL_CHECK`|force-gateway|force-gateway/src/force_gateway/api.py:290|(none)|1|docs/adr/ADR_Pack_10_FORCE_Gateway.md, docs/runbooks/v1.2-deploy-rollback.md (+2)|
|`FORCE_GATEWAY_URL`|field-core|field-core/src/field_core/llm.py:86|(via helper)|2|packages/field-core/README.md, docs/IMPLEMENTATION.md (+6)|
|`FORCE_HYGIENE_BAND`|force-gateway|force-gateway/src/force_gateway/api.py:771|'0.15'|1|services/force-gateway/README.md|
|`FORCE_HYGIENE_BASELINE_WINDOWS`|force-gateway|force-gateway/src/force_gateway/api.py:772|'2'|1|**NONE**|
|`FORCE_HYGIENE_JUDGE`|force-gateway|force-gateway/src/force_gateway/hygiene_judge.py:165|''|1|services/force-gateway/README.md (+1)|
|`FORCE_HYGIENE_JUDGE_MODEL`|force-gateway|force-gateway/src/force_gateway/hygiene_judge.py:114|<expr>|1|services/force-gateway/README.md|
|`FORCE_HYGIENE_WINDOW`|force-gateway|force-gateway/src/force_gateway/api.py:770|'5'|1|services/force-gateway/README.md|
|`FORCE_TELEMETRY_RETAIN`|force-gateway|force-gateway/src/force_gateway/store.py:71|''|1|docs/IMPLEMENTATION.md, services/force-gateway/README.md|
|`FORCE_TELEMETRY_WINDOW`|force-gateway|force-gateway/src/force_gateway/api.py:238|''|1|docs/IMPLEMENTATION.md, services/force-gateway/README.md|

## What I did NOT do
- Edit the repo or add docs/ENVIRONMENT.md (report only; no PR).
- Read each README to check that the variable's meaning and accepted values are explained (only the name's presence).
- Cover `tools/`, `plugins/`, `integration/` scripts or shell variables.
