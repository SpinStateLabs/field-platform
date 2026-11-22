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
