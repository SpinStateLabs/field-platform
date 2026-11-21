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
