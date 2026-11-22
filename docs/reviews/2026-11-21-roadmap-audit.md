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

## (4) Post-merge reviews of merges with no review on record (roley.reviewer)

This section is added on main by #1108 (pending). It is repeated here so this PR stands alone. Run on the merge commit, per GO-LIVE-LOOP reviewer fallback (b).

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
