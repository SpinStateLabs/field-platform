# Roadmap audit: 2026-11-21 (roley.reviewer)

- **Scope:** read-only audit of `main` at `cb7a94f8`.
- **Method:** I posted the adversarial reviews (Task A) before reading any other reviewer's verdict. Four read-only sub-agents gathered the README claims and test evidence. I then spot-checked one claim from each agent's output by hand; those checks are marked ✔.
- **Estate:** one unauthenticated `GET https://force-field-sandbox.fly.dev/health` at 2026-11-21T15:25:08Z returned HTTP 200 with `service: ops-console`, `build_sha: cb7a94f8…`, `operator_mode: enforce` and `internal_secret_sha256_present: false`. I made no other estate request and used no credential.

**Verdict key:**
- **VERIFIED:** a named test on main asserts the claimed behaviour. Test bodies were read, except the sealed-ledger rows without a †, which were matched on their specific test names only.
- **PARTIAL:** a test exists but misses part of the claim.
- **UNBACKED:** no test was found.

Paths in each table are relative to that service's directory unless they are given in full.

## Summary

| Item | Result |
|---|---|
| (1) README "Enforced" claims | 257 claims: **237 VERIFIED, 19 PARTIAL, 1 UNBACKED**. 2 rows contradict the code, and 2 are stale. |
| (2a) Policy-driven gate verdicts | **PARTIAL.** Verdicts are driven by manifests through the sentinel, but the rules are hard-coded, and `deny_patterns_verdict: policy` is declared in the schema but nothing in this repo consumes it. |
| (2b) `kill_switch.local_sentinel` | **Schema and host watcher are on main and tested. Nothing is wired into the estate.** The gate half sits on an unmerged Force-Field branch. |
| (3) Merges in the last 14 days with no review | **25 of 25** merged PRs have 0 GitHub reviews and 0 PR comments. 3 have indirect review evidence in commit messages. |

## Findings that need action, ranked by severity

1. **MEDIUM: the estate perimeter secret fails open.** `integration/fly/entrypoint.sh:101` defaults `FIELD_SHARED_SECRET` to empty and never refuses to start. Compare the refusing hash check at `entrypoint.sh:118-133`. With the secret unset, `field_core.authn` lets every route through (`packages/field-core/src/field_core/authn.py:78`). I verified locally that `/pack` returns 200 in that case.
   - The fix branches named for review (`bob/entrypoint-empty-secret`, `bob/probe-heavy-guard`) do not exist on origin (`git ls-remote`, 2026-11-21).
   - See the review comments on #1081 and #1082.
2. **MEDIUM: ops-console README:48 is contradicted by the code.** The README says "Operator name is mandatory on every mutation", but `POST /api/tokens/{id}/revoke` (`services/ops-console/src/ops_console/api.py:855-858`) takes no operator. `services/ops-console/tests/test_ops_console.py:140` revokes with no operator and asserts 200. ✔
3. **LOW: force-gateway README:243 is contradicted by the tests.** The README says "Every proxied call carries the preset's FORCE block", but bypassed calls are forwarded without the block, and tests assert exactly that:
   - `services/force-gateway/tests/test_gateway_delta.py:255` ✔
   - `test_f1_enforce.py:434`
   - Judge passthrough: `test_d2_upstream_passthrough.py:140`

   The row needs an exception clause.
4. **LOW: incident-replay README:89 is unbacked.** The claim is "No LLM in the report path". `tests/test_incident_replay.py:127` only checks the label text. The claim is true on code inspection, but no import guard or other test pins it.
5. **LOW: two stale rows.**
   - claude-approver README:150 cites "17 of 17" mutant tests. No test runs the mutant (`services/claude-approver/pyproject.toml:35` is only a marker), and the marker appears 21 times. MEDIUM confidence, because of parametrized tests.
   - The ops-console "operator is who they typed: Declared only" row predates the Phase G operator auth, which is tested at `services/ops-console/tests/test_operator_auth_g_ops_console.py:71`.
6. **LOW, pattern: the shared-secret middleware is pinned per app in only some services.** Six of the 14 READMEs rest their "shared-secret enforced" row on the toy app at `packages/field-core/tests/test_authn.py:32`, with no 401 test against the service's own app:
   - conformance-sentinel :335
   - federation-broker :149
   - incident-replay :145
   - kill-switch :175
   - spend-governor :214
   - force-gateway :342 (only the `/health`-open half is affected)

   PR #1081/#1082 closes this gap for attestation-reporter only, and attestation-reporter was already pinned at `services/attestation-reporter/tests/test_api.py:113`.

## (1) README "Enforced" claims against tests on main

"Enforced" claims means every row marked "Enforced in code" in each README's "Enforced vs. Declared" table, plus the prose "shared-secret enforced" line. Negations ("not enforced", "never enforced HERE") and Declared-only rows are excluded. None of the Declared-only rows contradicts the code, apart from the stale ops-console row above.

### agent-registry: 10 claims, 10 VERIFIED

| README line | Test | Verdict |
|---|---|---|
| :40 | tests/test_agent_registry.py:49, :62; tests/test_registry_update_validation.py:49 | VERIFIED |
| :41 | tests/test_registry_update_atomicity.py:125, :235 | VERIFIED |
| :42 | tests/test_agent_registry.py:70, :99 | VERIFIED |
| :43 | tests/test_d3_credential_scan.py:90-395; tests/test_d3_scan_hardening.py:89, :135, :196 | VERIFIED |
| :45 | tests/test_d3b_manifest_ref_resolves.py:77, :119, :138 | VERIFIED |
| :46 | tests/test_patch_manifest_ref_by_mode.py:61, :68 | VERIFIED |
| :47 | tests/test_on_behalf_of_c12_agent_registry.py:89-154; tests/test_on_behalf_of_c12_enforce_refusal.py:72, :125 | VERIFIED |
| :48 | tests/test_on_behalf_of_reserved_c12_agent_registry.py:98; services/sealed-ledger/tests/test_on_behalf_of_reserved_ledger.py:63 | VERIFIED |
| :49 | tests/test_attestation_and_migration.py:76, :90 | VERIFIED |
| :123 (shared secret) | tests/test_registry_pins_c162.py:144 | VERIFIED |

### attestation-reporter: 22 claims, 21 VERIFIED, 1 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :19 | tests/test_attestation_reporter.py:148 | VERIFIED |
| :152 (shared secret) | tests/test_api.py:113 ✔ | VERIFIED |
| :193 | tests/test_attestation_reporter.py:74 | VERIFIED |
| :194 | tests/test_attestation_reporter.py:137; tests/test_c4_window_and_signature.py:411 | **PARTIAL**: registry and delegation outages are not asserted as unavailable |
| :195 | tests/test_c4_window_and_signature.py:532; tests/test_attestation_reporter.py:170 | VERIFIED |
| :196 | tests/test_c4_window_and_signature.py:429, :479 | VERIFIED |
| :197 | tests/test_attestation_reporter.py:81; tests/test_c4_window_and_signature.py:626 | VERIFIED |
| :198 | tests/test_retention_metrics.py:80, :118 | VERIFIED |
| :199 | tests/test_attestation_reporter.py:111 | VERIFIED |
| :200 | tests/test_c4_window_and_signature.py:360, :381 | VERIFIED |
| :201 | tests/test_c4_window_and_signature.py:200-268 | VERIFIED |
| :202 | tests/test_c4_window_and_signature.py:1089, :290, :323 | VERIFIED |
| :203 | tests/test_f4_served_signing.py:147, :209, :437 | VERIFIED |
| :204 | tests/test_f4_served_signing.py:247-363 | VERIFIED |
| :205 | tests/test_f4_served_signing.py:404, :472 | VERIFIED |
| :206 | tests/test_c4_window_and_signature.py:795, :1015 | VERIFIED |
| :207 | tests/test_c4_window_and_signature.py:847, :908 | VERIFIED |
| :208 | tests/test_c4_window_and_signature.py:939, :957 | VERIFIED |
| :209 | tests/test_c4_window_and_signature.py:683 | VERIFIED |
| :210 | tests/test_c4_window_and_signature.py:626 | VERIFIED |
| :211 | tests/test_c4_window_and_signature.py:587 | VERIFIED |
| :212 | tests/test_c4_window_and_signature.py:411 | VERIFIED |


### claude-approver: 12 claims, 12 VERIFIED

| README line | Test | Verdict |
|---|---|---|
| :150 | tests/test_approver_tick.py:108, :27 | VERIFIED (the mutant count is stale; see finding 5) |
| :151 | tests/test_approver_tick.py:108, :329; tests/test_approver_estate.py:73 | VERIFIED |
| :152 | tests/test_approver_tick.py:120 | VERIFIED |
| :153 | tests/test_approver_tick.py:137, :146 | VERIFIED |
| :154 | tests/test_approver_api.py:39 | VERIFIED |
| :155 | tests/test_approver_estate.py:43-125; tests/test_approver_review_fixes.py:184, :214 | VERIFIED |
| :156 | tests/test_approver_tick.py:159, :183, :204; tests/test_approver_review_fixes.py:139 | VERIFIED |
| :157 | tests/test_approver_review_fixes.py:80, :103; tests/test_approver_selection_c257.py:59, :81 | VERIFIED |
| :158 | tests/test_approver_review_fixes.py:30, :52, :68; tests/test_approver_retry_applied_c258.py:221-251 | VERIFIED |
| :159 | tests/test_approver_usage.py:15-104; tests/test_approver_review_fixes.py:231 | VERIFIED |
| :160 | tests/test_approver_api.py:112, :161; tests/test_approver_review_fixes.py:152 | VERIFIED |
| :199 (shared secret) | tests/test_approver_api.py:192 | VERIFIED |

### compliance-crosswalk: 15 claims, 13 VERIFIED, 2 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :282 | tests/test_crosswalk.py:29 | VERIFIED |
| :283 | tests/test_crosswalk.py:182 | VERIFIED |
| :284 | tests/test_crosswalk.py:190, :222 | **PARTIAL**: the live `collect_evidence` (src api.py:213) is always faked (tests/test_pack_api.py:211) |
| :285 | tests/test_suggestions.py:40, :90 | VERIFIED |
| :286 | tests/test_suggestions.py:118 | VERIFIED |
| :287 | tests/test_evidence_pack.py:61; tests/test_signer_sanitise_c252.py:70-225; tests/test_pack_api.py:124 | VERIFIED |
| :289 | tests/test_evidence_pack.py:68, :88; tests/test_pack_api.py:157; tests/test_stale_clear_name_cw10.py:35 | VERIFIED |
| :290 | tests/test_evidence_pack.py:97, :137 | **PARTIAL**: only one row is checked; no test walks every row |
| :294 | tests/test_regwatch.py:142-755; tests/test_regwatch_api.py:108 | VERIFIED |
| :295 | tests/test_regwatch.py:416 | VERIFIED |
| :296 | tests/test_regwatch_api.py:152, :130 | VERIFIED |
| :297 | tests/test_regwatch.py:515, :564, :467, :481 | VERIFIED |
| :298 | tests/test_regwatch.py:632-693; tests/test_byte_cap_boundary_c394.py:33-120 | VERIFIED |
| :299 | tests/test_regwatch.py:811, :855 | VERIFIED |
| :301 | tests/test_regwatch_check_file.py:112-399 | VERIFIED |

### conformance-sentinel: 21 claims, 19 VERIFIED, 2 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :149 | tests/test_self_manifest.py:36 | VERIFIED |
| :218 | tests/test_sentinel.py:22 | VERIFIED |
| :219 | tests/test_sentinel.py:81, :95 | VERIFIED |
| :220 | tests/test_sentinel.py:72; tests/test_scorecard.py:136 | **PARTIAL**: no test of an expired token in enforce mode |
| :221 | tests/test_sentinel.py:42, :50 | VERIFIED |
| :222 | tests/test_sentinel.py:147; tests/test_f2_fail_closed.py:57-81 | VERIFIED |
| :223 | tests/test_f2_fail_closed.py:118-190 | VERIFIED |
| :224 | tests/test_sentinel.py:137 | VERIFIED |
| :225 | tests/test_throttle_metering.py:71-141 | VERIFIED |
| :226 | tests/test_throttle_metering.py:222-484 | VERIFIED |
| :227 | tests/test_throttle_metering.py:532-598 | VERIFIED |
| :228 | tests/test_throttle_metering.py:640 | VERIFIED |
| :229 | tests/test_caller_context_ledger.py:50; tests/test_sentinel.py:81 | VERIFIED |
| :230 | tests/test_sentinel.py:247, :198 | VERIFIED |
| :231 | tests/test_scorecard.py:49 | VERIFIED |
| :232 | tests/test_judge.py:104-212 | VERIFIED |
| :233 | tests/test_judge.py:49, :59 | VERIFIED |
| :235 | tests/test_self_manifest.py:26, :53 | VERIFIED |
| :236 | tests/test_self_manifest.py:147, :161 | VERIFIED |
| :237 | tests/test_self_manifest.py:93, :123 | VERIFIED |
| :335 (shared secret) | packages/field-core/tests/test_authn.py:32 | **PARTIAL**: toy app only |

### delegation-authority: 12 claims, 12 VERIFIED

| README line | Test | Verdict |
|---|---|---|
| :208 | tests/test_delegation_authority.py:91, :98 | VERIFIED |
| :209 | tests/test_delegation_authority.py:105 | VERIFIED |
| :210 | tests/test_delegation_authority.py:122; packages/field-core/tests/test_delegation_and_conformance.py:48 | VERIFIED |
| :211 | tests/test_delegation_authority.py:147 | VERIFIED |
| :212 | tests/test_delegation_authority.py:156; tests/test_revoke_c625.py:70 | VERIFIED |
| :213 | tests/test_doa_roster.py:147-232; tests/test_redteam_mint_matrix.py:279-318 | VERIFIED |
| :214 | tests/test_doa_check_verb.py:185-376 | VERIFIED |
| :215 | tools/tests/test_generate_doa_roster.py:101-310; tools/tests/test_doa_roster_job_rows.py:125 | VERIFIED |
| :217 | tests/test_d1e_token_ceiling.py:57-146 | VERIFIED |
| :218 | services/conformance-sentinel/tests/test_throttle_metering.py:640 | VERIFIED |
| :219 | tests/test_oauth_introspect.py:162 | VERIFIED |
| :266 (shared secret) | tests/test_redteam_mint_matrix.py:456, :480 | VERIFIED |

### federation-broker: 12 claims, 10 VERIFIED, 2 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :94 | tests/test_federation_broker.py:165 | VERIFIED |
| :95 | tests/test_federation_broker.py:115 | VERIFIED |
| :96 | tests/test_federation_broker.py:135, :146, :158 | VERIFIED |
| :97 | tests/test_federation_broker.py:102, :146 | VERIFIED |
| :98 | tests/test_federation_broker.py:205, :214, :229 | VERIFIED |
| :99 | tests/test_federation_pubkey_cli.py:119, :129, :392 | VERIFIED |
| :100 | tests/test_federation_pubkey_cli.py:255, :167, :414 | VERIFIED |
| :101 | tests/test_federation_outbound.py:162-219 | VERIFIED |
| :102 | tests/test_federation_outbound.py:193-211 | VERIFIED |
| :103 | tests/test_federation_outbound.py:104-302 | **PARTIAL**: the direction on inbound BLOCK verdicts is not asserted |
| :106 | tests/test_federation_broker.py:243, :257, :270 | VERIFIED |
| :149 (shared secret) | packages/field-core/tests/test_authn.py:32 | **PARTIAL**: toy app only |

### force-gateway: 28 claims, 26 VERIFIED, 2 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :170 | tests/test_f1_enforce.py:423 | VERIFIED |
| :243 | tests/test_force_gateway.py:18, :49 | **PARTIAL, contradicted**: see finding 3 ✔ |
| :244 | tests/test_force_gateway.py:54, :63 | VERIFIED |
| :245 | tests/test_telemetry_analyze.py:140 | VERIFIED |
| :246 | tests/test_force_gateway.py:128; tests/test_d2_upstream_passthrough.py:164 | VERIFIED |
| :247 | tests/test_gateway_delta.py:226, :268 | VERIFIED |
| :248 | tests/test_gateway_delta.py:226, :268 | VERIFIED |
| :249 | tests/test_gateway_delta.py:181, :201 | VERIFIED |
| :250 | tests/test_gateway_delta.py:128, :148 | VERIFIED |
| :251 | tests/test_gateway_delta.py:83 | VERIFIED |
| :252 | tests/test_d2_store.py:294 | VERIFIED |
| :253 | tests/test_d2_rates.py:55-144 | VERIFIED |
| :254 | tests/test_d2_drift_dimensions.py:40-67 | VERIFIED |
| :256 | tests/test_d2_store.py:50, :110, :228 | VERIFIED |
| :257 | tests/test_d2_store.py:257, :283 | VERIFIED |
| :258 | tests/test_d2_store.py:157 | VERIFIED |
| :259 | tests/test_d2_upstream_passthrough.py:140, :327 | VERIFIED |
| :260 | tests/test_d2_upstream_passthrough.py:265, :275 | VERIFIED |
| :261 | tests/test_d2_upstream_passthrough.py:140 | VERIFIED |
| :262 | tests/test_d2_upstream_passthrough.py:164, :186 | VERIFIED |
| :263 | tests/test_d2_llm_callers.py:63-102; tests/test_d2_upstream_passthrough.py:88 | VERIFIED |
| :265 | tests/test_d2_upstream_passthrough.py:58 | VERIFIED |
| :270 | tests/test_f1_enforce.py:215-409; tests/test_f1_flags.py:128, :140 | VERIFIED (code half only) |
| :271 | tests/test_f1_flags.py:269-305; packages/field-core/tests/test_llm_f1.py:55 | VERIFIED |
| :272 | tests/test_f1_enforce.py:462-556; tests/test_f1_flags.py:114, :406 | VERIFIED |
| :273 | tests/test_f1_enforce.py:229, :271; tests/test_f1_flags.py:374, :383 | VERIFIED |
| :274 | tests/test_f1_flags.py:240, :246 | VERIFIED (structural only) |
| :342 (shared secret) | tests/test_d2_upstream_passthrough.py:265 | **PARTIAL**: `/health`-open is tested only on the toy app |

### incident-replay: 17 claims, 13 VERIFIED, 3 PARTIAL, 1 UNBACKED

| README line | Test | Verdict |
|---|---|---|
| :83 | tests/test_incident_replay.py:92 | **PARTIAL**: values are not pinned as derived only from the named sources |
| :84 | tests/test_incident_replay.py:149 | VERIFIED |
| :85 | tests/test_raci_from_data.py:949, :982 | VERIFIED |
| :86 | tests/test_incident_replay.py:130 | **PARTIAL**: no test of an event exactly on an inclusive boundary |
| :87 | tests/test_replay_truncation.py:77-108; tests/test_summary_bounds.py:42, :51 | VERIFIED |
| :88 | tests/test_raci_from_data.py:898 | VERIFIED |
| :89 | none (tests/test_incident_replay.py:127 checks the label only) | **UNBACKED** |
| :90 | tests/test_raci_from_data.py:390 | VERIFIED |
| :91 | tests/test_raci_from_data.py:204-747 | VERIFIED |
| :92 | tests/test_raci_from_data.py:663-827 | VERIFIED |
| :93 | tests/test_raci_from_data.py:300, :314, :929 | VERIFIED |
| :94 | tests/test_raci_from_data.py:373, :382, :929 | VERIFIED |
| :95 | tests/test_raci_from_data.py:348 | VERIFIED |
| :96 | tests/test_raci_from_data.py:400-445 | VERIFIED |
| :97 | tests/test_raci_from_data.py:276-880 | VERIFIED |
| :98 | tests/test_raci_from_data.py:464-523 | VERIFIED |
| :145 (shared secret) | packages/field-core/tests/test_authn.py:32 | **PARTIAL**: toy app only |

### kill-switch: 19 claims, 18 VERIFIED, 1 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :98 | tests/test_kill_switch.py:55 | VERIFIED |
| :99 | services/conformance-sentinel/tests/test_sentinel.py:22 | VERIFIED |
| :100 | services/delegation-authority/tests/test_delegation_authority.py:98 | VERIFIED |
| :101 | tests/test_kill_switch.py:77; tests/test_endpoint_and_liveness.py:558 | VERIFIED |
| :102 | tests/test_kill_switch.py:133 | VERIFIED |
| :103 | tests/test_endpoint_and_liveness.py:448, :480; tests/test_c19_kill_switch.py:134 | VERIFIED |
| :104 | tests/test_endpoint_and_liveness.py:319 | VERIFIED |
| :105 | tests/test_endpoint_and_liveness.py:167-781 | VERIFIED |
| :106 | tests/test_endpoint_and_liveness.py:629, :672; tests/test_halt_result_c811.py:104 | VERIFIED |
| :107 | tests/test_endpoint_and_liveness.py:702-734 | VERIFIED |
| :108 | tests/test_endpoint_and_liveness.py:811, :840, :289; tests/test_self_guard_c574.py:160 | VERIFIED |
| :109 | tests/test_endpoint_and_liveness.py:854-884 | VERIFIED |
| :110 | tests/test_endpoint_and_liveness.py:360 | VERIFIED |
| :111 | tests/test_endpoint_and_liveness.py:390, :414; tests/test_c19_kill_switch.py:42, :80; tests/test_cli_domain_partial_exit.py:38, :76 | VERIFIED |
| :112 | tests/test_endpoint_and_liveness.py:529, :567, :975 | VERIFIED |
| :114 | tests/test_retired_guard.py:45-115 | VERIFIED |
| :115 | tests/test_operator_auth_g_kill_switch.py:195-258 | VERIFIED |
| :116 | tests/test_on_behalf_of_c12_kill_switch.py:109, :148; tests/test_set_status_public_api_c12.py:95 | VERIFIED |
| :175 (shared secret) | packages/field-core/tests/test_authn.py:32 | **PARTIAL**: toy app only |

### lifecycle-manager: 26 claims, 26 VERIFIED

README :234-259, one claim per line: every row is backed by a test in `tests/`.

| README lines | Test files |
|---|---|
| :234 | test_witness_finding.py |
| :235-238 | test_lifecycle_manager.py:72-127 |
| :239-240, :243-245 | test_api.py:140-382; test_empty_roster_refusal.py:83 |
| :241-242 | test_roster_aliases.py:100-371 |
| :246-248, :251, :253-258 | test_transitions.py:231-697 |
| :249-250 | test_provision_rate_limits.py:171-282 |
| :252 | test_transitions.py:431; test_provision_alias_listed_require_g21.py:181 |
| :259 | test_retention_finding.py:101-255 |

Caveats:
- :235 claims determinism, but no test re-runs a sweep and compares the results.
- :241 says "mutation-checked", which the tests cannot confirm.

### ops-console: 12 claims, 9 VERIFIED, 3 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :47 | tests/test_ops_console.py:119 | VERIFIED |
| :48 | tests/test_ops_console.py:133; tests/test_console_features.py:309 | **PARTIAL, contradicted**: see finding 2 ✔ |
| :49 | tests/test_ops_console.py:96 | VERIFIED |
| :50 | tests/test_ops_console.py:153, :171; tests/test_console_features.py:333 | VERIFIED |
| :51 | tests/test_ops_console.py:178; tests/test_console_features.py:366 | VERIFIED |
| :52 | tests/test_console_identity_c14.py:94, :146, :197 | VERIFIED |
| :53 | tests/test_retired_agent_ui.py:46, :60 | VERIFIED |
| :54 | tests/test_console_features.py:294, :325 | **PARTIAL**: the FLEET HALT test asserts no ledger events |
| :55 | tests/test_halt_banner_counts_c19.py:73-119 | VERIFIED |
| :56 | tests/test_console_features.py:315 | **PARTIAL**: a halt with a missing operator or reason is never tested |
| :57 | tests/test_console_features.py:169, :192; tests/test_ops_console_c184.py:84, :117 | VERIFIED |
| :58 | tests/test_console_features.py:353, :366 | VERIFIED |

### sealed-ledger: 35 claims, 34 VERIFIED, 1 PARTIAL

Every cited test name exists on main. † marks rows whose test bodies were read; the rest were matched on their highly specific names (MEDIUM confidence).

| README line | Test | Verdict |
|---|---|---|
| :559 † | tests/test_sealed_ledger.py:23; tests/test_ledger_rotation.py:198 | VERIFIED |
| :560 † | tests/test_sealed_ledger.py:61, :78; tests/test_ledger_rotation.py:183 | VERIFIED |
| :561 † | tests/test_ledger_crash_points.py:258 | **PARTIAL**: tests cover process kills only, not fsync before ack or power loss |
| :562 † | tests/test_export_bundle.py:171, :191 | VERIFIED |
| :563 | tests/test_export_bundle.py:958-1123 | VERIFIED |
| :564 † | tests/test_export_bundle.py:349, :387 | VERIFIED |
| :566 | tests/test_time_filters.py:49-140 | VERIFIED |
| :568 † | tests/test_sealed_ledger.py:138 | VERIFIED |
| :569 | tests/test_ledger_rotation.py:72, :104, :286 | VERIFIED |
| :570 | tests/test_ledger_rotation.py:719; tests/test_ledger_c2_hardening.py:487, :644 | VERIFIED |
| :571 † | tests/test_ledger_rotation.py:299; tests/test_ledger_c2_hardening.py:1211 | VERIFIED |
| :572 | tests/test_ledger_crash_points.py:142 | VERIFIED |
| :573 | tests/test_ledger_readers.py:324; tests/test_ledger_rotation.py:686 | VERIFIED |
| :574 † | tests/test_ledger_readers.py:300 | VERIFIED |
| :575 | tests/test_ledger_rotation.py:243, :271 | VERIFIED |
| :576 | tests/test_ledger_rotation.py:971; tests/test_ledger_c2_hardening.py:929, :1061 | VERIFIED |
| :577 † | tests/test_ledger_c2_hardening.py:1234 | VERIFIED |
| :578 † | tests/test_ledger_rotation.py:806 | VERIFIED |
| :581 | tests/test_event_signing_f2.py:161, :427, :545 | VERIFIED |
| :582 | tests/test_event_signing_f2.py:179, :704 | VERIFIED |
| :583 | tests/test_event_signing_f2.py:192, :207, :316 | VERIFIED |
| :584 | tests/test_caller_signing_f2b.py:145-297 | VERIFIED |
| :585 | tests/test_caller_signing_f2b.py:362, :380, :436 | VERIFIED |
| :586 | tests/test_caller_signing_f2b.py:205, :527 | VERIFIED |
| :587 | tests/test_caller_signing_f2b.py:623, :712 | VERIFIED |
| :588 | tools/tests/test_volume_admin.py:428, :452 | VERIFIED |
| :590 | tests/test_ledger_retention.py:370, :400, :482 | VERIFIED |
| :591 | tests/test_ledger_retention.py:774, :815 | VERIFIED |
| :592 | tests/test_ledger_retention.py:97, :547; tests/test_ledger_c2_hardening.py:582 | VERIFIED |
| :593 | tests/test_ledger_retention.py:149, :181, :461 | VERIFIED |
| :595 | tests/test_ledger_retention.py:232, :301 | VERIFIED |
| :596 | tests/test_witness.py:138, :183 | VERIFIED |
| :597 † | tests/test_witness.py:220, :255 | VERIFIED |
| :598 | tests/test_witness.py:287, :299, :335 | VERIFIED |
| :599 | tests/test_witness.py:450, :460, :606 | VERIFIED |

### spend-governor: 16 claims, 14 VERIFIED, 2 PARTIAL

| README line | Test | Verdict |
|---|---|---|
| :18 | tests/test_throttle.py:314 | VERIFIED |
| :129 | tests/test_spend_governor.py:112 | VERIFIED |
| :130 | tests/test_spend_governor.py:54; tests/test_escalation_atomicity.py:92 | VERIFIED |
| :131 | tests/test_escalation_atomicity.py:159, :201 | VERIFIED |
| :132 | tests/test_spend_governor.py:68 | VERIFIED |
| :133 | tests/test_spend_governor.py:105; tests/test_bounds_and_audit_c246.py:73 | **PARTIAL**: negative tokens, actions and `/usage` values are untested |
| :134 | tests/test_spend_governor.py:99 | VERIFIED |
| :135 | tests/test_spend_governor.py:39, :131 | VERIFIED |
| :136 | services/conformance-sentinel/tests/test_throttle_metering.py:222, :405; services/force-gateway/tests/test_f1_enforce.py:229 | VERIFIED |
| :139 | tests/test_throttle.py:150, :178 | VERIFIED |
| :140 | tests/test_throttle.py:642, :661, :674 | VERIFIED |
| :142 | tests/test_throttle.py:335, :349, :486 | VERIFIED |
| :143 | tests/test_throttle.py:422; services/lifecycle-manager/tests/test_provision_rate_limits.py:171 | VERIFIED |
| :144 | tests/test_throttle.py:593, :609 | VERIFIED |
| :145 | tests/test_throttle.py:756 | VERIFIED |
| :214 (shared secret) | packages/field-core/tests/test_authn.py:32 | **PARTIAL**: toy app only |

### Totals

**257 claims: 237 VERIFIED, 19 PARTIAL, 1 UNBACKED.**

## (2) State on main

### (2a) Policy-driven gate verdicts: PARTIAL

**Docs:**
- `ROADMAP.md:9` says only "Deterministic cores shipped". There is no separate roadmap item for policy-driven verdicts.
- `docs/adr/ADR_Pack_02_Conformance_Sentinel.md:9` says a deterministic policy engine is the primary evaluator.
- `STATE.md:101` records the manifest key `deny_patterns_verdict` (`deny` | `policy`, default `deny`).

**Code:**
- The only verdict producer is `services/conformance-sentinel/src/conformance_sentinel/engine.py:394` (`check`). It reads per-agent manifest fields: scope (:576), `irreversible_action_policy` (:600-611), triggers (:614) and spend cap (:635).
- The step order and the mapping from condition to decision are hard-coded. No separate policy or rule file is loaded.
- force-gateway (`services/force-gateway/src/force_gateway/api.py:590-637`) and claude-approver (`services/claude-approver/src/claude_approver/core.py:492`) only relay the sentinel's ALLOW. Anything else fails closed.

**`deny_patterns_verdict`:**
- Declared and validated at `packages/field-core/src/field_core/manifest.py:128`.
- **Nothing in `services/`, `plugins/` or `tools/` consumes it** (`grep -rn deny_patterns_verdict services plugins tools`: no hits ✔).

**Tests:**
- `services/conformance-sentinel/tests/test_fail_closed_pins_c168.py:187`, `:206`
- `services/conformance-sentinel/tests/test_sentinel.py:81`, `:106`
- `services/conformance-sentinel/tests/test_escalation_trigger_edges.py:20`
- `deny_patterns_verdict` has schema tests only: `packages/field-core/tests/test_validation_parity.py:223`, `:241`

### (2b) `kill_switch.local_sentinel`: schema and watcher present, not wired

- **Schema:**
  - `packages/field-core/src/field_core/manifest.py:105` ✔ (`local_sentinel`), `:106` (`sentinel_max_age_s`)
  - `packages/field-core/src/field_core/schema/manifest-schema.json:129`
  - Vendored copy: `plugins/field-agent/templates/manifest-schema.json:129`
- **Host watcher:** `tools/estate_kill_watcher.py:116` (`poll`), `:167` (`apply`), `:201` (`from_manifest`), `:283` (`main`).
- **Deployment agent:** requires the key at `tools/deployment_agent/manifest.py:85`; `manifests/deployment-agent.yaml:64` sets it.
- **Tests:**
  - `tools/tests/test_estate_kill_watcher.py:148`, `:191`, `:372`. That file has 23 `def test_` functions, while `STATE.md:93` says 36 tests; the difference may be parametrized cases (UNSURE).
  - `packages/field-core/tests/test_validation_parity.py:252`, `:268`
  - `tools/tests/test_deployment_agent_cli_manifest.py:135`
  - `tools/tests/test_deployment_agent_manifest_shapes.py:47`
- **Not wired:**
  - The `kill-switch` service never references it.
  - No compose, Fly, Dockerfile or cron file installs the watcher. `STATE.md:96` ✔ says "Not done: the watcher is not installed anywhere".
  - The gate half lives on Force-Field branch `claude/adr-0072-estate-kill-local-sentinel`, which is "not merged" (`STATE.md:88-89` ✔).
  - `STATE.md:87` still labels the section DRAFT.
  - `ROADMAP.md` does not mention it.

## (3) Merged changes in the last 14 days with no review on record

**Window:** merged on or after 2026-11-07.

**Sources:** `gh api search/issues "is:pr is:merged merged:>=2026-11-07"` returned 25 PRs. `pull_request_read get_reviews` returned `[]` for every one of them, and the search's `comments` field is 0 for every one.

**Result:** all 25 have **no GitHub review and no PR comment**. Every one was authored and merged by the same account, `dhagell`.

| PR | Merged (UTC) | Title (abridged) | Indirect review evidence |
|---|---|---|---|
| #837 | 11-07 18:25 | G18: stage1_window | none |
| #950 | 11-08 02:38 | Batch m3: PRs 920, 885, 881 | none (constituent PRs not checked) |
| #973 | 11-08 02:59 | batch m4a: 12 PRs | none (constituents not checked) |
| #975 | 11-08 13:54 | batch m4b: 9 services PRs | none (constituents not checked) |
| #1012 | 11-08 19:36 | batch m6b | none (constituents not checked) |
| #1016 | 11-08 20:36 | batch m8b | none (constituents not checked) |
| #1017 | 11-09 00:59 | batch m9b | none (constituents not checked) |
| #1049 | 11-09 05:29 | batch m5a: 15 PRs | none (constituents not checked) |
| #1052 | 11-09 12:41 | batch m12b: 17 services PRs | none (constituents not checked) |
| #1054 | 11-10 10:37 | Stage 2 Actions driver | commit `df376056d`, "(PR 1054 C1, C2)" |
| #1055 | 11-10 14:43 | read-only Stage2Estate | commit `5f33067ac`, "(R-PR1055 1, 2, 3)" |
| #1057 | 11-10 15:11 | fly entrypoint: FIELD_INTERNAL_SECRET_SHA256 | commits `8eeb4bc72`, `2ff17d28d`, "(R-PR867 …)" |
| #1058 | 11-13 06:18 | docs: STATE.md GB10 correction | none |
| #1059 | 11-13 06:42 | defence-shield: S.pivot index | none |
| #1060 | 11-13 06:19 | defence-shield: calibrate sweep | #1063 fixes "1060 LOWs" |
| #1063 | 11-13 07:18 | calibrate: 1060 LOWs | none (it is itself a review follow-up) |
| #1064 | 11-13 07:24 | synthetic labelled corpus | none |
| #1069 | 11-13 19:21 | Fly image: strip setuid; sysctls | none |
| #1070 | 11-13 23:41 | ops-console redesign | none |
| #1071 | 11-14 02:45 | GB10 image: strip setuid | none |
| #1073 | 11-14 02:14 | sentinel /check: stop echoing token id | none |
| #1074 | 11-20 17:20 | estate_probe: --timeout | none |
| #1075 | 11-20 19:52 | T6: heavy ledger routes vs /health | none |
| #1076 | 11-20 23:49 | T7: ledger-head parse cache | none |
| #1078 | 11-21 02:44 | T8: /verify not from cache once archived | none |

**Limits:**
- Reviews held outside GitHub (chat sessions, `tasks/`) are not visible to this method. Grepping `tasks/`, `docs/`, `STATE.md` and `CHANGELOG.md` on main for each PR number found no review record.
- Reviews on the PRs that the batch PRs bundled were not checked.
- A single-account repository cannot record a formal GitHub approval from its own author, so "no review on record" is structural here, not necessarily a sign that no review happened.

— roley.reviewer

## (4) Post-merge reviews of merges with no review on record (roley.reviewer, appended 2026-11-21)

Each review was run on the merge commit, as GO-LIVE-LOOP reviewer fallback (b) requires. The follow-up cards were proposed to the controller through comms. Paths and line numbers are on the reviewed merge commit unless the text names another.

### #1057 post-merge (roley.reviewer, 8eeb4bc)

Status: COMPLETE (2026-11-21). Written incrementally; sections appear in the order they were done.

**Merge sha:** 8eeb4bc72c87546a292361c229c93abb0f2e7d5c. PR merged as fast-forward: head sha == commit on main first-parent chain (`git log --first-parent origin/main` shows 8eeb4bc72 with parent 2ff17d28d; GitHub PR get: head.sha 8eeb4bc, merged_at 2026-11-10T15:11:18Z). HIGH.
Base 5f33067ac. 4 commits: cb727e90a, 9ea3b1536, 2ff17d28d, 8eeb4bc72. Files: integration/fly/entrypoint.sh (+27), tools/tests/test_fly_identity_c5.py (+163), tools/tests/test_internal_secret_hash_fly_docs.py (+39), docs/ENVIRONMENT.md, docs/runbooks/v1.2-deploy-rollback.md (`git diff --stat 5f33067ac 8eeb4bc72`). HIGH.

#### (3) Tests (venv /tmp/claude-0/venv1057, installed per .github/workflows/ci.yml "Install platform" step: pip 26.2.2, constraints, field-core[dev], 14 services --no-deps, field-agent, agent-incident-retro, fastapi uvicorn httpx pytest; Python 3.13.18)
- Merge 8eeb4bc: `python -m pytest -q -p no:cacheprovider tools/tests/test_fly_identity_c5.py tools/tests/test_internal_secret_hash_fly_docs.py` -> `129 passed in 91.18s (0:01:31)` HIGH
- origin/main d2cfab30c (worktree /tmp/claude-0/pm1057main, PYTHONPATH to its field-core src): same command -> `129 passed in 90.97s (0:01:30)` HIGH
- Between 8eeb4bc and main only integration/fly/entrypoint.sh changed among the touched files (+11, commit 6bc2c80fa #1069: FIELD_HARDEN_SYSCTLS block inserted at line 32, BEFORE the hash check). `git diff --stat 8eeb4bc72 HEAD`. HIGH

#### (1) Entrypoint hash check (integration/fly/entrypoint.sh:107-123 at 8eeb4bc; same block on main shifted +11 lines)
Probe: block extracted verbatim (`sed` from `fly_hash="${...}"` to `fly_hash=""`, 17 lines) run under `bash -c "set -eu; <block>"` with LC_ALL=C and C.UTF-8, compared with `field_core.operator_health.internal_secret_problem()` on the same value (probe at /tmp/claude-0/pm1057probe/probe.py, made-up values only: "ab"*32 etc.).
| Input | shell | field-core | value in stderr |
|---|---|---|---|
| "ab"*32 (good), blank | accept | accept | n/a |
| upper case, mixed case | REFUSE | REFUSE | no |
| 64 hex + "\n", + " ", + "\r" | REFUSE | REFUSE | no |
| leading space, surrounding ws, tab inside, space only | REFUSE | REFUSE | no |
| `sha256:` prefix, `0x` prefix | REFUSE | REFUSE | no |
| Arabic-Indic digits x64, fullwidth digits x64, fullwidth `a` x64 | REFUSE | REFUSE | no |
| sha256("") lower, sha256("") upper | REFUSE | REFUSE | no |
| 63, 65, 128 hex; `*`x64; `-n` | REFUSE | REFUSE | no |
| "0"*64 | accept | accept | n/a |
Result: 24 values x 2 locales = 48 rows, 0 drift, 0 leaks, every refusal exactly 1 stderr line. HIGH (executed).
Why it holds: the case pattern enumerates `0123456789abcdef` explicitly (no `[a-f]` range, so no locale collation effect; `[!...]` rejects any other code point incl. newline); `${#var}` length check after; empty-hash literal equals `hashlib.sha256(b"").hexdigest()` (printed by probe). Python side uses `_HEX64_RE.fullmatch` (operator_health.py:455, :524) and `[0-9a-f]` is ASCII-only (not `\d`). HIGH.
- Refusal text (line 120) interpolates only `$fly_hash_problem`, which is one of two fixed strings; value never printed. HIGH (code + probe).
- What runs before the check at 8eeb4bc: `set -eu`, `mkdir -p "$FIELD_DATA_DIR"`, `trap`, and `export` lines (lines 12-106). No service, no key file (C-5 block starts line 166). HIGH. On current main, #1069 inserted the opt-in FIELD_HARDEN_SYSCTLS block (main lines 32-41) BEFORE the check: with FIELD_HARDEN_SYSCTLS=1 and a bad hash, sysctl writes happen and >=1 extra stderr line ("harden: ... applied") precedes the refusal, so the documented "one error line" (ENVIRONMENT.md row, runbook (e)) is false under that flag, and no test covers the combination. Harmless side effects (hardening). LOW, attributable to #1069 not #1057. HIGH confidence (code read; not executed).
- Placeholder acceptance: "0"*64 (and any 64-hex placeholder) passes both checks; /health then reports `internal_secret_sha256_present: true` (operator_health.py:298) and `phase_g_check --stage 2` would read present while no preimage exists, so routes are dead (fail closed, not open). LOW. HIGH confidence.

**"A hash grants nothing" (entrypoint.sh:101) - only conditionally true.**
1. The hash is unsalted, single-round SHA-256 of the secret (operator_health.py:563-564). Anyone who reads it (any process in the container via its environ, `fly ssh console`, a crash dump/env dump of any of 13 processes) can test candidate secrets offline. HIGH (code).
2. No minimum length or entropy is enforced: `internal_secret_problem` accepts a 1-character secret; executed: hash of "x" -> None, value "x" -> None. HIGH (executed). The hash-only side cannot check entropy by construction.
3. No generation command exists in repo: no code produces FIELD_INTERNAL_SECRET (grep of *.py outside tests: only operator_health reads it), and runbook "Internal secret (G22)" (v1.2-deploy-rollback.md:2355-2380) and step (e) give no `openssl rand`/length rule. HIGH.
4. Cost, assuming ~2.2e10 SHA-256/s on one current GPU (training data, MEDIUM): 94^8 = 6.1e15 -> 2.8e5 s = 77 h; 94^10 = 5.4e19 -> 78 years; 128-bit random -> 4.9e20 years (calc shown in session). So a human-chosen or <= 8-char secret is recoverable from the hash in days; a 128-bit random one is not.
5. Precondition for exploitation: reading the hash means code exec or shell in the container; on Fly the runbook (c) says the holder is "the rotator only, by file mount in the rotator container", but Fly is one container (entrypoint.sh:2-8), so the value file, if on that machine, is likely readable by the same attacker anyway. LOW confidence (no Fly rotator design in source; not in source).
Finding F1 (MEDIUM): the claim "a hash grants nothing" is true only for a high-entropy secret, and nothing in code or runbook requires one. Condition: add a generation rule (e.g. 32 random bytes, hex) to runbook (e) and G22 section, and correct the entrypoint comment. Not a code defect in the shell check itself. Pre-existing design (compose already passes the hash to 8 services, docs/ENVIRONMENT.md row), widened by #1057 to all 13 Fly processes.

#### (2) Consumer field_core.operator_health (packages/field-core/src/field_core/operator_health.py)
- Same rule: `internal_secret_problem` (:516-539) rejects non-`^[0-9a-f]{64}$` (fullmatch) and sha256(""); the shell block reproduces exactly these two; secret-equality checks stay Python-only (needs other secrets), as the comment at entrypoint.sh:103-106 says. 48/48 agreement in probe above. HIGH.
- Drift risk: two independent implementations (shell literal pattern + hard-coded empty-hash literal vs Python regex + computed hash). The equivalence test `test_the_entrypoint_rule_is_field_cores_rule` checks Python on the same 8 values the shell is tested on (7 bad + good + blank); it does not execute the shell and Python on a shared generated corpus. If Python later ADDS a rule, the shell keeps passing and the service then raises at `install_routes` (:798-800); with the supervisor's `wait -n` (tasks/todo.md:246) the machine still goes down, just later and with a Python traceback instead of the one-line refusal. Fail closed either way. LOW. HIGH confidence.
- ENFORCE with hash blank: `internal_request_allowed` (:541-570) returns False when neither form is set and mode is ENFORCE -> both internal routes 404 (fail closed); OFF/LOG-ONLY allow with one WARNING; `/health` `internal_secret_sha256_present` false (:298), so `tools/phase_g_check.py:318-323` Stage 2 cannot read present. Belt-and-braces: even a malformed hash that slipped past start is re-checked by fullmatch at request time (:563). HIGH (code read).
- Exposure scope: compose passes the hash to 8 operator-block services; on Fly it now reaches all 13 processes, while only 8 call `operator_health.install` (ops-console, sealed-ledger, lifecycle-manager, spend-governor, agent-registry, delegation-authority, federation-broker, kill-switch: grep). 5 processes hold it with no use. Unavoidable without per-process env (C-5 style). LOW. HIGH confidence.

#### (5) In-repo callers affected
- `integration/fly/Dockerfile:60-75` copies and runs entrypoint.sh as ENTRYPOINT: every Fly boot now runs the check. HIGH.
- `.github/workflows/ci.yml:80` runs entrypoint.sh under bash with stub services (tools/tests). HIGH.
- `tools/fly_identity_check.py`, `tools/topology_lint.py` read the script (imported by test_fly_identity_c5.py:48-50); tests green, so their parse still holds. MEDIUM (inferred from passing tests, not separately run).
- `tools/phase_g_check.py:318-323` reads `internal_secret_sha256_present` from /health; behaviour unchanged, but a placeholder hash reads as present (see (1)). HIGH.
- 8 services calling `operator_health.install` (grep list in (2)) now receive the Fly value. HIGH.
- Doc drift caused by #1057: `services/lifecycle-manager/README.md:181` cites `fly/entrypoint.sh:271` for `lifecycle serve`; correct at base 5f33067 (line 271) but #1057's +27 lines moved it to 298 (309 on main after #1069). README:170 `entrypoint.sh:64` still correct at 8eeb4bc but stale on main (75) due to #1069. LOW. HIGH confidence (grep -n).

#### (4) Mutants - interim note
Pass 1 (38 mutants, runner /tmp/claude-0/pm1057probe/mutants.py, results pass1.json): 21 of the 36 "kills" were collection ERRORS (`1 error in 0.06s`), not behavioural kills: the test module's MUTANTS table calls `_mut(old, ...)` at import, which asserts `REAL.count(old) >= 1` (test_fly_identity_c5.py `_mut`), so any mutant that edits a string the table targets breaks collection. Those 21 are re-run in pass 2 with that one assert neutralised (harness only; `test_each_c5_mutant_is_caught` deselected in both passes).

#### (4) Mutants - final (38 mutants, 9 claimed behaviours, >= 4 each; worktrees pm1057, pm1057m1-3 at 8eeb4bc; `git checkout -- .` after each; oracle = the 2 PR test files with `-x`, `test_each_c5_mutant_is_caught` deselected; pass 2 rows ran with the `_mut` anchor assert neutralised)

| # | Behaviour | Mutant | Result | Killing test | Pass |
|---|---|---|---|---|---|
| 0 | B1 blank export to every process | export line removed | KILLED | test_the_stage_2_hash_is_exported_blank_to_every_process_by_default | 2 |
| 1 | B1 blank export to every process | default :-0000 | KILLED | test_absent_secrets_are_byte_identical_to_origin_main | 2 |
| 2 | B1 blank export to every process | export keyword dropped | KILLED | test_the_stage_2_hash_is_exported_blank_to_every_process_by_default | 2 |
| 3 | B1 blank export to every process | unset after check | KILLED | test_the_stage_2_hash_is_exported_blank_to_every_process_by_default | 1 |
| 4 | B2 set value passed through | value dropped to blank | KILLED | test_the_stage_2_hash_is_passed_through_to_every_process | 2 |
| 5 | B2 set value passed through | last char cut after check | KILLED | test_the_stage_2_hash_is_passed_through_to_every_process | 1 |
| 6 | B2 set value passed through | upper-cased after check | KILLED | test_the_stage_2_hash_is_passed_through_to_every_process | 1 |
| 7 | B2 set value passed through | trailing space appended when set | KILLED | test_the_stage_2_hash_is_passed_through_to_every_process | 1 |
| 8 | B3 refuse non lower-hex | ABCDEF admitted | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 9 | B3 refuse non lower-hex | a-z admitted | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 10 | B3 refuse non lower-hex | whitespace admitted | SURVIVED | - | 2 |
| 11 | B3 refuse non lower-hex | only FIRST char checked | SURVIVED | - | 2 |
| 12 | B3 refuse non lower-hex | only LAST char checked | SURVIVED | - | 2 |
| 13 | B4 refuse length != 64 | -ne -> -gt (63 accepted) | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 14 | B4 refuse length != 64 | -ne -> -lt (65 accepted) | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 15 | B4 refuse length != 64 | length check removed | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 16 | B4 refuse length != 64 | 65 also accepted | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 1 |
| 17 | B5 refuse sha256('') | literal -> zeros | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 18 | B5 refuse sha256('') | literal one char changed | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 19 | B5 refuse sha256('') | elif -> elif false | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 20 | B5 refuse sha256('') | compared to upper-case literal | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 21 | B6 one line, never the value | full value printed | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 22 | B6 one line, never the value | first 8 chars printed | SURVIVED | - | 2 |
| 23 | B6 one line, never the value | second stderr line | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 1 |
| 24 | B6 one line, never the value | exit 1 -> exit 0 | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 25 | B7 refused before anything starts | refusal in subshell | EQUIVALENT | - | 2 |
| 26 | B7 refused before anything starts | exit removed | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 2 |
| 27 | B7 refused before anything starts | key dir made before refusal | KILLED | test_absent_secrets_are_byte_identical_to_origin_main | 1 |
| 28 | B7 refused before anything starts | check reads wrong var | KILLED | test_a_malformed_stage_2_hash_stops_the_machine_with_one_line_and_no_v | 1 |
| 29 | B8 shell rule == field-core rule | py regex admits A-F | KILLED | test_the_entrypoint_rule_is_field_cores_rule[ABABABABABABABABABABABABA | 1 |
| 30 | B8 shell rule == field-core rule | py regex {63,64} | KILLED | test_the_entrypoint_rule_is_field_cores_rule[ababababababababababababa | 1 |
| 31 | B8 shell rule == field-core rule | py empty-hash check removed | KILLED | test_the_entrypoint_rule_is_field_cores_rule[e3b0c44298fc1c149afbf4c89 | 1 |
| 32 | B8 shell rule == field-core rule | py fullmatch -> match (trailing \n ok) | SURVIVED | - | 1 |
| 33 | B8 shell rule == field-core rule | py strips before check | KILLED | test_the_entrypoint_rule_is_field_cores_rule[ababababababababababababa | 1 |
| 34 | B9 docs say it | ENV row: whole-machine sentence removed | KILLED | test_the_environment_row_names_the_fly_way_and_the_malformed_value_con | 1 |
| 35 | B9 docs say it | runbook: 'does not yet' re-added | KILLED | test_the_runbook_no_longer_says_the_fly_entrypoint_does_not_pass_it | 1 |
| 36 | B9 docs say it | runbook: 'never prints the value' removed | KILLED | test_the_runbook_names_the_fly_way_and_the_malformed_value_consequence | 1 |
| 37 | B9 docs say it | ENV row: 'blank by default' removed | SURVIVED | - | 1 |

Totals per behaviour (counted from the table):

| Behaviour | Killed | Survived | Equivalent | n |
|---|---|---|---|---|
| B1 blank export to every process | 4 | 0 | 0 | 4 |
| B2 set value passed through | 4 | 0 | 0 | 4 |
| B3 refuse non lower-hex | 2 | 3 | 0 | 5 |
| B4 refuse length != 64 | 4 | 0 | 0 | 4 |
| B5 refuse sha256('') | 4 | 0 | 0 | 4 |
| B6 one line, never the value | 3 | 1 | 0 | 4 |
| B7 refused before anything starts | 3 | 0 | 1 | 4 |
| B8 shell rule == field-core rule | 4 | 1 | 0 | 5 |
| B9 docs say it | 3 | 1 | 0 | 4 |
| **All** | **31** | **6** | **1** | **38** |

Survivor analysis (each verified by the run above; HIGH unless stated):
- #10 / #11 / #12 (B3): the char-class check is only ever tested with bad values that are also the wrong length (63/65, "a space inside" and "a trailing space" are 65 chars) or bad at both first and last char ("AB"*32, "g"*64). A shell that checks only the first or last char, or admits whitespace, passes the whole suite. The merged code is correct (probe in (1)); field-core would still refuse such a value at service start (install_routes), so impact of a future regression = later, noisier failure, not an open route. LOW test gap. Missing corpus: a 64-char value with ONE interior bad char (e.g. "ab"*16 + "G" + "b" + "ab"*15), a 64-char value with an interior space.
- #22 (B6): leak check is `value.strip()` or `value[:16]` in output (problems_hash_refused); printing 8 chars of the value passes. LOW.
- #32 (B8): the equivalence test has no "64 hex + \n" case; switching Python `fullmatch` to `match` would accept it (`$` matches before a trailing newline; probe: `R.match(h+'\n')` True), and the shell/field-core agreement test would not notice. LOW.
- #37 (B9): docs test does not pin "blank by default" in the ENV row. INFO.
- #25 EQUIVALENT: under `set -eu` (entrypoint.sh:12) a refusal inside `( ... )` still aborts the script (verified: `bash -c 'set -eu; ( ...exit 1 ); echo STARTED'` -> rc=1, no STARTED).
Totals (from table): 38 mutants; 31 killed, 6 survived, 1 equivalent. Kill rate on non-equivalent = 31/37 = 83.8%.

#### Prior post-merge comment on GitHub (read only; not commented)
A post-merge comment by "don.reviewer" was posted on PR #1057 at 2026-11-21T21:11:42Z (GitHub get_comments; get_reviews returns []), verdict PASS WITH CONDITIONS, 21/21 own mutants killed. So "no review on record" in docs/reviews/2026-11-21-roadmap-audit.md section 3 is now stale for comments, still true for formal GitHub reviews. HIGH. Differences:
1. It says the PR's parametrised test "pins this on 24 values". Wrong for this repo: `test_the_entrypoint_rule_is_field_cores_rule` is parametrised on `[*BAD_HASHES.values(), GOOD_HASH, ""]` = 7 + 1 + 1 = 9 values (test_fly_identity_c5.py, BAD_HASHES has 7 keys). The 24 figure is from the PR 1056 body ("agree on 24 values"), not from code in this repo. HIGH.
2. It reports 10 first-run collection errors with "I don't know why". Cause: the module-level MUTANTS table's `_mut()` asserts its anchor string exists in the live script (see (4) interim note). HIGH.
3. Its mutant set had no partial-character-class mutants; mine shows 3 B3 survivors and the 8-char leak survivor. Its C1 (entropy) matches my F1; I rate it MEDIUM, not LOW, because the PR comment asserts the opposite ("a hash grants nothing") in the shipped script and nothing in code or runbook mitigates it.

### Findings (severity, confidence)
| ID | Severity | Finding | Source | Confidence |
|---|---|---|---|---|
| F1 | MEDIUM | "a hash grants nothing" (entrypoint.sh:101) holds only for a high-entropy secret; unsalted SHA-256, no min length (1-char secret accepted, executed), no generation rule in runbook; <= 8 random printable chars ~77 GPU-hours | (1) items 1-4 | HIGH (code/exec); GPU rate MEDIUM |
| F2 | LOW | Test corpus misses interior-bad-char 64-length values; 3 char-class mutants survive | (4) #10-12 | HIGH |
| F3 | LOW | Leak check only catches >= 16-char prefix | (4) #22 | HIGH |
| F4 | LOW | Shell/Python equivalence test lacks `hex+"\n"`; fullmatch->match drift undetected | (4) #32 | HIGH |
| F5 | LOW | Placeholder hash (e.g. "0"*64) passes and reads "present" in /health and phase_g_check while routes can never open | (1) | HIGH |
| F6 | LOW | On main, #1069's FIELD_HARDEN_SYSCTLS block runs before the hash check; with it on, the "one error line" doc claim is false; untested combination (owned by #1069) | (1), (3) | HIGH (code read, not executed) |
| F7 | LOW | lifecycle-manager README:181 line ref `fly/entrypoint.sh:271` made stale by #1057 | (5) | HIGH |
| F8 | INFO | Hash reaches 13 Fly processes, 8 use it | (2) | HIGH |

Not found (checked): no value leak in any refusal (48 probe rows + PR tests); no locale effect; unicode digits, `sha256:` prefix, whitespace, CR/LF, empty-hash in either case all refused by both rules; nothing but mkdir/trap/exports runs before the check at 8eeb4bc; ENFORCE + blank hash fails closed (404).

### Verdict on 8eeb4bc: PASS WITH CONDITIONS
ASSUMPTIONS: merge sha = PR head (fast-forward, verified); CI's install = the venv I built (same commands, Python 3.13 only, not 3.11/3.12/3.14); GPU rate ~2.2e10 SHA-256/s (training data, MEDIUM).
REASONING: (1) The shipped check is correct on every adversarial input tried, in two locales, and agrees with field-core (48/48). (2) Every failure path is fail-closed: bad shell rule -> field-core refuses at start; blank under ENFORCE -> 404. (3) Tests pass on merge and main (129/129 each). (4) Weaknesses are in test strength (6 surviving mutants) and in an unqualified security claim (F1), not in runtime behaviour. No HIGH finding -> not BLOCK; one MEDIUM -> not plain PASS.
CONCLUSION: PASS WITH CONDITIONS. Conditions (follow-up cards, none urgent before Stage 2 except C1):
- C1 (F1, before the Stage 2 go point): runbook (e) and "Internal secret (G22)" state how to generate the secret (e.g. 32 random bytes, hex) and a minimum; fix the entrypoint comment to "a hash of a high-entropy secret grants nothing". Optionally a length floor in `internal_secret_problem` for the value form.
- C2 (F2-F4): add to BAD_HASHES a 64-char value with one interior upper-case char, one with an interior space, and `"ab"*32 + "\n"`; run the shell and Python rules over the SAME corpus; tighten the leak check to any 8-char window of the value.
- C3 (F5-F7): reject or warn on an all-zero hash; resolve the FIELD_HARDEN_SYSCTLS/one-line wording on main; fix README line refs (or drop line numbers).
Overall confidence in verdict: HIGH for correctness of the merged check; MEDIUM for the brute-force cost estimate.
Artifacts: /tmp/claude-0/pm1057probe/{probe.py,mutants.py,mutants2.py,pass1.json,mutants2.json,table.md}.

### #1073 post-merge (roley.reviewer, e143038)

_Merge sha e143038e0bd35d1842d76d3babd8fdfaaed5fcb3 (squash, parent 750824b8). Source: `git log origin/main --grep='#1073'`. Files: README.md, engine.py, test_f2_fail_closed.py, test_verdict_no_token_echo.py (+105/-4)._

**Tests (merge e143038, venv /tmp/claude-0/venv1073, Python 3.13.18, CI install steps from .github/workflows/ci.yml L30-50):**
- PR tests `test_verdict_no_token_echo.py test_f2_fail_closed.py`: `19 passed, 1 warning in 2.56s`
- Full suite `cd services/conformance-sentinel && python -m pytest -q tests`: `412 passed, 1 warning in 46.13s`

**Dynamic leak probe (in-process stack from tests/conftest.py, fake/minted ids; probe file tests/test_zz_probe_pm1073.py in worktree only, deleted at end).** Searched response body, headers, captured logs (DEBUG, all loggers) and sentinel-written ledger rows (`conformance.*`, `sentinel.*` in events.jsonl) for: full id, first 8, last 8, sha256 hex, sha256[:12].

| Path | Status | Full/prefix/suffix/sha64 found | token_ref (sha256[:12]) |
|---|---|---|---|
| ALLOW | 200 | none | body (by design) |
| BLOCK D.scope | 200 | none | body |
| ESCALATE E.escalation_trigger | 200 | none | body |
| D.revoked | 200 | none from /check (a log hit came from the probe's own `POST /tokens/{id}/revoke` URL, delegation-authority side) | body |
| D.expired | 200 | none | body |
| unknown fake id (D.revoked fail-closed) | 200 | none | body |
| LOG_ONLY shadow | 200 | none | body |
| L.unreachable step 1 | 200 | none | body |
| F2 failed allow append | 200 | none | body |
| delegation unreachable | 200 | none | body |
| 11 x 422 variants (missing field, wrong types, dict key, extra field named by id, invalid JSON, list body) | 422 | none (field_core.http_errors redaction, api.py L66) | none |
| 5xx (registry raises msg containing id) | 500 | none (`Internal Server Error`) | none |
| lone-surrogate token_id (ENFORCE and LOG_ONLY) | 500 | none | none |
| caller puts id in `context.source` | 200 | **ledger** (caller_context allow-list) | body |

Pre-PR control (parent 750824b8 engine.py): ALLOW and L.unreachable bodies contained full/prefix/suffix -> fix confirmed effective (HIGH, probe output).

**Relays (static read, merge sha):**
- force-gateway `_authorize` (services/force-gateway/src/force_gateway/api.py L552-588) copies only decision, clause_id, reasons, agent_id, action, retry_after_seconds into its 403 body; `gateway.shadowed` ledgers only `would_be`. `SentinelClient.check` (L359-376) error text carries status code / exception type, not the request body. Never relayed `context.token_id` even pre-PR. HIGH.
- claude-approver `_check` (services/claude-approver/src/claude_approver/core.py L448-505) relays decision, clause, joined reasons, shadowed. No context relay. HIGH.
- ops-console `/api/check` (services/ops-console/src/ops_console/api.py L866-870) proxies the sentinel verdict VERBATIM: it was the one in-repo relay that carried the full id pre-PR; it now carries token_ref. Its 422 is redacted (install_validation_handler, L435). HIGH.
- Scorecard (measure.py L110-122) reads only `decision`, `context.would_be`, `context.shadowed`; cli.py L181-187 posts token_id but never prints the verdict context. No leak. HIGH.
- No in-repo code reads `verdict.context.token_id` (`git grep` over src, plugins, integration: only hit is the new test's docstring). Affected in-repo callers: ops-console `/api/check` (output shape change: `token_id` -> `token_ref`,`token_presented`), sentinel CLI `check` (prints verdict), field-agent `field_client.py` L197 / `governed.py` L103 (send token_id, read decision only), force-gateway, claude-approver, integration/demo/fixtures/upgrade-smoke/upgrade_flow.py L175-182, plugins/field-agent/templates/rest_api.sh L23. None break. MEDIUM-HIGH (static grep; external consumers unknown).

**Mutation testing (engine.py only, worktree /tmp/claude-0/pm1073, `git checkout -- .` after each; runner asserts a clean tree at the end). Suite for kill/survive = PR tests (`test_verdict_no_token_echo.py`, `test_f2_fail_closed.py`); every survivor was re-run against the full `tests/` dir (438 = 412 + 26 probe tests) and still survived.**

| # | Behaviour claimed | Mutant | Result |
|---|---|---|---|
| M01 | B1 verdict has no id | re-add `token_id` to main context | KILLED |
| M02 | B1 | add `id[-8:]` to main context | **SURVIVED** |
| M03 | B1 | add `id[:8]` to main context | **SURVIVED** |
| M04 | B1 | ALLOW reason names the id | KILLED |
| M05 | B1 (ledger rows) | add `token_id` to sentinel ledger payload | **SURVIVED** |
| M06 | B1 | add `len(id)` to main context | **SURVIVED** |
| M07 | B2 log-only shadow | re-add `token_id` to shadow ctx | KILLED |
| M08 | B2 | shadow reason names the id | KILLED |
| M09 | B2 | shadow `token_ref` = raw id | KILLED |
| M10 | B2 | shadow `token_ref` = `id[:12]` | KILLED |
| M11 | B3 F2 BLOCK | re-add `token_id` to F2 ctx | KILLED |
| M12 | B3 | F2 reason names the id | KILLED |
| M13 | B3 | F2 ctx drops `_token_context` | KILLED |
| M14 | B3 | F2 `token_ref` = `id[-12:]` | KILLED |
| M15 | B4 ref = sha256[:12] | `[:12]` -> `[:16]` | KILLED |
| M16 | B4 | sha256 -> md5 | KILLED |
| M17 | B4 | first 12 -> last 12 hex | KILLED |
| M18 | B4 | salted hash | KILLED |
| M19 | B5 presented / no token | `token_presented` always True | KILLED |
| M20 | B5 | no-token ref `''` not None | KILLED |
| M21 | B5 | `presented = token_id is not None` (`""` counts as presented) | **SURVIVED** |
| M22 | B5 | no-token ref = sha256('')[:12] | KILLED |
| M23 | B6 forged/inactive id | inactive reason names the id | KILLED |
| M24 | B6 | inactive path `extra_context={"token_id": id}` | KILLED |
| M25 | B6 | delegation-unreachable reason names the id | **SURVIVED** |
| M26 | B6 | inactive reason names `id[:8]` | **SURVIVED** |

Totals (counted from the table): 26 mutants, 19 KILLED, 7 SURVIVED (M02, M03, M05, M06, M21, M25, M26). Per behaviour: B1 2/6 killed, B2 4/4, B3 4/4, B4 4/4, B5 3/4, B6 2/4.
Cause: `_assert_clean` checks only `token not in r.text` (full-string match) and `"token_id" not in ctx`; no test checks prefixes/suffixes/length, the ledger rows, or the delegation-unreachable path (test_verdict_no_token_echo.py L27-31, L79-86). The code at the merge sha does not leak in any of these (probe above); the gap is regression protection only.

**Other suites on the merge sha (callers/relays):** force-gateway `573 passed`, claude-approver `387 passed`, ops-console `471 passed`, field-agent `453 passed` (each `python -m pytest -q tests`, 1 warning each). HIGH.

#### Objections (FORCE [O])
1. Tests pin full-string absence only; a partial echo (prefix, suffix, length) or a ledger-row echo would merge green (M02/M03/M05/M06/M26 survive).
2. Two paths still copy upstream text into `reasons` without filtering: `token inactive: {intro.get('reason')}` (engine.py L563) and `delegation-authority unreachable: {exc}` (L554). Today neither contains the id (probe rows D.revoked/unknown/delegation-unreachable). If delegation-authority ever puts the id in `reason`, the sentinel would echo it again.
3. `token_ref` is unsalted and deterministic. Anyone who holds the token list (delegation `/tokens`, ops-console) can map a ref back to its token. By design (README L192-193), and not a credential: uuid4 has 122 random bits (field_core/delegation.py L26), so the 48-bit ref cannot be reversed by brute force.
4. A lone-surrogate `token_id` returns 500. Pre-PR it also returned 500 (crash during response encoding, parent 750824b8). Post-PR it crashes earlier, in `_token_context`, at engine.py L63. The probe showed no leak. ENFORCE fails closed; in LOG_ONLY the caller gets a 5xx and no shadow ALLOW. force-gateway refuses with 503 (`SentinelUnavailable`, api.py L367-368). claude-approver denies (core.py L478-481).

#### Findings
| ID | Sev | Finding | Source | Conf |
|---|---|---|---|---|
| F1 | MEDIUM (test gap, no live leak) | 7/26 mutants survive the full suite. Partial, length and ledger echoes are unpinned | mutant table above; test_verdict_no_token_echo.py L27-31 | HIGH |
| F2 | LOW | Upstream `reason` and exception text go into `reasons` unbounded and unfiltered (L554, L563). Defence in depth: strip `req.token_id` from relayed text, or relay `token_status` only | engine.py L549-564 | HIGH (code), LOW (exploitability today) |
| F3 | LOW (pre-existing) | Lone-surrogate `token_id` returns 500 before and after the PR. The PR adds a new crash site at L63. Fix with `encode("utf-8","surrogatepass")` or a validator | probe rows; traceback engine.py L552->L267->L63 | HIGH |
| F4 | INFO | Caller-supplied `context.source` etc. reaches the ledger (caller_context allow-list), so a caller can put an id there itself. Caller misuse, not an echo | ledger_context.py L25-64; probe row | HIGH |
| N1 | MEDIUM (NEW, out of #1073 scope) | incident-replay `/replay` JSON returns the full `token_id` of every AuthorityGrant. Its markdown prints `id[:8]…`. A post-mortem is a quoted report, the same class as #1072 | incident_replay/engine.py L197-205, L464-465, L593, L641; api.py L44 | HIGH (code read; not run) |
| N2 | INFO (by design, out of scope) | delegation-authority `/introspect` echoes `token_id` (IntrospectionResult.token_id). The caller is the authority's own client, and the sentinel drops the field. `/tokens/{id}/revoke` puts the id in the URL path, so it reaches access logs | delegation_authority/api.py L446-467; field_core/delegation.py L80 | HIGH |
| N3 | INFO (out of scope) | ops-console lists full ids from delegation `/tokens` (operator surface). Its revoke route has the id in the path. `/api/check` now relays only token_ref | ops_console/api.py L549, L617, L855-870 | HIGH |
| N4 | INFO (out of scope) | lifecycle-manager ledgers `token_id` in its expiry finding payload | lifecycle_manager/engine.py L637 | MEDIUM (not run) |

#### Verdict: **PASS WITH CONDITIONS** on e143038
ASSUMPTIONS: in-process TestClient stack is representative of the deployed wiring (same create_app, field_core handlers); external (out-of-repo) consumers of `context.token_id` are unknown.
REASONING: (1) The id, its prefix, suffix and sha64 are absent from the body, headers, logs and sentinel ledger rows on all 10 decision paths, 11 x 422 and both 5xx paths. The pre-PR control leaked. (2) No relay copies `context`, except ops-console, which now carries only token_ref. (3) All caller suites pass. (4) The regression guard is weak (F1).
CONCLUSION: the fix works and nothing needs reverting. Conditions, as follow-up and not blocking: (a) extend `_assert_clean` to check `id[:8]`, `id[-8:]`, the sentinel ledger rows and the delegation-unreachable path, then re-run M02/M03/M05/M25/M26; (b) F2 sanitise; (c) open a separate issue for N1. Confidence: HIGH for the no-leak result at the merge sha, MEDIUM for completeness beyond the paths enumerated.

Worktree /tmp/claude-0/pm1073 removed after the review; probe file never committed. No GitHub comments, pushes or deployed-service requests.

### #1078 post-merge (roley.reviewer, cb7a94f)

Status: COMPLETE (see end)

#### Corrections to the brief
- C1. #1077 is not "prior cache work on main": `gh api repos/SpinStateLabs/field-platform/pulls/1077` -> "sealed-ledger: parse each segment's bytes once per change, not once per read (T6-B) | closed | merged=false". Prior merged work is #1075 (95cd9647, T6 harness, no fix) and #1076 (787de47d, T7 parse+verify cache). HIGH.
- C2. Merge sha confirmed: `git log origin/main --grep='#1078'` -> cb7a94f8dcc64489cde69ba87b9b7267001eaaa7; REST merged_at=2026-11-21T02:44:47Z; `/pulls/1078/reviews` length 0. HIGH.
- C3. docs/reviews/2026-11-21-roadmap-audit.md does not exist at cb7a94f (added later on main); on origin/main its section (3) line 453 lists #1078 review "none". HIGH.

#### Suite on cb7a94f (CI command)
- `pytest -q packages/field-core/tests services/sealed-ledger/tests` (venv /tmp/claude-0/venv1078, Python 3.13.18, ci.yml:34-50 install incl. constraints) -> last line `3334 passed, 6 skipped, 2 warnings in 130.56s (0:02:10)`; exit 0; wall 133 s. Log: /tmp/claude-0/reports/pm1078-suite.log. HIGH.

#### Attack cases (executable: /tmp/claude-0/pm1078-attacks/test_attack_1078.py, 20 cases; 18 pass = safe, 2 fail = finding)
Run: `python -m pytest -q test_attack_1078.py` -> `2 failed, 18 passed`. Each case asserts store.verify() == uncached Snapshot.verify() == fresh LedgerStore(p).verify(), and ok=False when damaged.
| # | Vector | Result | Conf |
|---|---|---|---|
| A1a | warm cache -> archive (test helper) -> flip byte in archive copy | ok=False, == uncached == fresh. SAFE | HIGH |
| A1b | warm -> real `archive_closed_segments` (retention apply) -> flip byte in retention event | ok=False. SAFE | HIGH |
| A1c | retention-evidenced segment, archive copy deleted | ok=True cached AND uncached: design (store.py:1287-1292 skips the copy when a live retention event names n+sha256), not a cache defect. INFO | HIGH |
| A2 | warm -> rotate -> warm -> same-size flip in newly closed segment | ok=False. SAFE | HIGH |
| A3 x5 | closed segment: same size+same mtime (os.utime restored), same size new mtime, last line truncated, line duplicated, file deleted | all ok=False, == uncached. SAFE (key is full bytes, store.py:1776-1777, never stat) | HIGH |
| A4a | 4 verify threads vs archive then unlink of copy; any call STARTED after damage that says ok=True | 0 such calls. SAFE | MEDIUM (timing-based) |
| A4b | 4 verify threads vs same-size tamper of unarchived closed seg | 0. SAFE | MEDIUM |
| A5a | same bytes, new inode | cache hit, == uncached. Correct | HIGH |
| A5b | journal `archived_to` re-pointed to attacker dir with forged empty copy | ok=False (journal bytes are in Layout key via JournalState.raw, store.py:757-758; archived bypass). SAFE | HIGH |
| A5c | in-process caller mutates a LedgerEvent returned by `store.events()`, then an append | **FAIL**: cached verify ok=False "segment 3: hash mismatch at index 10 ... (record was mutated)" while fresh store ok=True. T7 parse cache shares LedgerEvent objects (store.py:1727-1737 `list(events)` copies the list, not the models; LedgerEvent is not frozen, field_core/ledger.py:61-62). Fail-closed (false break, never false ok shown). Not reachable over HTTP (responses are serialized); no in-repo mutator found (grep of sealed_ledger/src). LOW | HIGH (repro) |
| A6 | restart after same-size tamper | ok=False. SAFE (cache is in-memory only, store.py:1535-1538) | HIGH |
| A7 | second writer PROCESS appends 3, then same-size tamper of its line | ok=False, == uncached. SAFE | HIGH |
| A8 | GET /events unfiltered + filtered, then /verify; tamper; filtered /events re-warms parse cache with tampered bytes; then unparseable tamper | /verify ok=False, reason == uncached. SAFE | HIGH |
| A9 | /health after same-size in-place edit of open segment's last hash | **FAIL**: /health keeps serving the old head_hash (and `ok: true`) while /verify ok=False. Cause: health_info keys on (size, inode) of open file + journal size (store.py:1594-1604, 1982-1992). Pre-existing (not #1078, not the verify cache); `ok` is hard-coded liveness (api.py:371). estate_probe compares /health head against /events (tools/estate_probe.py:444-450) so it would flag the mismatch. LOW | HIGH (repro) |
| C1 | open-segment tail truncated by one line | ok=True cached AND uncached, length 10. Inherent to a hash chain with no anchor check in /verify; not #1078 | HIGH |
| C2 | last open event rewritten with recomputed hash | ok=True cached AND uncached. Inherent (Snapshot.verify, store.py:1136-1236, checks no signature/anchor); not #1078 | HIGH |

Core question answer: no case found where the CACHE makes /verify say ok=True for a chain an uncached verification calls broken. /verify does say ok=True for a truncated or re-hashed open-segment tail, and for a deleted retention-evidenced archive copy, with or without the cache.

#### Mutants (worktree only, `git checkout -- .` after each; runner /tmp/claude-0/pm1078-attacks/mutate.py, raw /tmp/claude-0/reports/pm1078-mutants.json)
ATK = attack file with the 2 baseline-failing cases (A5c, A9) deselected (baseline `18 passed, 2 deselected`). Full = whole sealed-ledger suite, run only where T7+T8 left the mutant alive.
| Behaviour | Mutant | T8 file | T7 file | Full suite | ATK |
|---|---|---|---|---|---|
| B1 archived bypass | M1.1 guard deleted | KILL (2 failed, 5 passed) | live (11 passed) | n/a (killed by T7/T8) | KILL (2 failed, 16 passed) |
| B1 archived bypass | M1.2 guard `and False` | KILL (2 failed, 5 passed) | live (11 passed) | n/a (killed by T7/T8) | KILL (2 failed, 16 passed) |
| B1 archived bypass | M1.3 bypass only when >1 archived | KILL (2 failed, 5 passed) | live (11 passed) | n/a (killed by T7/T8) | KILL (2 failed, 16 passed) |
| B1 archived bypass | M1.4 inverted (`not archived`) | KILL (3 failed, 4 passed) | KILL (1 failed, 10 passed) | n/a (killed by T7/T8) | KILL (2 failed, 16 passed) |
| B1 archived bypass | M1.5 keyed on pending instead | KILL (2 failed, 5 passed) | live (11 passed) | n/a (killed by T7/T8) | KILL (2 failed, 16 passed) |
| B2 bytes in key | M2.1 bytes compare dropped | live (7 passed) | KILL (2 failed, 9 passed) | n/a (killed by T7/T8) | KILL (10 failed, 8 passed) |
| B2 bytes in key | M2.2 sizes only (stat-like) | live (7 passed) | KILL (1 failed, 10 passed) | n/a (killed by T7/T8) | KILL (5 failed, 13 passed) |
| B2 bytes in key | M2.3 all->any | live (7 passed) | live (11 passed) | KILL (5 failed: concurrency/stress tests, e.g. test_ledger_readers.py::test_readers_during_rotate_and_archive_never_see_a_short_ok_chain) | KILL (10 failed, 8 passed) |
| B2 bytes in key | M2.4 open segment only | live (7 passed) | live (11 passed) | **SURVIVES** (`1078 passed, 5 skipped` in 115.69s) | KILL (7 failed, 11 passed) |
| B2 reuse kept | M2.5 never stores (no reuse) | KILL (1 failed, 6 passed) | KILL (1 failed, 10 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B3 layout in key | M3.1 layout compare dropped | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B3 layout in key | M3.2 watch only | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B3 layout in key | M3.3 seg count only | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B3 layout in key | M3.4 seg paths only | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B4 newline guard | M4.1 guard removed | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B4 newline guard | M4.2 guard `or True` | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B4 newline guard | M4.3 endswith '}' instead | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |
| B4 newline guard | M4.4 strip before check | KILL (1 failed, 6 passed) | live (11 passed) | n/a (killed by T7/T8) | live (18 passed) |

Totals (counted from the table): 18 mutants across 4 behaviours (B1 5, B2 5, B3 4, B4 4). Killed by in-repo tests: 17/18. Killed by ATK: 9/18. Killed by either: 18/18. Survivor of the in-repo suite: M2.4.

#### Findings (severity, confidence)
1. MEDIUM (test gap, HIGH conf). No in-repo test pins CLOSED-segment bytes in the /verify cache key. Mutant M2.4 (`zip(cached[1][-1:], snap.raw[-1:])` at store.py:1777: only the open segment's bytes compared) passes all 1078 sealed-ledger tests; under it a same-size edit of a closed segment of an unarchived rotated ledger is answered ok=True from the cache. The merged code is correct (A3 x5 pass); the regression guard is missing. T7's same-size test is open-segment only (tests/test_ledger_head_cache_t7.py:128-150) and its rotation test never tampers a closed segment (:206-217). Fix: add A3 (warm, same-size flip in seg 2 with mtime restored, assert == uncached and ok=False).
2. LOW (HIGH conf, repro A5c). T7 parse cache shares mutable LedgerEvent instances across callers (store.py:1728, 1737 copy the list only; field_core/ledger.py:61-62 model not frozen). An in-process caller mutating an event from `store.events()` makes the next recomputed verify report a false break (fresh store ok=True). Fail-closed; HTTP callers unaffected (serialized responses); no in-repo mutator found. `test_each_reader_gets_its_own_list` (t7:188-192) tests list isolation only. Fix: freeze LedgerEvent in the cache (model_copy on hand-out, or frozen model) or document.
3. LOW, pre-existing, not #1078 (HIGH conf, repro A9). /health `head_hash`/`event_count` are keyed on (size, inode) of the open file + journal size (store.py:1594-1604, 1982-1992); a same-size in-place edit leaves /health serving the old head while /verify says ok=False. `ok` on /health is constant liveness (api.py:371), never integrity. /health does not touch the verify cache at all, so the brief's "/health still reporting from the cache" is only true of this stat-keyed health cache.
4. INFO (HIGH conf, C1/C2/A1c). /verify answers ok=True, cached or not, for: a truncated open-segment tail; a re-hashed rewrite of the open tail; a deleted archive copy whose segment+sha256 a live retention event names (store.py:1287-1292, by design). None is a cache defect; they bound what "ok" means for every caller below.
5. LOW perf (MEDIUM conf, inferred from store.py:1772-1773). Once any segment is archived (the steady state after the first retention apply) the verify-result cache is never used, so every /verify re-hashes all live events (the parse cache still applies). This reverses part of the T6/T7 latency win on archived ledgers; not measured here.

#### Claims in the #1078 commit message, checked
- "archive-copy byte flip and unlink ... fail before this change": M1.1 (guard deleted = pre-change) -> T8 `2 failed, 5 passed`. CONFIRMED, HIGH.
- "journal head_hash edit ... kills a key-on-segment-bytes-only mutant": M3.1 killed by T8 only. CONFIRMED, HIGH.
- "newline guard ... kills the guard-removed mutant": M4.1 killed by T8 only. CONFIRMED, HIGH.
- "The only reads outside the key are in _verify_archived ... so the bypass is complete": Snapshot.verify (store.py:1136-1236) reads files only via `_verify_archived` (read_shared at :1293), which returns None when nothing is archived (:1282-1283). CONFIRMED by reading, MEDIUM-HIGH.
- Diff touches only store.py `_verified` docstring + 2-line guard, README, and the new test file (`git show --stat cb7a94f8`: 3 files, +147/-2). No API shape change. HIGH.

#### In-repo /verify callers affected (all over HTTP; none use LedgerStore in-process)
- attestation-reporter: src/attestation_reporter/engine.py:445-461 (GET /verify + /health; INTACT/BROKEN from `ok`).
- incident-replay: src/incident_replay/engine.py:125 (/verify), :130 (/health), :404 (`integrity_ok = bool(verification.get("ok"))`).
- tools/estate_probe.py:435-450 (/health then /events then /verify; cross-checks /health head against /events, so finding 3 would surface as an inconsistency).
- ops-console: src/ops_console/api.py:551 (`ledger_verify=_section(app.state.ledger, "/verify", "verify")`).
Effect of #1078 on them: on archived ledgers, a fresh verification every call (correct, possibly slower); unchanged otherwise. HIGH.

#### Verdict on cb7a94f: PASS WITH CONDITIONS
No executable case made the cache produce ok=True where an uncached verification says broken (20 attack cases; 18 safe, 2 failures are findings 2 and 3, neither a false ok). Conditions: (1) add the closed-segment same-size test (kills M2.4) before more T-series cache work lands; (2) decide on finding 2 (freeze or copy events handed out of the parse cache). Follow-up, not blocking: document /health's non-integrity semantics (finding 3) and measure finding 5.

Status: COMPLETE. Worktree /tmp/claude-0/pm1078 removed after the review; attack file and mutant runner kept at /tmp/claude-0/pm1078-attacks/.

### (4b) Post-merge reviews, batch 2 (roley.reviewer, 2026-11-22)

#### Ordering trade-off recorded at the controller's request (from the #1057 review)
In integration/fly/entrypoint.sh the FIELD_HARDEN_SYSCTLS block (#1069, around lines 35-41) runs BEFORE the FIELD_INTERNAL_SECRET_SHA256 validation (#1057, around lines 118-133). The #1057 review proposed validating first, so that a refusing boot prints one error line. The controller rejected that change on 2026-11-21: the G22 delta review relies on the harden block running on EVERY boot, including a boot that then refuses, so the sysctls are always applied. Accepted cost: when FIELD_HARDEN_SYSCTLS=1, a refusing boot prints the harden lines before the refusal line, so the "one error line" wording in the entrypoint comment is not literally true. The #1087 second verdict noted the same ordering (mkdir and the sysctl writes run before the secret check; no service starts and no key is written first).

### #1069 post-merge (roley.reviewer, 6bc2c80)

Status: COMPLETE.

Merge sha: 6bc2c80fafa6930ad5d45d2e2bb8e8972df9ed7c (squash; `git log origin/main -S FIELD_HARDEN_SYSCTLS -- integration/fly/entrypoint.sh`). PR head 53b88e03c, base 123b71b50, merged 2026-11-13T19:21:56Z (GitHub MCP pull_request_read get). HIGH
Worktree: /tmp/claude-0/pm1069 (detached at merge sha). Docker: NOT available on this host (`docker version` -> "failed to connect to the docker API at unix:///var/run/docker.sock"). Image NOT built; Dockerfile analysed statically, plus CI evidence. HIGH

## Corrections to the brief
- C1: there is no explicit "zero setuid files" assertion in CI. `.github/workflows/ci.yml:244-` (fly-image-smoke) only runs `docker build` + health/flow steps; `grep -n 'perm /6000\|setuid' .github/workflows/ci.yml` returns nothing. The zero-setuid guarantee is the Dockerfile's own `test -z` RUN (integration/fly/Dockerfile:72), which fly-image-smoke executes by building. fly-image-smoke concluded success on the PR head 53b88e03c (GitHub MCP get_check_runs, run 43487470455). So: asserted at build time on CI, indirectly; not asserted on the running container. HIGH
- C2: the "#1057 review flagged" ordering item is LOW (F6 in /tmp/claude-0/reports/POSTMERGE-PR1057.md:137), attributed to #1069; it is a doc-claim ("one error line") issue, not a security issue. HIGH

## Tests (venv /tmp/claude-0/venv1069, Python 3.13.18, installs per .github/workflows/ci.yml:30-50)
- Merge sha 6bc2c80: `pytest -q tools/tests/test_fly_image_hardening.py` -> `5 passed in 0.08s`; with test_topology_lint.py + test_fly_identity_c5.py -> `416 passed in 205.56s (0:03:25)`; `python tools/topology_lint.py` -> `RESULT: OK (0 finding(s), 4 allowlisted)`. HIGH
- origin/main d2cfab30c: `pytest -q tools/tests/test_fly_image_hardening.py` -> `6 passed in 0.07s` (+1 test from #1071 for the GB10 mirror); topology lint -> `RESULT: OK (0 finding(s), 4 allowlisted)`. HIGH
- PR head 53b88e03c and merge sha have identical trees (`git diff --stat 53b88e03c 6bc2c80fa` empty), so CI on the head (all 7 checks success) applies to the merge. HIGH

## Empirical: entrypoint block (lines 35-41 copied, /proc/sys replaced by a scratch dir; host sysctls not touched)
- Parsing: only the exact string `1` arms it. `"1 "`, `" 1"`, `true`, `yes`, `01`, `TRUE`, empty, unset -> block skipped, NO log line at all. HIGH (executed)
- Refused writes: with a non-existent target dir, bash prints its own redirection error (`...: No such file or directory`) BEFORE the `2>/dev/null` takes effect (redirections apply left to right), then the "refused" line; so 8 lines for 4 refusals, and the final "FIELD_HARDEN_SYSCTLS=1 applied" line is printed anyway; script continues (rc 0, next line reached) under `set -eu`. HIGH (executed)
- Non-fatal is the documented intent: entrypoint.sh:32-33 ("each refused write is logged and the estate still starts"), integration/fly/README.md:105-106, PR body. HIGH

## (1) Dockerfile setuid/setgid strip (integration/fly/Dockerfile:63-72, merge sha; unchanged on main)
- Placement: after the strip (lines 70-72) only ENV/EXPOSE/ARG/ENV/ENTRYPOINT follow (lines 74-86); no later COPY/RUN/ADD. Correct on merge sha and main. HIGH (file read)
- Build-time enforcement: `test -z "$(find / -xdev -type f -perm /6000)"` fails the build; CI fly-image-smoke builds this Dockerfile and passed on the head (identical tree). HIGH. Not re-run here (no docker).
- Filesystems: `-xdev` limits to the image root fs. At build time that is the whole image (BuildKit's /etc/hosts, resolv.conf bind mounts are skipped, harmless). The runtime /data volume is not covered; every process is root, so root could set setuid there anyway. LOW impact. MEDIUM confidence (general knowledge of BuildKit mounts).
- File capabilities: NOT covered. `chmod a-s` does not touch security.capability xattrs and there is no getcap/xattr check. Concrete case: upstream caddy alpine image runs `setcap cap_net_bind_service=+p /usr/bin/caddy` (web: raw caddy-docker master/2.11/alpine/Dockerfile:39); Dockerfile:58 copies that binary with `COPY --from`. Whether the pinned 2026-10-28 digest carries it and whether COPY --from keeps the xattr: not verified (no docker). Impact today nil (all root, cap is bind-low-ports only); matters once non-root agent uids exist. LOW severity, MEDIUM confidence that a cap-bearing file is in the image.
- ff-harden is not setuid: `chmod 0755` (line 70) then the strip runs after it in the same RUN; it is also a `#!/bin/sh` script, and Linux ignores setuid on scripts. HIGH
- No runtime assertion: fly-image-smoke never runs `find -perm /6000` inside the started container, so a setuid file added AFTER the strip (see survivors below) would pass both the build and CI. LOW (needs a reviewer to miss a post-strip COPY). HIGH confidence (ci.yml:244-300 read; grep).

## (2) FIELD_HARDEN_SYSCTLS block (integration/fly/entrypoint.sh:32-41, same lines on main)
- F-1 MEDIUM, HIGH confidence: the operator documentation describes a mechanism that does not exist. integration/fly/README.md:104-107: "The entrypoint runs it [ff-harden] only when FIELD_HARDEN_SYSCTLS=1 ... After arming, the boot log must show four `ff-harden: ok` lines." The entrypoint does NOT run ff-harden (entrypoint.sh:35-41: four `echo >` writes, no launch; the test pins "no new launch", test_fly_image_hardening.py:76-77). The boot log will never show `ff-harden: ok`. tools/ff-harden.sh:9 repeats the stale claim ("Called by entrypoint.sh ONLY when ..."). Left over from review-fix commit 2 (commit message: "entrypoint: no new launch"). An operator following the README's arming check gets a false negative; one skimming the log sees "applied".
- F-2 LOW-MEDIUM, HIGH confidence (executed): entrypoint.sh:40 prints "FIELD_HARDEN_SYSCTLS=1 applied" unconditionally, even when all four writes were refused, and `2>/dev/null` does not suppress bash's own redirection error (8 lines for 4 refusals). The log overstates the security state. Fix: count refusals and print "applied 4/4" or "PARTIAL n/4".
- F-3 LOW, HIGH confidence (executed): only the literal `1` arms it. `true`, `yes`, `"1 "`, `01` arm nothing and print nothing. This fails toward OFF (safe for availability) but silently leaves a security control unarmed. Suggest: warn on any non-empty value other than 0/1.
- Non-fatal by design: confirmed and documented (entrypoint.sh:33, README:105-106). Correct choice for a hardening knob on a platform that may refuse sysctls. HIGH
- Ordering vs secret checks: confirmed. The harden block is at lines 35-41; the Stage 2 hash refusal is at 118-132 (`exit 1` at 132) and the identity refusals at ~180-197 (merge sha and main identical). Effect with the flag on and a bad secret: the sysctl writes happen first (VM-local, idempotent, harmless, and the machine stops anyway), and 1 to 9 extra stderr lines precede the refusal, so the "one error line" claim noted in the #1057 review (F6) is false under the flag. No security impact. Note: the test PINS the block before `FIELD_REGISTRY_URL` (test_fly_image_hardening.py:78), so moving it after the checks needs a test edit too. LOW. HIGH confidence (code read).
- max_user_namespaces=0: nothing in the image needs user namespaces. The image copies only packages/, services/, constraints, tools/volume_admin.py, tools/estate_probe.py and caddy (Dockerfile:23-60). The repo-wide grep for bwrap/unshare/CLONE_NEWUSER/chromium/playwright finds only integration/video/capture_scene3.py (Playwright), which is not in the image. HIGH. Fly's own `fly ssh console` and `machine exec` working with the setting on is PR-body evidence only, not reproduced. MEDIUM.
- ff-harden (tools/ff-harden.sh): it writes and reads back each value, prints ok/FAIL, and exits 1 on any FAIL. The DRY_RUN path only reads. I ran a dry run here: rc 0, 4 lines, no writes. HIGH. Its failure path (refused write -> rc=1) is untested (see mutants B3).

## (4) Mutants (worktree /tmp/claude-0/pm1069 only; `git checkout -- .` after each; `git status --porcelain` empty at end)
Oracle: `pytest -q tools/tests/test_fly_image_hardening.py` (the PR's test file). Script: scratchpad h1069/mut.py.

| # | Behaviour | Mutant | Result | Last line |
|---|---|---|---|---|
| 1 | B1 strip last + build fails | COPY binary after strip | KILLED | 1 failed, 4 passed |
| 2 | B1 | lowercase `copy` after strip (Dockerfile keywords are case-insensitive) | SURVIVED | 5 passed |
| 3 | B1 | COPY after strip whose line contains "ff-harden" | SURVIVED | 5 passed |
| 4 | B1 | RUN chmod u+s after strip | KILLED | 1 failed, 4 passed |
| 5 | B1 | check narrowed to -perm /4000 | KILLED | 1 failed, 4 passed |
| 6 | B1 | check neutralised with `|| true` | KILLED | 1 failed, 4 passed |
| 7 | B1 | strip narrowed to -perm /4000 | KILLED | 1 failed, 4 passed |
| 8 | B1 | indented `  COPY` after strip | SURVIVED | 5 passed |
| 9 | B2 lint admits exactly the strip | find literal widened to `find / -xdev[^;|&`]*` | KILLED | 1 failed, 4 passed |
| 10 | B2 | test literal widened to `test -z "$(.*)"` | KILLED | 1 failed, 4 passed |
| 11 | B2 | test literal dropped | KILLED | 1 failed, 4 passed |
| 12 | B2 | fullmatch -> match | KILLED | 1 failed, 4 passed |
| 13 | B2 | find widened to `find / .*` | KILLED | 1 failed, 4 passed |
| 14 | B3 ff-harden sets + reads back | max_user_namespaces 0 -> 1 | KILLED | 2 failed, 3 passed |
| 15 | B3 | read-back neutralised (`|| true`) | SURVIVED | 5 passed |
| 16 | B3 | write-refused branch sets rc=0 | SURVIVED | 5 passed |
| 17 | B3 | `exit $rc` -> `exit 0` (old text kept in comment) | SURVIVED | 5 passed |
| 18 | B3 | one setting dropped | KILLED | 3 failed, 2 passed |
| 19 | B3 | dry-run message changed | KILLED | 1 failed, 4 passed |
| 20 | B4 entrypoint gate/non-fatal/match/after trap | gate `= 1` -> `!= 0` | KILLED | 1 failed, 4 passed |
| 21 | B4 | default ON (`:-1`) | KILLED | 1 failed, 4 passed |
| 22 | B4 | one write made fatal (no `|| echo`) | KILLED | 1 failed, 4 passed |
| 23 | B4 | refusal silenced (`|| true`) | KILLED | 1 failed, 4 passed |
| 24 | B4 | protected_regular 2 -> 1 | KILLED | 1 failed, 4 passed |
| 25 | B4 | `exit 1` inside block | KILLED | 1 failed, 4 passed |
| 26 | B4 | launches ff-harden | KILLED | 1 failed, 4 passed |
| 27 | B4 | "applied" line to stdout | SURVIVED | 5 passed |
| 28 | B4 | "applied" line removed | SURVIVED | 5 passed |
| 29 | B4 | block moved before TERM trap | KILLED | 1 failed, 4 passed |

Totals from the table: B1 8 (5 killed / 3 survived); B2 5 (5/0); B3 6 (3/3); B4 10 (8/2). All 29: 21 killed, 8 survived (72%).
- The B1 survivors (#2, #3, #8) also pass `tools/topology_lint.py` (`RESULT: OK (0 finding(s), 4 allowlisted)` for each). The build's `test -z` runs BEFORE them, so a setuid file copied there would ship. The test's `^(COPY|RUN|ADD)\b` match is case-sensitive and anchored at column 0, and it exempts any line containing "ff-harden" (test_fly_image_hardening.py:33). LOW. HIGH confidence (executed). That Docker accepts lowercase/indented instructions: general knowledge, HIGH.
- The B3 survivors: ff-harden's verdict logic (read-back, rc, exit) is pinned only by substring presence (test:63), not by behaviour. Mutant on the DRY_RUN guard was NOT run: it would write this host's sysctls (hard limit).
- The B4 survivors are cosmetic.

## (5) Callers / consumers (origin/main d2cfab30c)
- `grep -rn 'FIELD_HARDEN_SYSCTLS\|ff-harden\|perm /6000'`: only integration/fly/{Dockerfile,entrypoint.sh,README.md}, tools/ff-harden.sh, tools/topology_lint.py:1282-1283, integration/demo/Dockerfile:47-54, and the test. HIGH
- GB10 mirror #1071 (507f0109c): integration/demo/Dockerfile:53-54 has the same strip+check after its last COPY (line 45) and no sysctls (rationale at :50-52). It is pinned by test_gb10_image_strips_setuid_after_the_last_binary_step_without_sysctls on main (same column-0/case-sensitive weakness). Not built here. HIGH (read)
- Compose: no reference (by design). fly.toml: no FIELD_HARDEN_SYSCTLS (default off holds). docs/runbooks: no mention, so the arming procedure lives only in integration/fly/README.md:98-110, which is wrong (F-1). HIGH
- services/claude-approver/Dockerfile is not stripped. Out of scope; informational. HIGH (find)

## Verdict on 6bc2c80: PASS WITH CONDITIONS
Rationale: the default-off runtime change is inert. The image strip is placed correctly and enforced at build time (CI green on an identical tree). No finding is exploitable today (all processes are root; the PR says this is hygiene). Conditions:
1. (MEDIUM, F-1) Fix README.md:104-107 and ff-harden.sh:9. The entrypoint does not run ff-harden. The arming check is `fly ssh console -C /usr/local/sbin/ff-harden` (expect 4 `ok`), not the boot log.
2. (LOW-MEDIUM, F-2) Make entrypoint.sh:40 report the refused count instead of an unconditional "applied".
3. (LOW) Add a runtime step to fly-image-smoke: `docker exec estate sh -c 'test -z "$(find / -xdev -type f -perm /6000)"'`. It closes the B1 survivors for both images regardless of instruction spelling. Optionally widen the test regex to `(?i)^\s*(COPY|RUN|ADD)\b` and drop the "ff-harden" exemption in favour of excluding only line 69 exactly.
4. (LOW) Test ff-harden's failure path behaviourally (e.g. an injectable /proc/sys root for tests only), and warn on non-0/1 values of FIELD_HARDEN_SYSCTLS (F-3).
5. (LOW, carry-over from #1057 F6) Either move the block after the secret refusals (and edit test:78) or reword the "one error line" docs.
6. (LOW) Decide on file capabilities (caddy cap_net_bind_service) before non-root agent uids land.

Status: COMPLETE. Worktrees removed at end of review.

### #1075 post-merge (roley.reviewer, 95cd964)

Merge sha: 95cd964731ec86e5d529cb4a7b7e9ddb5fa50e52 (squash; parent ba861753). Source: `git log -1 --format='%H %P' 95cd96473`; GitHub PR head 3de26bf8.

#### Corrections (first)
1. **#1075 changes no service code.** `git diff --stat 95cd96473^ 95cd96473` lists only `docs/capstone-evidence/t6-health-under-load.md` (+131), `tools/health_under_load.py` (+214) and `tools/tests/test_health_under_load.py` (+87). The PR body says: "this PR ships no code fix". The title "heavy ledger routes must not block /health" describes the task, not what was delivered. HIGH
2. **The /health lane, the read gate and `test_health_and_appends_do_not_wait_behind_queued_heavy_reads` were in the code before #1075.** The test exists at the merge parent ba861753 (`git grep` at 95cd96473 gives `services/sealed-ledger/tests/test_ledger_c2_hardening.py:1234`). Pickaxe (`git log -S`) dates it to 6ba5f61b8 (2026-11-08). #1075 cites them as evidence; it did not introduce them. HIGH
3. **#1089 was not found in local history** (`git log --all --grep='#1089'` returned nothing relevant). Taken as given, not verified. LOW

#### What #1075 actually introduced
- `tools/health_under_load.py`: a loopback-only harness that polls /health around one heavy GET.
- `tools/tests/test_health_under_load.py`: 12 tests.
- An evidence doc. The doc makes HIGH-confidence claims: /health runs on its own lane, and `LedgerStore.health_info` never takes the read gate.

This review attacks the harness and its tests, and checks the doc's claims against the code at the merge sha. Behavioural findings in ledger code are **pre-existing**: #1075 did not cause them, but it asserted the mechanism as HIGH.

#### Executable cases
File: `/tmp/claude-0/pm1075/cases/test_cases_1075.py`. Command: `pytest -q -s test_cases_1075.py`. Last line: `7 passed, 1 warning in 3.47s`. Each case asserts the behaviour it documents.

| case | question | result | origin | conf |
|---|---|---|---|---|
| C1 | Is /health's head_hash correct after an append while a heavy read holds the read gate? | Correct. head = the new append's hash, count +1 | pre-existing (lanes) | HIGH |
| C2 | Does /health report an unknown head, or a count that goes down, during 3 rotations + 15 appends polled concurrently? | Neither | pre-existing | HIGH (one run, not a proof) |
| C3 | Another process appends, then the recount raises | **/health ok=true with the STALE head and count** (`store.py:1914` `except Exception: pass`; `api.py:372` `ok=True` unconditional) | pre-existing | HIGH |
| C4 | The open segment file is deleted under a running store | **/health ok=true, event_count 11→8**, head = the last closed segment's; /verify ok=false | pre-existing | HIGH |
| C5 | The harness refuses a non-loopback base. Does it also refuse a redirect? | **No.** `request()` follows a 302 from 127.0.0.1 to 127.0.0.2 (which `loopback_base` refuses) and **sends `x-field-auth` there** (urllib's default redirect handler copies the header) | **#1075** | HIGH |
| C6 | `summarize` window | A poll sent 0.2 s before the heavy GET that times out inside it counts as **idle, not failed** (window keys on send time `t`, `health_under_load.py` summarize) | **#1075** | HIGH |
| C7 | Does the committed e2e stub test exercise the failure counter? | **No.** 0 polls fall in the "during" window (heavy GET is instant), so `failed == 0` is vacuous | **#1075** | HIGH |

C3/C4 matter because the witness anchors the remote ledger's head from `/ledger/health` (`witness.py:247` → `parse_head`). A stale or regressed head on /health becomes a signed `anchor.remote`. That is not #1075's change; it is a fail-open the doc's "/health never locks" framing does not mention. MEDIUM (impact inferred from code, not run end to end)

#### Suite on the merge sha
`pytest -q packages/field-core/tests services/sealed-ledger/tests` at 95cd964. Venv: `/tmp/claude-0/pm1075/venv`, Python 3.13.18, installed as ci.yml "Install platform". Last line: **`3316 passed, 6 skipped, 2 warnings in 167.52s (0:02:47)`** (exit 0). HIGH

The PR's own tests: `pytest -q tools/tests/test_health_under_load.py` → `12 passed in 2.26s`. HIGH

#### Mutants
Runner: `/tmp/claude-0/pm1075/mutants.py`. One textual mutant at a time in the worktree, then `git checkout -- .`. A clean tree is asserted after each one, and `git status` showed 0 changed files at the end.
- B1–B3 run against `tools/tests/test_health_under_load.py`.
- B4 runs against `test_health_and_appends_do_not_wait_behind_queued_heavy_reads`. B4 is the code behind the doc's HIGH claims; that code is pre-existing.

| behaviour | mutant | result | last line |
|---|---|---|---|
| B1 loopback refusal | M1.1 LOOPBACK also accepts 0.0.0.0 | killed | 1 failed, 2 passed in 0.05s |
| B1 | M1.2 scheme check dropped | killed | 1 failed, 3 passed in 0.05s |
| B1 | M1.3 host check only rejects missing host | killed | 1 failed in 0.06s |
| B1 | M1.4 any 10./127. prefix accepted | killed | 1 failed, 1 passed in 0.05s |
| B2 failure counting | M2.1 >= 5 s becomes > 5 s | killed | 1 failed, 10 passed in 0.57s |
| B2 | M2.2 only 500 counts as failed | killed | 1 failed, 10 passed in 0.56s |
| B2 | M2.3 streak never resets | **SURVIVED** | 12 passed in 2.26s |
| B2 | M2.4 run() summarises an empty window | **SURVIVED** | 12 passed in 2.27s |
| B2 | M2.5 poller records every status as 200 | **SURVIVED** | 12 passed in 2.26s |
| B3 proxy-free opener | M3.1 default opener (reads proxy env) | killed | 1 failed, 8 passed in 0.05s |
| B3 | M3.2 ProxyHandler() reads env | killed | 1 failed, 8 passed in 0.05s |
| B3 | M3.3 request() uses urlopen | **SURVIVED** in this env* | 12 passed in 2.27s |
| B3 | M3.4 explicit proxy configured | killed | 1 failed, 8 passed in 0.05s |
| B4 /health and appends off the read lane | M4.1 health_info runs on the read lane | killed | 1 failed, 1 warning in 13.65s |
| B4 | M4.2 health_info waits on the read gate | killed | 1 failed, 1 warning in 13.77s |
| B4 | M4.3 operator health fields on the read lane | killed | 1 failed, 1 warning in 13.67s |
| B4 | M4.4 appends run on the read lane | killed | 1 failed, 1 warning in 20.36s |
| B4 | M4.5 /verify skips the read gate (vacuity probe) | **SURVIVED** | 1 passed, 1 warning in 3.66s |

\* With `NO_PROXY`/`no_proxy` unset, M3.3 is killed: `2 failed, 10 passed in 2.08s`. The proxy test's behavioural half only bites when no NO_PROXY covers loopback. HIGH

**Totals, counted from the table: 18 mutants, 13 killed, 5 survived.**

| behaviour | killed |
|---|---|
| B1 | 4/4 |
| B2 | 2/5 |
| B3 | 3/4 (4/4 without NO_PROXY) |
| B4 | 4/5 |

#### Answers to the brief's questions (corrected scope)
1. **How /health avoids blocking.** A dedicated 4-thread `health` executor (`api.py:329-333`, `:362`, `:366`). `health_info` reads a cached `(count, head)` keyed on the disk key and never takes the read gate (`store.py:1879-1919`, `_disk_key` `:1571` = open-segment size+inode + journal size). Pre-existing; #1075 only cites it. M4.1–M4.3 being killed confirms the claim. HIGH
2. **Stale or wrong head during a heavy read or a rotation.**
   - Correct in C1 (gate held) and C2 (rotations + appends polled concurrently). HIGH for the cases run.
   - Stale under a failed recount (C3) and regressed when the open segment vanished (C4), both with ok=true. Pre-existing fail-open. HIGH
3. **Appends starving.** Appends have their own 8-thread lane (`api.py:331`). Under a held gate, measured appends were ≤ 0.077 s (8 runs, including 3 under 8 busy-loop processes on 4 cores). M4.4 killed. #1075's own doc says this does not remove GIL contention from a RUNNING parse (README LIMITS). HIGH
4. **Is `test_health_and_appends_do_not_wait_behind_queued_heavy_reads` timing-dependent?**
   - Not flaky in practice: 2.0 s/5.0 s budgets against ≤ 0.097 s measured, 5/5 plain and 3/3 under CPU stress. HIGH for this host
   - **It can pass vacuously**: it never asserts the 60 reads are still queued when it measures. M4.5 (the gate removed from /verify, so nothing queues) survives. HIGH
   - The `time.sleep(3.0)` "every reader connected" is an unchecked timing assumption. On a slow host, fewer than 40 queued readers would also let the pre-lane code pass. Not run at the pre-lane sha. MEDIUM
   - The test is pre-existing, not #1075's.
5. **Thread safety of state #1075 added.** `polls[prefix]` lists: one writer thread each; read after `join(timeout=7)`. urllib's `timeout` is per socket operation, so a slow-drip response can outlive the join and append while `summarize` iterates. CPython does not raise on that, but late rows can be missed. Not exercised. LOW
6. **Fail-closed weakened?** **No.** #1075 changes no runtime path (diff stat). /health returning ok=true with a stale or regressed head (C3/C4) predates it. The doc's "/health never locks" framing omits that cost. HIGH

#### Findings against #1075 (ranked)
| id | finding | evidence | severity | conf |
|---|---|---|---|---|
| F1 | The harness follows redirects to hosts its own guard refuses, sending `x-field-auth` | C5; urllib default `HTTPRedirectHandler` in `build_opener` | Low: local tool, test secret, but it contradicts the "refuses non-loopback" docstring | HIGH |
| F2 | The e2e test cannot detect a broken failure counter (0 polls in window) | C7; M2.4 and M2.5 survive | Medium: the harness's headline numbers rest on the untested path | HIGH |
| F3 | The window keys on send time, so a timeout sent just before the heavy GET counts as idle | C6 | Low/Medium: it biases "failed during" downward, the opposite of conservative | HIGH |
| F4 | The proxy-free test's behavioural half is masked by NO_PROXY | M3.3 env-dependent | Low | HIGH |
| F5 | The streak-reset branch is untested | M2.3 survives | Low | HIGH |
| F6 | The PR title claims a behaviour change the PR does not make | diff stat vs title | Process | HIGH |

#### In-repo callers of ledger /health
Behaviour is unchanged by #1075, so none is newly affected. These are the callers exposed to the pre-existing C3/C4 fail-open:
- `services/sealed-ledger/src/sealed_ledger/witness.py:247`: anchors the remote head from `/ledger/health` (`parse_head`). **Most exposed:** it signs whatever head /health returns.
- `services/sealed-ledger/src/sealed_ledger/cli.py:972`: witness direction 1.
- `services/attestation-reporter/src/attestation_reporter/engine.py:445,473`: the `earliest_live_*` note in the pack.
- `integration/fly/fly.toml:82`: the Fly http_service check. Liveness only, so ok=true while broken never fails it.
- `.github/workflows/ci.yml:500,609,621,642,655,666-667`: smoke checks.
- `integration/demo/fixtures/upgrade-smoke/signing_fault.py:76`.
- `tools/health_under_load.py`: the harness itself.

#### Verdict: **PASS WITH CONDITIONS** (95cd964)
The merge is tooling and docs only. The suite is green, and the doc's HIGH mechanism claims hold under mutation (B4: 4/5 killed).

Conditions (follow-up PR, harness only):
1. Build `_OPENER` with a handler that refuses redirects (F1).
2. Count a poll as "during" when `[t, t+dt]` overlaps `[start, end]` (F3).
3. Add an e2e case with a slow and a 503 stub, so that M2.3, M2.4 and M2.5 are killed (F2, F5).
4. Run the proxy test with NO_PROXY cleared (F4).

Separate issue, not a #1075 condition: /health `ok=True` is unconditional and `health_info` swallows recount errors (C3/C4), while the witness signs that head. Recommend `ok=false` or a `head_stale: true` field whenever the recount failed or the count regressed. MEDIUM

Not done:
- No GitHub comment.
- No estate request.
- Not run: the lane test at the pre-lane sha.

### #1076 post-merge (roley.reviewer, 787de47)

Status: COMPLETE (written incrementally; sections appended in order of work)

- PR: SpinStateLabs/field-platform#1076 "T7: ledger-head parse cache with a parse-count test", merged 2026-11-20T23:49:11Z by squash; head 224e33e, base 95cd964 (GitHub MCP pull_request_read get). HIGH
- Merge sha: 787de47dee5f06be29f5123090d2ba6a03a9571e (`git log` on main: "T7: ledger-head parse cache ... (#1076)", single parent 95cd964 = PR base). HIGH. Note: the MCP `get` payload did not include `merge_commit_sha`; the sha is taken from main's history and parent match.
- Worktree /tmp/claude-0/pm1076 (detached), venv /tmp/claude-0/venv1076 (Python 3.13.18, CI "Install platform" steps, editable installs pointing at the worktree).
- Diff: 3 files, +323/-5: store.py (+96), README.md, tests/test_ledger_head_cache_t7.py (+217, 11 tests).

## Attack cases (executable)
File: /tmp/claude-0/pm1076-attacks/test_attack_1076.py (15 cases; each asserts the CORRECT behaviour: cached store == uncached verify of the same read == fresh store).
Command: `cd services/sealed-ledger && PYTHONPATH=tests python -m pytest -q /tmp/claude-0/pm1076-attacks/test_attack_1076.py` on 787de47 -> last line `6 failed, 9 passed in 3.01s`. HIGH

| case | attack | result at 787de47 |
|---|---|---|
| K1 | open segment, same size + same inode + mtime_ns restored, after warm verify/events | safe (detected) |
| K2 | unlink + recreate same size (inode reuse), mtime restored | safe |
| K3 | os.replace same-size tmp, mtime restored | safe |
| K4 | CLOSED segment same-size edit (rotated, unarchived) after cached verify, mtime restored | safe (code correct; no in-repo test, see (b)) |
| K5 | archived ledger: flip a byte in the archive copy after a cached verify | **FAIL: stale ok=True from cache, uncached ok=False** |
| K5b | archived ledger: delete the archive copy after a cached verify | **FAIL: stale ok=True** |
| K6 | append by another store instance (other-process stand-in) | safe |
| K7 | rotation by another store | safe |
| K8 | archive by another store (events + verify) | safe |
| K9 | 4 reader threads (events + verify, chain-link check, monotone length) vs 150 appends | safe (no error) |
| K10 | retained raw bytes (parse cache + verify cache, distinct objects) <= PARSE_CACHE_MAX_BYTES | **FAIL: 25180 retained vs cap 12600 (2 copies)** |
| K11 | stale cache entries after 12 rotations | safe (bounded; rotated paths stay live) |
| K12 | tamper on disk, caller restores the field on the cached event, same-store verify | **FAIL: same store ok=True, fresh store ok=False (false ok, no append needed)** |
| K13 | same masking, retention guard `_refuse_unless_live_verify_ok` | **FAIL: DID NOT RAISE LedgerCorrupt (archiving would proceed past a tamper)** |
| K14 | caller sets cached head `.hash`, identical-bytes file replace (new inode), then append | **FAIL: ledger WRITES prev_hash=ffff... ; fresh verify `link break at index 40`** |

Cache key (from code): exact bytes per segment path (store.py:1720-1737 `raw == data`, extension `raw.endswith(b"\n") and data.startswith(raw)`); never stat. So size/mtime/inode/mtime-granularity attacks (K1-K4) cannot keep the key. HIGH (code + K1-K4).

Same attack file against current main ce1ffae (separate temporary worktree, PYTHONPATH override, removed after): `4 failed, 11 passed in 2.00s` -- K5/K5b fixed by #1078 (cb7a94f, "never answer /verify from the cache once a segment is archived (T8)"); K10, K12, K13, K14 still live on main. HIGH

## Suite on merge sha
`pytest -q packages/field-core/tests services/sealed-ledger/tests` (repo root, worktree 787de47, venv1076) -> `3327 passed, 6 skipped, 1 warning in 163.69s (0:02:43)`. Log: /tmp/claude-0/reports/pm1076-suite.log. HIGH
(First attempt errored at collection, `No module named 'uvicorn'`, because the venv lacked CI's final `pip install fastapi uvicorn httpx pytest` line; rerun after completing the CI install.)

K15 (same-size tamper, then another writer appends; same store verify) and K16 (cached unterminated last record, then the same line grown) added after the first mutant pass; both pass at 787de47 (attack file now `6 failed, 11 passed in 0.87s`, same 6 failures). HIGH

## Mutants (worktree only; `git checkout -- .` after each; runner /tmp/claude-0/pm1076-attacks/mutate.py, raw rows /tmp/claude-0/reports/pm1076-mutants.json)
Columns: T7 = `tests/test_ledger_head_cache_t7.py` (the PR's 11 tests); ATK = attack cases newly failing vs the 6 baseline failures; FULL = `pytest -q -x services/sealed-ledger/tests` (repo root), run only for mutants T7 did not kill.

| beh | mutant | T7 (11 tests) | ATK new failures | FULL sealed-ledger (`-x`) | outcome |
|---|---|---|---|---|---|
| B1 equal-bytes key | M1.1 size-only key | KILL 1 failed | K1,K2,K3,K4,K8 | n/a | killed |
| B1 | M1.2 path-only key | KILL 7 failed | K1-K4,K6-K9,K15,K16 | n/a | killed |
| B1 | M1.3 first-half bytes + size | KILL 1 failed | K4 | n/a | killed |
| B1 | M1.4 last-4KiB bytes + size | KILL 1 failed | K1,K2,K3 | n/a | killed |
| B2 extension path | M2.1 newline guard dropped | live 11 passed | K16 | live `1071 passed, 5 skipped` | **survives in-repo** (ATK only) |
| B2 | M2.2 prefix check -> length grew | live 11 passed | K15 | KILL `1 failed, 535 passed` (test_ledger_readers.py::test_interleavings_rotate_vs_readers, incidental) | killed (not by T7) |
| B2 | M2.3 bad tail ignored | KILL 2 failed | - | n/a | killed |
| B2 | M2.4 grown not remembered | KILL 2 failed | - | n/a | killed |
| B3 strict-only cache | M3.1 tolerant parse cached | KILL 2 failed | K16 | n/a | killed |
| B3 | M3.2 partial tolerant parse cached | KILL 2 failed | - | n/a | killed |
| B3 | M3.3 tolerant never cached | KILL 1 failed | - | n/a | killed |
| B3 | M3.4 tolerant catches JSONDecodeError only | KILL 2 failed | - | n/a | killed |
| B4 verify key | M4.1 layout dropped | live | - | live `1071 passed` | **survives all** |
| B4 | M4.2 open segment bytes only | live | K4 | live `1071 passed` | **survives in-repo** (= #1078's M2.4) |
| B4 | M4.3 segment sizes only | KILL 1 failed | K1-K4 | n/a | killed |
| B4 | M4.4 over-cap result cached | live | - | live `1071 passed` | **survives all** |
| B5 memory cap | M5.1 oversized segment kept | KILL 1 failed | - | n/a | killed |
| B5 | M5.2 eviction loop removed | live | - | live `1071 passed` | **survives all** |
| B5 | M5.3 cap x2 | live | - | live `1071 passed` | **survives all** |
| B5 | M5.4 cap on event count | live | - | live `1071 passed` | **survives all** |
| B6 locking | M6.1 no lock, parse lookup | live | - | live `1071 passed` | **survives all** |
| B6 | M6.2 no lock, _remember | live | - | live `1071 passed` | **survives all** |
| B6 | M6.3 no lock, verify read | live | - | live `1071 passed` | **survives all** |
| B6 | M6.4 no lock, verify write | live | - | live `1071 passed` | **survives all** |
| B7 reader isolation | M7.1 equal hit returns cached tuple | live | - | live `1071 passed` | **survives all** |
| B7 | M7.2 shared list on equal hit | KILL 1 failed | K6,K9 | n/a | killed |
| B7 | M7.3 verify hit returns cached object | live | - | live `1071 passed` | **survives all** |
| B7 | M7.4 grown list shared | live | K9 | KILL `1 failed, 141 passed` (test_caller_signing_f2b.py, incidental) | killed (not by T7) |

Totals (counted from the table): 28 mutants, 7 behaviours x 4. Killed by T7's own file: 13/28. Killed by the full in-repo sealed-ledger suite (T7 + rest): 15/28. Killed by ATK: 11/28. Killed by in-repo or ATK: 17/28. Survive the in-repo suite: 13 (M2.1, M4.1, M4.2, M4.4, M5.2, M5.3, M5.4, M6.1-M6.4, M7.1, M7.3). Survive everything: 11 (M4.1, M4.4, M5.2-M5.4, M6.1-M6.4, M7.1, M7.3). HIGH (rows from /tmp/claude-0/reports/pm1076-mutants.json and pm1076-mutants-full.json)
Note: FULL here is `services/sealed-ledger/tests` only at 787de47 (1071 tests + 5 skipped); the CI line above also includes field-core.

## CORRECTIONS (first)
1. FALSE at 787de47 (PR body "Mechanism" + store.py `_verified` docstring "The result is a pure function of them"): `/verify` on a ledger with an archived segment also reads files outside the key (`Snapshot._verify_archived`, store.py:1276-1310: the archive copy at `archived_to`). K5/K5b: after a cached verify, flipping one byte in, or deleting, the archive copy leaves the same store answering `ok=True` while an uncached verify of the same read says `ok=False` (`break_segment=1`). This is a false OK from #1076 itself, needing no in-process mutator. Fixed later on main by #1078 (cb7a94f, whose commit message credits "T7 post-merge review, reproduced"); K5/K5b pass on ce1ffae. HIGH
2. FALSE (PR body "Memory cap ... the cache holds at most about 160 MB"; README T7 paragraph "keeps at most PARSE_CACHE_MAX_BYTES ... of raw segment bytes"): the cap bounds `_parse_cache` only. `_verify_cache` keeps a second list of raw bytes objects (store.py:1774-1776), and on an equal-bytes hit those are different objects from the parse cache's (the hit keeps the old `raw`, the verify cache stores the snapshot's new `data`). K10: 25180 B retained vs cap 12600 B (two distinct 12590 B copies). Worst case is about 2x32 MiB raw + ~128 MB parsed, ~192 MB, not ~160 MB. Still bounded. HIGH (K10), MEDIUM (MB extrapolation from the PR's own 4x figure).
3. OVERSTATED (PR body "The 5 that pass on both prove the cache returns exactly what an uncached read returns"; "each reader gets its own list"): `test_each_reader_gets_its_own_list` (t7:188-192) is vacuous for the cache: `events()` always builds a new list (store.py:2259 list comprehension), and its first call is a cache miss. Mutant M7.1 (equal hit returns the cached tuple itself) survives the T7 file. HIGH
4. INCOMPLETE (PR body "What I did NOT verify: whether any caller mutates a returned LedgerEvent ... The README now states the rule"): the store itself is a consumer of the shared objects in its WRITE path. `_recover_locked` (store.py:1789-1801) takes the writer head from `snap.head` = the cached last event's `.hash` (store.py:1110-1113). K14: one caller sets `events()[-1].hash`, the file is replaced by identical bytes (new inode -> `_disk_key` change -> recover on next write), and the next `append` writes `prev_hash=ffff...` to disk; a fresh store then reports `link break at index 40`. The ledger corrupts its own on-disk chain from a mutated cache object. HIGH (repro), fail-closed (break is detectable).

## Where the known context traces
- (a) shared mutable LedgerEvent: INTRODUCED by #1076. `_parsed` returns `list(events)` over a cached tuple of the same objects (store.py:1734, 1737 at 787de47); `LedgerEvent` is a non-frozen pydantic model (packages/field-core/src/field_core/ledger.py:61-62). Reproduced at 787de47 without an append: K12 (same-store verify ok=True, fresh ok=False) and K13 (retention guard `_refuse_unless_live_verify_ok`, store.py:2566-2582, does not raise, so retention apply would archive past a tamper). K13 and K14 are new consequences beyond the #1095 verdict. Still live on main ce1ffae. HIGH (repro), exploitability MEDIUM: needs an in-process mutator; no in-repo non-test mutator found (api.py:440 serializes; prior grep in R-PR1095 report).
- (b) open-segment-only verify key survives: TRACES to #1076's tests. At 787de47 the code compares every segment (store.py:1772 `all(a == b for a, b in zip(cached[1], snap.raw))`), K4 passes, but M4.2 (open segment only) survives the T7 file; T7's same-size test is open-segment only (t7:128-150) and its rotation test never tampers a closed segment (t7:206-217). HIGH
- (c) /health stat key (size, inode): NOT #1076. `_disk_key` (store.py:1594-1604) is unchanged by the #1076 diff (`git blame` attributes all lines to the pre-#1076 boundary commit 6ba5f61). #1076 interacts with it only through K14 (a stat change triggers `_recover_locked`, which now reads the head from the parse cache). HIGH

## Attack-by-attack answers
- Cache key: exact bytes per path, never stat (store.py:1720-1737). Same size, same mtime_ns, same inode, inode reuse after unlink, os.replace, coarse mtime: none keep the key (K1-K4 pass). HIGH. mtime granularity is irrelevant because mtime is never read by the cache (code). HIGH
- Invalidation: append (same store and another store, K6, K15), rotation by another store (K7), archive by another store for events (K8) all correct. Archive for VERIFY is wrong at 787de47 (K5/K5b; correction 1). HIGH
- Thread safety: K9 (4 readers vs 150 appends) clean. All four lock-removal mutants (M6.1-M6.4) survive T7 and ATK, so the lock is untested; under CPython's GIL a dict get/set and a tuple-of-(bytes, events) store are atomic, and a stale `_remember` from a slower reader only regresses the cache to older bytes, which are still compared exactly, so correctness does not depend on the lock (code reasoning). MEDIUM. Free-threaded CPython (3.13t/3.14t) not tested. LOW
- Memory: bounded (cap + single verify entry + per-path eviction; K11 no stale growth over 12 rotations), but about 2x the claimed raw bound (correction 2). Eviction (M5.2), the cap multiplier (M5.3) and a count-based cap (M5.4) are untested by T7. HIGH
- Parse-count test: not vacuous for "parse once". It asserts `validations == N` exactly (t7:73) with `LedgerEvent.model_validate` patched at class level and looked up at call time (store.py:640), so an implementation that skips counting would fail, not pass. The verify-reuse test counts `store_mod.verify_chain`, which `Snapshot.verify` resolves through the module global (store.py:976, 1140). Mutants M1.x, M2.3, M2.4, M3.x and M5.1 are killed by it or its siblings. Vacuous parts are the list-isolation test (correction 3) and the absence of a tamper-then-append case (M2.2 survives T7). HIGH

## In-repo callers affected (non-test, at 787de47; grep of `.events(|.snapshot(|.verify(|hash_at(|export(|_take_snapshot(`)
Readers that now receive shared cached `LedgerEvent` objects or cached verify results:
- services/sealed-ledger/src/sealed_ledger/api.py:440 (`GET /events`, serializes), api.py:458 (`GET /verify` -> `_verified`), api.py:490 (export).
- cli.py:395, 1085 (`verify`), cli.py:420, 1091 (`snapshot`, signature/witness checks), cli.py:520 (`export`).
- anchors.py:81, 157 (`snapshot`), anchors.py:208 and witness.py:412 (`hash_at` reads `.hash` of cached objects).
- store.py internal: `_recover_locked` 1789 (writer head; K14), `iter_events` 2024, `hash_at` 2273, `export` 2298-2300, `_refuse_unless_live_verify_ok` 2572-2573 (retention guard; K13).
- services/incident-replay/src/incident_replay/engine.py:403, 430 (`self.ledger.verify()/events()`): MEDIUM that this is an HTTP client per R-PR1095 (dicts, not shared objects); not re-verified here.
No non-test in-repo mutator of a returned LedgerEvent found (R-PR1095 grep; not re-derived). MEDIUM

## ASSUMPTIONS
1. 787de47 is #1076's merge (squash) commit: parent 95cd964 equals the PR base sha; subject carries "(#1076)". HIGH
2. A second `LedgerStore` on the same path is an adequate stand-in for another process (each has its own cache; the PR body says the same). MEDIUM
3. "False ok" means the same store's `verify()` says ok=True while an uncached `Snapshot(...).verify()` of the same read, or a fresh store, says ok=False. HIGH (definition)

## REASONING
1. The parse-cache key is exact bytes, so every stat-shaped attack fails (K1-K4) and the PR's main design claim holds for live segments. HIGH
2. The verify-result key (layout + live bytes) omits archive files that `_verify_archived` reads, so on any archived ledger an archive-copy flip or deletion is served as ok from the cache (K5/K5b). This needs no mutator and is reachable through `GET /verify` (api.py:458 -> `_verified`). It is a ledger-integrity false ok introduced by #1076. HIGH
3. Shared mutable objects (a) let an in-process caller mask a tamper in `verify` (K12) and in the retention guard (K13), and push a mutated head into the next write (K14). The README "no reader may mutate" rule is unenforced. Exploitability needs an in-process mutator: none found. MEDIUM
4. The test suite pins parse counts well (13 kills from T7 alone) but leaves the verify key's layout (M4.1) and closed-segment bytes (M4.2), the newline guard (M2.1), the eviction and cap (M5.2-M5.4), the locks (M6.x) and reader isolation (M7.1, M7.3) unpinned. HIGH
5. Severity on the merge sha is set by step 2: a security-relevant false ok with no precondition beyond "a segment is archived". The main branch fixed that one in #1078 (commit cb7a94f dated 2026-11-20 21:44:47 -0500, about 2h55m after #1076 merged at 23:49:11Z; commit date, not merge time). MEDIUM

## CONCLUSION / VERDICT on 787de47: **BLOCK**
Reason: K5/K5b, a stale `ok=True` from `/verify` on an archived ledger whose archive copy was altered or deleted, introduced by #1076 and reproduced at the merge sha. Already remediated on main by #1078 (K5/K5b pass on ce1ffae). HIGH
Residual items still open on main (ce1ffae), recommended as conditions for the next T-series cache change:
- C1 (MEDIUM severity): freeze or copy the events handed out of the parse cache (frozen model, or `model_copy` on hand-out), or at least have `_recover_locked` and `_refuse_unless_live_verify_ok` bypass the cache. Kills K12-K14. Add K12-K14 as tests.
- C2: add tests that kill M4.1 (journal edit after a cached verify; #1078 added one), M4.2 (closed-segment same-size edit, = (b)), M2.1 (#1078 added one), M5.2-M5.4 (eviction and cap) and M7.1/M7.3 (mutate a hit-path list / returned verification, then re-read).
- C3 (LOW): correct the "at most about 160 MB" / "keeps at most PARSE_CACHE_MAX_BYTES" claims (two raw copies, K10), or make the verify cache reuse the parse cache's bytes objects.
- C4 (INFO): the four lock-removal mutants survive; either test under free-threaded CPython or document that correctness does not rely on `_cache_lock`.

Worktree /tmp/claude-0/pm1076 removed after the review; attack file, runners and findings draft kept at /tmp/claude-0/pm1076-attacks/. No GitHub comment, push, commit or deployed-service request made.
Status: COMPLETE.

### Correction to section (3) (roley.reviewer, 2026-11-22)

Section (3) says all 25 PRs merged between 2026-11-07 and 2026-11-21 had "no review on record". **That is wrong.** The method checked GitHub reviews and comments plus main's tasks/, docs/, STATE.md and CHANGELOG.md. It did NOT check the `comms` branch, where reviewers file verdicts (comms/done/reviewer__*.md). Corrected status, using comms evidence (MEDIUM-HIGH confidence; every row cites a path):

- **Pre-merge review on the merged head:** 2 PRs (#837, #1054). The audit missed both.
- **Batch PRs whose every bundled PR has a reviewer file:** 6 PRs (#950, #973, #1012, #1017, #1049, #1052). The bundled verdicts were not compared sha-by-sha against each bundled PR's GitHub head.
- **Post-merge review only:** 12 PRs. Ten of these were filed by don.reviewer on 2026-11-21 after the audit was written; #975 and #1016 were reviewed post-merge by fp-reviewer-a on 2026-11-08, and their bundled PRs have pre-merge files.
- **No review record found anywhere:** 5 PRs (#1058, #1064, #1070, #1074, #1075).

The statement "no PR comment" was true when the audit ran (2026-11-21 ~15:30Z). don.reviewer's post-merge comments on 11 of these PRs were posted later that day.

Lesson (also proposed for tasks/lessons.md): before stating that a change has no review on record, search the comms branch as well as GitHub reviews and comments.

#### Correction to roadmap-audit section (3): review records on the `comms` branch

Scope: the 25 PRs merged 2026-11-07..2026-11-21. Source: read-only extract of origin/comms at `/tmp/claude-0/commsro/comms` (paths below are relative to it). Merged sha / PR head sha: GitHub PR get (`SpinStateLabs/field-platform`) and `git log origin/main` in `/workspace/field-platform`. Files written by roley.reviewer are excluded.

Conventions
- "merged sha7": the commit on main. For fast-forward merges (837, 950, 973, 975, 1012, 1016, 1017, 1049, 1052, 1054, 1055, 1057) this equals the PR head. For squash merges it is the squash commit; the PR head sha7 is given in brackets. A review of the squash commit reviews the merged result.
- Merge types: fast-forward per `inbox/coordinator/20261108-0240-fp-merge-a-batch-m3-landed.md`, `...-0310-fp-merge-a-batch-m4a-landed.md`, `...-1354-fp-merge-b-batch-m4b-landed.md`, `...-1937-fp-merge-b-batch-m6b-landed.md`, `...20261108-2036-fp-merge-b-batch-m8b-landed.md`, `...20261109-0059-fp-merge-b-batch-m9b-landed.md`, `...20261109-0530-fp-merge-a-batch-m5a-landed.md`, `...20261109-1241-fp-merge-b-batch-m12b-landed.md`, `...20261110-1038-fp-merge-a-batch-pr1054-landed.md`; 1055 and 1057 per `inbox/coordinator/20261121-2235-don.reviewer-postmerge-pr1055.md`, `...20261121-2111-don.reviewer-postmerge-pr1057.md`. Squash: git log subjects ending `(#n)`.
- "pre" = filed before merge; "post" = filed after merge (post-merge by fp-reviewer-a, or by don.reviewer on 2026-11-21). A "verifier run" is a GX10 16-suite test run, not a review; it is listed but does not count as a review.
- Batch PRs: the vehicle PR has no reviewer file of its own (except 975, 1016); "k of m" counts bundled PRs that have a `done/reviewer__PR<n>@*.md` with a verdict.

## Table

| PR | merged sha7 | review record(s) (path, sha7, verdict) | reviewed head == merged head? | corrected status |
|---|---|---|---|---|
| 837 | 2bc5643 | reviewer: `done/reviewer__PR837@2bc5643.md` 2bc5643 PASS (pre, 2026-11-07T17:38Z); earlier heads: `done/reviewer__PR837@{81fd0e2,3a435b7,c972adf,a6e2ec3}.md` PASS WITH CONDITIONS. verifier: `done/verifier__RUN_PR837@2bc5643.md` 16/16 | yes (2bc5643) | REVIEWED on merged head |
| 950 | 62a3f85 | bundled 920 885 881: `done/reviewer__PR920@8df3d82.md`, `done/reviewer__PR885@0e14b75.md`, `done/reviewer__PR881@d7b3bb9.md` all PASS. vehicle verifier: `done/verifier__RUN_BRANCH_batch_2026-11-07-m3@62a3f85.md` 62a3f85 16/16 | vehicle: verifier run names 62a3f85 = head; no reviewer file for the vehicle | BATCH 3 of 3 |
| 973 | 45bd655 | bundled 878 896 901 903 906 922 923 925 926 928 931 932: `done/reviewer__PR{878@dc7247b,896@ecf187e,901@40a9338,903@7835986,906@53a0ed0,922@dc89222,923@41b0d90,925@cd3fcf4,926@b295485,928@bdf220e,931@9a6d843,932@effb1ec}.md`; 11 PASS, 903 PASS WITH CONDITIONS (condition met per `inbox/coordinator/20261108-0310-fp-merge-a-batch-m4a-landed.md`). vehicle verifier: `done/verifier__RUN_BRANCH_batch_2026-11-08-m4a@45bd655.md` | vehicle: verifier run names 45bd655 = head | BATCH 12 of 12 |
| 975 | 16fc921 | reviewer (vehicle): `done/reviewer__PR975@16fc921.md` 16fc921 PASS (post-merge, read-only, fp-reviewer-a, 2026-11-08T17:36Z). bundled 924 921 919 918 917 911 910 909 895: `done/reviewer__PR{924@e8b26ea,921@4237a49,919@51c1d69,918@3372a6f,917@110c486,911@14e9647,910@8a522b8,909@8a24e2f,895@bd584ad}.md` all PASS. verifier: `done/verifier__RUN_BRANCH_batch_2026-11-08-m4b@16fc921.md` | yes (16fc921); post-merge | REVIEWED on merged head (post-merge; bundled 9 of 9) |
| 1012 | df7fd3a | bundled 943 942 940 938 705: `done/reviewer__PR{943@c4b56f9,942@8ad16b8,940@b69b7c6,938@ca93cb8,705@6d28de4}.md` all PASS. vehicle verifier: `done/verifier__RUN_BRANCH_batch_2026-11-08-m6b@df7fd3a.md` | vehicle: verifier run names df7fd3a = head | BATCH 5 of 5 |
| 1016 | 347b720 | reviewer (vehicle): `done/reviewer__PR1016@347b720.md` 347b720 PASS (post-merge, 19/19 mutants killed). bundled 702 405: `done/reviewer__PR702@41443a2.md` PASS; `done/reviewer__PR405@fc6b549.md` BLOCK on source head (no merge base; patch itself 25/25 mutants killed; recommended clean cherry-pick rebuild), rebuilt cherry-pick landed in 347b720. verifier: `done/verifier__RUN_BRANCH_batch_2026-11-08-m8b@347b720.md` | yes (347b720); post-merge. 405's reviewed sha fc6b549 is the source head, not the cherry-pick | REVIEWED on merged head (post-merge; bundled 2 of 2 have a record: 1 PASS, 1 BLOCK-on-lineage) |
| 1017 | 7a42cb9 | bundled 941: `done/reviewer__PR941@87454bf.md` PASS. vehicle verifier: `done/verifier__RUN_BRANCH_batch_2026-11-08-m9b@7a42cb9.md` | vehicle: verifier run names 7a42cb9 = head | BATCH 1 of 1 |
| 1049 | 117ee0f | bundled 933 956 961 962 966 967 968 969 970 971 972 974 994 998 1000: `done/reviewer__PR{933@d6cbe58,956@dfcc6b8,961@63c9655,962@60c4e1b,966@27c4b45,967@52746cb,968@141973f,969@94af499,970@5a3f8de,971@ad0addb,972@122b02b,974@24d5f2e,994@f45cf20,998@6a15fda,1000@4ad223d}.md`; 14 PASS, 956 PASS WITH CONDITIONS. vehicle verifier: `done/verifier__RUN_BRANCH_batch_2026-11-09-m5a@117ee0f.md` | vehicle: verifier run names 117ee0f = head | BATCH 15 of 15 |
| 1052 | e6d88b1 | bundled (17, list in `inbox/coordinator/20261109-1241-fp-merge-b-batch-m12b-landed.md`) 875 892 953 957 960 976 977 978 979 980 982 983 985 986 987 990 1013: `done/reviewer__PR{875@9b3bd13,892@3bf9c88,953@e1a1b85,957@d5c3ab0,960@4fe76a8,976@f3f0c36,977@d5bb955,978@c5b8daa,979@9beb816,980@344880c,982@bf83993,983@2e91276,985@1d9e016,986@953af0d,987@9c023ec,990@23918f1,1013@75eb8d2}.md` all PASS. vehicle verifier: `done/verifier__RUN_BRANCH_batch_2026-11-09-m12b@e6d88b1.md` | vehicle: verifier run names e6d88b1 = head | BATCH 17 of 17 |
| 1054 | df37605 | reviewer: `done/reviewer__PR1054@df37605.md` df37605 PASS (pre, 2026-11-10T06:06Z); `done/reviewer__PR1054@b223c7d.md` b223c7d PASS WITH CONDITIONS (earlier head). verifier: `done/verifier__RUN_PR1054@df37605.md` 16/16. post-merge: `inbox/coordinator/20261121-2237-don.reviewer-postmerge-pr1054.md` df37605 PASS; GitHub comment pull/1054#issuecomment-7070304880 | yes (df37605) | REVIEWED on merged head |
| 1055 | 5f33067 | no pre-merge record. post-merge: `inbox/coordinator/20261121-2235-don.reviewer-postmerge-pr1055.md` 5f33067 PASS WITH CONDITIONS; GitHub comment pull/1055#issuecomment-7070291726 | yes (5f33067); post-merge only | REVIEWED on merged head (post-merge only) |
| 1057 | 8eeb4bc | no pre-merge record on this head. PR body cites a PASS WITH CONDITIONS on PR 1056 b79742e; no `R-PR1056` / `b79742e` file in comms (not in source). Predecessor PR 1041: `done/reviewer__PR1041@cd20694.md` PASS WITH CONDITIONS (different head, not counted). post-merge: `inbox/coordinator/20261121-2111-don.reviewer-postmerge-pr1057.md` 8eeb4bc PASS WITH CONDITIONS; GitHub comment pull/1057#issuecomment-7069301004 | yes (8eeb4bc); post-merge only | REVIEWED on merged head (post-merge only) |
| 1058 | e2d1511 [head e10a88f] | none. grep of comms for R-PR1058, PR1058@, PR 1058, #1058, head sha e10a88f: no hit. GitHub comments: none | n/a | NO RECORD |
| 1059 | 78498a9 [head c3a538f] | no pre-merge record. post-merge: `inbox/coordinator/20261121-2242-don.reviewer-postmerge-pr1059.md` merge 78498a94d PASS; GitHub comment pull/1059#issuecomment-7070362154 (URL as cited in that file) | yes (squash commit 78498a9); post-merge only | REVIEWED on merged head (post-merge only) |
| 1060 | c07e5a9 [head c1e8cc9] | no pre-merge record. post-merge: `inbox/coordinator/20261121-2242-don.reviewer-postmerge-pr1060-1063.md` verdict on 5461995 (covers c07e5a993 and 546199519) PASS WITH CONDITIONS; GitHub comment pull/1060#issuecomment-7070363873 | yes (squash commit c07e5a9 measured within the 5461995 review); post-merge only | REVIEWED on merged head (post-merge only) |
| 1063 | 5461995 [head 2d83cef] | no pre-merge record (`inbox/coordinator/20261121-2052-don.reviewer-pr1061-db8fb2b.md` reviews superseded PR 1061, not 1063). post-merge: `inbox/coordinator/20261121-2242-don.reviewer-postmerge-pr1060-1063.md` 5461995 PASS WITH CONDITIONS; GitHub comment pull/1063#issuecomment-7070362840 | yes (5461995); post-merge only | REVIEWED on merged head (post-merge only) |
| 1064 | 123b71b [head f7ea314] | none in comms. The PR body claims "Independent review: PASS on f7ea31492" but no file, inbox report or GitHub comment records it (only mention in comms: `inbox/coordinator/20261121-2242-don.reviewer-postmerge-pr1060-1063.md` and `...pr1062-2bd9451.md`, which review other PRs). GitHub comments: none | n/a | NO RECORD |
| 1069 | 6bc2c80 [head 53b88e0] | no pre-merge record in comms (PR body cites an unrecorded "independent Sonnet review ... SHIP-WITH-CONDITIONS on 77f6e68ea", an earlier head). post-merge: `inbox/coordinator/20261121-2105-don.reviewer-postmerge-pr1069.md` 6bc2c80f PASS WITH CONDITIONS; GitHub comment pull/1069#issuecomment-7069231968 | yes (squash commit 6bc2c80); post-merge only | REVIEWED on merged head (post-merge only) |
| 1070 | 750824b [head e1efa94] | none. Only mention: `inbox/coordinator/20261121-2236-don.reviewer-handover.md` lists a post-merge review of PR 1070 as "in flight" at handover; no verdict file. GitHub comments: none | n/a | NO RECORD |
| 1071 | 507f010 [head 4a3c48f] | no pre-merge record. post-merge: `inbox/coordinator/20261121-2234-don.reviewer-postmerge-pr1071.md` 507f0109c PASS; GitHub comment pull/1071#issuecomment-7070271341 (URL as cited in that file) | yes (squash commit 507f010); post-merge only | REVIEWED on merged head (post-merge only) |
| 1073 | e143038 [head 173792a] | no pre-merge record (PR body: "Draft, Don's named yes needed to merge"). post-merge: GitHub comment pull/1073#issuecomment-7069250646 e143038e PASS WITH CONDITIONS; no comms verdict file (comms only has follow-up cards `inbox/coordinator/20261121-2329-bob.the.builder-replay-token-echo.md`) | yes (squash commit e143038); post-merge only | REVIEWED on merged head (post-merge only) |
| 1074 | ba86175 [head 7ccdc12] | none in comms. PR body claims "Independent review (Opus): SHIP on 7ccdc12" but no record exists. `inbox/coordinator/20261121-2236-don.reviewer-handover.md` lists a post-merge review of PR 1074 as "in flight"; no verdict file. GitHub comments: none | n/a | NO RECORD |
| 1075 | 95cd964 [head 3de26bf] | none (excluding roley.reviewer). Only `WORKLIST.tsv` follow-up cards citing roley.reviewer's review, which is excluded. GitHub comments: none | n/a | NO RECORD |
| 1076 | 787de47 [head 224e33e] | no pre-merge record. post-merge: `inbox/coordinator/20261121-2106-don.reviewer-postmerge-pr1076.md` 787de47 BLOCK as merged (integrity defect, fixed by #1078); GitHub comment pull/1076#issuecomment-7069234243 | yes (squash commit 787de47); post-merge only | REVIEWED on merged head (post-merge only; verdict BLOCK) |
| 1078 | cb7a94f [head f8bfa54] | no pre-merge record in comms (PR body cites an unrecorded Opus SHIP). post-merge: `inbox/coordinator/20261121-2100-don.reviewer-postmerge-pr1078.md` cb7a94f8 PASS WITH CONDITIONS; GitHub comment pull/1078#issuecomment-7069166982 | yes (squash commit cb7a94f); post-merge only | REVIEWED on merged head (post-merge only) |

## Count summary (computed from the table; 2 + 12 + 6 + 5 = 25)

| corrected status | n | PRs |
|---|---|---|
| REVIEWED on merged head, pre-merge | 2 | 837, 1054 |
| REVIEWED on merged head, post-merge only | 12 | 975, 1016, 1055, 1057, 1059, 1060, 1063, 1069, 1071, 1073, 1076, 1078 |
| REVIEWED on earlier head (only) | 0 | none (837 and 1054 also have earlier-head reviews, but each has one on the merged head) |
| BATCH k of m | 6 | 950 (3 of 3), 973 (12 of 12), 1012 (5 of 5), 1017 (1 of 1), 1049 (15 of 15), 1052 (17 of 17) |
| NO RECORD | 5 | 1058, 1064, 1070, 1074, 1075 |

Bundled PRs overall (including the bundled PRs of 975 and 1016): 3+12+9+5+2+1+15+17 = 64 bundled PRs, 64 with a reviewer done file. Verdict mix: 61 PASS, 2 PASS WITH CONDITIONS (903, 956), 1 BLOCK on source-head lineage (405, patch itself clean 25/25; rebuilt as cherry-pick and covered by `done/reviewer__PR1016@347b720.md` PASS). GitHub was not needed for these: every bundled PR has a comms reviewer file.

## Findings and caveats
1. The audit's claim "25 of 25 had no review on record" is wrong. 20 of 25 have a record on the comms branch or in GitHub comments: 2 pre-merge reviewer files on the merged head, 12 post-merge reviews on the merged head, and 6 batch vehicles whose 64 bundled PRs each have a reviewer done file.
2. The audit's "no PR comment" claim is also wrong for 11 PRs: don.reviewer filed GitHub comments on 2026-11-21 for 1054, 1055, 1057, 1060, 1063, 1069, 1073, 1076, 1078 (fetched via the GitHub MCP) and 1059, 1071 (URLs cited in the comms files, not fetched). PRs 1058, 1064, 1070, 1074, 1075 have no comments (fetched; 1059, 1071 not fetched).
3. Most of the 12 "post-merge only" records were filed by don.reviewer on 2026-11-21, after the audit's window. They are not pre-merge gates. Only 837 and 1054 (pre-merge reviewer PASS on the merged head) and the batch bundles satisfy a pre-merge review. 975 and 1016 are post-merge (fp-reviewer-a, 2026-11-08); their bundled PRs have pre-merge PASS files.
4. Batch vehicles (950, 973, 1012, 1017, 1049, 1052) have a verifier run on the merged head (path in the table) but no reviewer file for the vehicle itself; the status BATCH k of m rests on the bundled PRs' reviewer files. The landed notes state the source heads were unchanged and each had a reviewer PASS naming its head (`inbox/coordinator/20261108-0240-fp-merge-a-batch-m3-landed.md` and the sibling landed notes above). I did not independently compare each bundled reviewer sha7 with the bundled PR's head on GitHub (not verified).
5. PR 1076 was reviewed post-merge with verdict BLOCK as merged; its defect was fixed by 1078 (`inbox/coordinator/20261121-2106-don.reviewer-postmerge-pr1076.md`).
6. NO RECORD means: no file in the comms extract (excluding roley.reviewer) matching R-PR<n>, PR<n>@, PR <n>, #<n>, reviewer__PR<n> or the PR head sha7 as a review, and no GitHub comment or review fetched. PRs 1064 and 1074 have review claims in their PR bodies (PASS on f7ea31492; SHIP on 7ccdc12) that I could not corroborate; PRs 1070 and 1074 were "in flight" at the don.reviewer handover. 1075 has roley.reviewer follow-up cards only.
7. GitHub PR get did not return merge_commit_sha; the merged sha for squash PRs is from `git log origin/main` subjects, and for fast-forward PRs equals the PR head (PR get head.sha = commit named in the landed notes).
