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

### (4c) Post-merge reviews, batch 3 (roley.reviewer, 2026-11-22)

This batch also carries corrections promised on #1108 and #1109:
- the #1057 c5 test diff is +161/-2, not +163;
- session scratch paths (`/tmp/claude-0/...`) cited in batches 1 and 2 are not retained, and the probe and mutant scripts are described in the text but were never committed;
- correction row 1070 is no longer "no record": don.reviewer filed a post-merge PASS WITH CONDITIONS at 2026-11-22T00:48Z, and roley.reviewer's independent post-merge review agrees.

### #1054 post-merge (roley.reviewer, df37605)

**VERDICT: PASS WITH CONDITIONS on df376056d** (conditions gate the first live ARMING run, i.e. `allow_already_armed=False`; no revert needed: the only in-repo caller uses the no-op path). Confidence in verdict: MEDIUM.

#### Corrections to the brief (first)
1. "Actions driver" is NOT GitHub Actions. `Stage2Actions` implements `stage_controller.Actions` (the controller's step driver protocol), `tools/stage2_driver.py:76-77`, `tools/stage_controller.py:103-104`. The PR adds no `.github/` file (`git diff --stat e6d88b167 df376056d`: 2 files, tools/ only). Attacks on Actions logs and workflow_dispatch inputs are therefore N/A for this PR (HIGH).
2. "No review on record" is true only for GitHub reviews. In-repo comms hold three reviews: R-PR1054-b223c7d (PASS WITH CONDITIONS, referenced in commit aa60f02d2), R-PR1054-df37605 PASS (commit ddfaf910a, `comms/inbox/coordinator/20261110-0606-fp-reviewer-a-r-pr1054-df37605.md`), a 16/16 suite verifier run (commit 824ec1975), and a prior post-merge PASS by don.reviewer on 2026-11-21 (commit 58523145b) (HIGH).
3. Merge sha: the PR was merged by fast-forward; main's first-parent history contains b223c7d9d then df376056d (`git log --first-parent main`), and PR head sha = df376056db3a6e6c8b54fb865251408ceed7249a (GitHub MCP get). There is no separate merge commit; the merge sha is df376056d (HIGH).
4. The PR was merged while marked draft (`"draft":true,"merged":true`, GitHub MCP get) (HIGH).

#### Scope (HIGH)
- PR = 2 commits, fast-forwarded: b223c7d9d (driver + 16 tests), df376056d (tests only, C1/C2). `git diff --stat e6d88b167 df376056d`: `tools/stage2_driver.py` +147, `tools/tests/test_stage2_driver.py` +304.
- `tools/stage2_driver.py`, `tools/stage_controller.py` and the test file are byte-identical on current main (`git diff --stat df376056d main -- <3 files>` prints nothing).
- Workflows read (read-only): `.github/workflows/ci.yml` only; triggers `push: [main]` and `pull_request` (ci.yml:7-10), no `workflow_dispatch`; it runs `pytest -q tools/tests` (ci.yml:74), which is how the new test file reaches CI. No workflow names `stage2_driver`.

#### Attack suite (local fakes only)
File: `(session scratch, not retained)` (34 tests; `test_holds_*` = defence holds, `test_finding_*` = pins a weakness as current behaviour).
Command: `PM1054_ROOT=<wt> python -m pytest -q test_attack_1054.py` at df376056d -> last line `34 passed in 1.56s`.

| # | Attack | Result | Evidence | Conf |
|---|---|---|---|---|
| 1 | Re-arm armed estate (override present) | HOLDS: `Refused("stage2_already_armed")`, zero mutating calls, one `refused` row, no `stage_start` | stage2_driver.py:137-144; test_holds_rearm_refused_before_any_mutation | HIGH |
| 1b | Re-arm an estate that is armed by REQUIRE flag (Stage-3 shape: override gone, mode enforce) | FINDING F2: not seen as armed; Stage 2 writes the override and `up`s the kill-switch; an abort ends `rollback_failed` because the verify hard-codes `log-only` | stage2_driver.py:117-119, 138; test_finding_stage3_estate_* | HIGH (code), LOW (likelihood: Stage 3 is not armed today, not verified) |
| 2 | Partial failure mid-arm (write ok, `up` raises; write raises; counter rise) | HOLDS: rolled back to exactly (no override, log-only) on a log-only start; armed+allow abort leaves enforce + override | test_holds_recreate_raises_*, test_holds_write_override_raises_*, test_holds_counter_rise_*, test_holds_armed_allow_abort_never_disarms | HIGH |
| 2b | "Restores the prior mode exactly" | PARTIAL: the driver never snapshots the prior mode; it assumes prior = log-only (fresh) or enforce (armed). Exact only for those two states | stage2_driver.py:117-119 | HIGH |
| 3 | Rollback failing (delete raises; `up` without raises; delete silently no-ops) | HOLDS: `rollback_failed`, one attempt, no retry, next run refused `rollback_failed_unresolved` (with allow flag); silent no-op delete caught by verify | stage_controller.py:456-485; test_holds_delete_override_fails_*, test_holds_recreate_without_fails_*, test_holds_delete_that_silently_* | HIGH |
| 3b | Retry after failed rollback without allow flag | FINDING F5 (LOW): refused as `stage2_already_armed`, masking `rollback_failed_unresolved` (driver pre-flight runs before controller preconditions) | stage2_driver.py:137-144 vs stage_controller.py:292-294; test_finding_retry_after_failed_rollback_* | HIGH |
| 4 | Vacuous verify: mode | HOLDS: exact string compare; `ENFORCE`, `enforce `, `enforce\n`, `""`, `None` all fail closed | stage2_driver.py:112, 118; test_holds_mode_must_match_exactly (5 params) | HIGH |
| 4b | Vacuous verify: file | HOLDS: truthy non-bool `override_present` ("False", "no") is treated as armed and refused (fail safe); verify uses `!=` against a bool so a non-bool fails | test_holds_truthy_non_bool_override_* | HIGH |
| 4c | Vacuous verify: health | FINDING F3 (MEDIUM): `not healthy()` truthiness; `"unhealthy"` or `{"registry": "down"}` passes every health check and the run completes. One bool, not checked against `expected_services` | stage2_driver.py:114, 120; test_finding_truthy_non_bool_health_*, test_finding_a_single_boolean_health_* | HIGH |
| 5 | Secrets in logs / argv | HOLDS: no CLI, no print, no subprocess, no environ in the module; nothing on stdout/stderr; go sentence stored only as len + sha8 | test_holds_nothing_printed_*, test_holds_module_has_no_cli_*; stage_controller.py:260-262 | HIGH |
| 5b | Exception text leakage | FINDING F4 (LOW): a raise from `override_present()` in the pre-flight is outside every try; the estate's own message escapes (fake token in test) and no `refused` row is written | stage2_driver.py:137-138; test_finding_preflight_exception_escapes_raw_* | HIGH |
| 6 | workflow_dispatch shell injection | N/A: no workflow runs the driver; no `workflow_dispatch` in any workflow | test_holds_no_workflow_runs_the_driver_*; ci.yml:7-10 | HIGH |
| 7 | Timeouts | FINDING F6 (MEDIUM, design): no timeout in driver or controller step loop; a hung `up` blocks indefinitely holding the run lock (second run gets `run_in_progress`). Delegated wholly to the Stage2Estate | stage2_driver.py:88-126; stage_controller.py:445-454; test_finding_a_hanging_estate_call_* | HIGH |
| 8 | Wrong (production) estate by typo | FINDING F7 (MEDIUM): `build_sha` is checked against the records only (stage_controller.py:278-289), never the estate; `Stage2Estate` has no identity/sha method; any estate object is armed. A typo'd records path is refused (`alerts_not_proven`) | test_finding_nothing_binds_*; test_holds_records_path_typo_refuses | HIGH (code); MEDIUM (that the future coordinator estate does not bind it, not in source) |
| 9 | Idempotency on retry | HOLDS: retry after `completed` refused, nothing mutated; retry after clean rollback arms once | test_holds_retry_after_* | HIGH |
| 9b | Audit trail of `allow_already_armed` | FINDING F8 (LOW): `step_done write_override`, `step_done recreate_killswitch`, `stage_done` are written though nothing ran; no row marks no-op/armed_before. The only in-repo caller (main `tools/stage2_estate_readonly.py:464-465`) always uses this path | stage2_driver.py:91-92; stage_controller.py:438; test_finding_allow_already_armed_records_* | HIGH |
| 10 | Two runs at once | HOLDS for overlapping runs (second refused `stage2_already_armed` or `run_in_progress`; one write) | test_holds_two_simultaneous_runs_* | HIGH |
| 10b | Pre-flight TOCTOU | FINDING F1 (MEDIUM): pre-flight reads the override BEFORE the run lock. Run B reads "not armed" and stalls; run A arms and finishes; B takes the lock, preconditions pass (last word `stage_done`), B re-arms with `armed_before=False`, and B's abort rollback deletes the override: A's armed Stage 2 is disarmed. This is exactly the hazard the PR exists to prevent (card item 4) | stage2_driver.py:137-147 vs stage_controller.py:380-386; test_finding_preflight_toctou_* | HIGH (code path reproduced with real flock); LOW (likelihood: needs two concurrent live runs by the coordinator) |

#### Mutants (worktree only, `git checkout -- .` after each; script `(session scratch, not retained)`, data `(session scratch, not retained)`)
Target `tools/stage2_driver.py` at df37605. PR tests = `tools/tests/test_stage2_driver.py` (baseline 22 passed). ATK = my attack file (baseline 34 passed).

| Mutant | Behaviour | Change | PR tests | PR killed | ATK killed |
|---|---|---|---|---|---|
| m01 | B1 armed pre-flight | refusal condition never true | 1 failed, 21 passed in 1.93s | yes | yes |
| m02 | B1 armed pre-flight | pre-flight reads armed=False | 6 failed, 16 passed in 0.16s | yes | yes |
| m03 | B1 armed pre-flight | pre-flight only when not live | 7 failed, 15 passed in 0.18s | yes | yes |
| m04 | B1 armed pre-flight | raise Refused removed | 1 failed, 21 passed in 0.22s | yes | yes |
| m05 | B1 armed pre-flight | allow flag inverted | 6 failed, 16 passed in 0.22s | yes | yes |
| m06 | B2 armed no-op steps | no-op branch disabled | 5 failed, 17 passed in 0.18s | yes | yes |
| m07 | B2 armed no-op steps | delete_override not a no-op | 4 failed, 18 passed in 0.17s | yes | yes |
| m08 | B2 armed no-op steps | recreate_killswitch not a no-op | 5 failed, 17 passed in 0.16s | yes | yes |
| m09 | B2 armed no-op steps | armed_before never passed | 5 failed, 17 passed in 0.16s | yes | yes |
| m10 | B3 override from estate | always with override | 2 failed, 20 passed in 0.14s | yes | yes |
| m11 | B3 override from estate | always without override | 3 failed, 19 passed in 0.18s | yes | yes |
| m12 | B3 override from estate | inverted | 4 failed, 18 passed in 0.15s | yes | yes |
| m13 | B3 override from estate | from flag armed_before | 3 failed, 19 passed in 0.17s | yes | yes |
| m14 | B4 fail-closed forward checks | write_override check removed | 1 failed, 21 passed in 0.15s | yes | no |
| m15 | B4 fail-closed forward checks | forward mode check removed | 5 failed, 17 passed in 0.16s | yes | yes |
| m16 | B4 fail-closed forward checks | forward health check removed | 2 failed, 20 passed in 0.19s | yes | yes |
| m17 | B4 fail-closed forward checks | check exception passes | 1 failed, 21 passed in 0.14s | yes | yes |
| m18 | B4 fail-closed forward checks | unknown check step passes | 1 failed, 21 passed in 0.16s | yes | no |
| m19 | B4 fail-closed forward checks | wrong-stage check passes | 1 failed, 21 passed in 0.14s | yes | no |
| m20 | B6 rollback verify | override presence ignored | 2 failed, 20 passed in 0.15s | yes | no |
| m21 | B6 rollback verify | mode ignored | 1 failed, 21 passed in 0.14s | yes | yes |
| m22 | B6 rollback verify | health ignored | 2 failed, 20 passed in 0.16s | yes | yes |
| m23 | B6 rollback verify | always expects armed | 2 failed, 20 passed in 0.15s | yes | yes |
| m24 | B6 rollback verify | never expects armed | 1 failed, 21 passed in 0.18s | yes | yes |
| m25 | B5 refusal record / guards / dry run | refused row not written | 1 failed, 21 passed in 0.14s | yes | yes |
| m26 | B5 refusal record / guards / dry run | do() stage guard removed | 1 failed, 21 passed in 0.14s | yes | no |
| m27 | B5 refusal record / guards / dry run | unknown do() step accepted | 1 failed, 21 passed in 0.16s | yes | no |
| m28 | B5 refusal record / guards / dry run | dry run forced live | 1 failed, 21 passed in 0.14s | yes | no |

Totals counted from the table: applied 28, not applied 0; killed by PR tests 28, survived 0; killed by attack file 21.
Per behaviour (PR tests): B1 armed pre-flight 5/5; B2 armed no-op steps 4/4; B3 override from estate 4/4; B4 fail-closed forward checks 6/6; B6 rollback verify 5/5; B5 refusal record / guards / dry run 4/4. Worktree clean after run: `git status --porcelain` empty (HIGH).

#### Test runs at df376056d (private venv `(session scratch, not retained)`, Python 3.13.18, CI install recipe ci.yml:30-50)
- `python -m pytest -q tools/tests/test_stage2_driver.py` -> `22 passed in 0.35s` (HIGH). PR body says 16; 22 after the C1/C2 commit (stale body, already noted by don.reviewer).
- `python -m pytest -q tools/tests` -> `1 failed, 4480 passed, 12 skipped, 1 warning in 588.86s (0:09:48)` (HIGH). The failure is `test_deployment_agent_cli_manifest.py::test_the_manifest_validates_with_field_core_offline`: "delegation.expiry 2026-11-22 is in the past" (date-driven, file not touched by the PR); it fails identically on parent e6d88b167 (`1 failed in 0.15s`). Not attributable to #1054 (HIGH). It is a live main-red risk for CI today (MEDIUM; not checked on main CI).
- Attack file -> `34 passed in 1.56s` (HIGH).

#### In-repo callers and docs affected (on main; `git grep -n stage2_driver main`)
- `tools/stage2_estate_readonly.py` (:2, :62 import, :464-465 `run_stage2(..., allow_already_armed=True)`), added by the next commit b63a14779 and 5f33067ac (#1055). Only caller; never takes the arming path (HIGH).
- `tools/tests/test_stage2_estate_readonly.py` (tests of that caller) (HIGH).
- `docs/runbooks/v1.2-deploy-rollback.md:2333` ("Recording a Stage 2 that is already armed") states the controller writes `step_done` x2 and `stage_done` while nothing changes: consistent with F8, but the records rows themselves do not say so (HIGH).
- `tools/stage_controller.py` docstring ("this file ships none" of Actions) remains true of that file; not updated to point at the driver (LOW impact).

#### Findings, ordered (none is exploitable on main today because no caller arms live; MEDIUM)
- F1 MEDIUM: pre-flight TOCTOU (stage2_driver.py:137-147 runs before the lock, stage_controller.py:380-386). Reproduced: a stalled second run re-arms and its abort disarms the first run's armed Stage 2. Earlier review listed this as design note O1 without the consequence. Fix: re-read `override_present()` inside the lock (e.g. lazily in `Stage2Actions` on the first `do`, refusing on mismatch), or make preconditions refuse stage 2 when the last word is `stage_done`.
- F3 MEDIUM: health truthiness (stage2_driver.py:114, 120). Fix: `if self.estate.healthy() is not True`.
- F7 MEDIUM: estate identity / build sha not bound to the arming estate. #1055 binds it for the read-only path only.
- F6 MEDIUM (design): no timeout; a hung estate call holds the run lock indefinitely. Delegated to the coordinator's Stage2Estate; must be stated as a protocol requirement.
- F2 LOW-MEDIUM: armed-ness = override file only; a REQUIRE-on estate (Stage 3 shape) is re-armed and its abort reports `rollback_failed`. Fix: also refuse when `mode() == "enforce"` with no override, or when `stage_clean(3)`.
- F4 LOW: raw estate exception escapes the pre-flight, no `refused` row.
- F5 LOW: retry after a failed rollback reports `stage2_already_armed`, hiding `rollback_failed_unresolved`.
- F8 LOW: no-op steps recorded as `step_done` with no marker.
- Process: merged while draft; no GitHub review (in-repo comms reviews exist, see corrections).

#### Conditions (before any live run with `allow_already_armed=False`)
- C1: close F1 (override re-read under the run lock) with a test equivalent to `test_finding_preflight_toctou_*` turning red-then-green.
- C2: close F3 (`is True` health) with a truthy-string test.
- C3: the coordinator's arming `Stage2Estate` must bind estate identity + build sha (as #1055 does for reads) and bound every call with a timeout (F6, F7); record this in the runbook section.
- Non-blocking: F2, F4, F5, F8.

#### What held (HIGH, all by test)
Re-arm refusal on an override-present estate; exact restore on fresh-estate partial failure; armed+allow abort never disarms; rollback failure stops once, never retries, and blocks the next run; mode and file verify fail closed; no output, no argv, no secret, go sentence never stored; no workflow surface; retry after `completed` is a refusal; overlapping runs serialise; 28/28 mutants killed by the PR's own tests.

Hard limits honoured: no push, commit, merge, GitHub comment, estate request, Fly or Actions dispatch; fakes only; worktree removed at end.

### #1055 post-merge (roley.reviewer, 5f33067)

**Verdict: PASS WITH CONDITIONS** on merge sha 5f33067ac559bac5ed5f58a7664eff6034221ab2. No write path exists, and every build/identity/sha forgery refuses or aborts. The conditions are about whether `stage_done` attests to one consistent armed state, and about test pins. No revert. Confidence HIGH on read-only, MEDIUM on severity ranking.

**Corrections first**
1. The brief says the tool should check the exact build sha and the identity of all eight before `stage_done`. It does, via `healthy()` in the `recreate_killswitch` check (stage2_driver.py:111-115 -> stage2_estate_readonly.py:262-272). But override, mode, health and counters come from four separate probes (stage2_estate_readonly.py:229-250, one `snapshot()` each). Nothing re-reads "armed" after the mode probe, so `stage_done` can be written for an estate that is no longer armed (F1, F2). HIGH.
2. PR body says "194 passed" for the three test files. At the merge sha it is 197 (command below). MEDIUM: the body predates commit 5f33067ac.
3. "No GitHub review on record" holds. A prior post-merge review is in-repo (deb2414cd, don.reviewer, PASS WITH CONDITIONS). Its scope line says "four reads" and lists five (`snapshot`, `override_present`, `mode`, `healthy`, `counters`). It flags `status: true` accepted in its B4. I confirm that and add: any non-200 status with the correct strings passes **preflight**, and is caught only later by `healthy()` (E4/E5/E5b). HIGH.
4. Docstring `timeout=10` (stage2_estate_readonly.py:121) is per socket operation, not per request. A slow-drip `/health` held one service for ~26 s (R5). HIGH.

- Merge sha: 5f33067ac559bac5ed5f58a7664eff6034221ab2 (GitHub `pull_request_read get`: merged true, head sha 5f33067ac, base df376056d; no merge commit: `git log --format='%H %P'` shows b63a14779 parent df376056d, 5f33067ac parent b63a14779, main first-parent contains 5f33067ac). Fast-forward. HIGH.
- Worktree: (session scratch, not retained) (detached at 5f33067ac). Venv: (session scratch, not retained) Python 3.13.18, installs per .github/workflows/ci.yml:30-50 with the repo constraints.
- A prior post-merge review exists (deb2414cd, comms/inbox/coordinator/20261121-2235-don.reviewer-postmerge-pr1055.md, PASS WITH CONDITIONS). This review is independent; agreements/disagreements are noted at the end.

#### Tests on the merge sha (venv above)
| Command | Last line |
|---|---|
| `python -m pytest -q tools/tests/test_stage2_estate_readonly.py tools/tests/test_stage2_driver.py tools/tests/test_stage_controller.py -p no:cacheprovider` | `197 passed in 5.44s` |
| `python -m pytest -q tools/tests -p no:cacheprovider` | `1 failed, 4532 passed, 12 skipped, 1 warning in 587.36s (0:09:47)` |

The one failure is `test_deployment_agent_cli_manifest.py::test_the_manifest_validates_with_field_core_offline`: `'delegation.expiry 2026-11-22 is in the past'`. A date-dependent fixture expiring today (2026-11-22), in a file PR #1055 does not touch (`git diff --stat df376056d 5f33067ac -- <that file>` is empty). Not attributable to #1055. HIGH.
PR body correction: it claims "194 passed" for the three files; at the merge sha it is 197 (the second commit added tests after the body was written). MEDIUM (inferred from commit order).

#### Attack cases (executable, local fakes only)
Harness: (session scratch, not retained) (stub transports + loopback `ThreadingHTTPServer` on 127.0.0.1; the real generated probe is run with local `bash` and a temp `HOME`; fake go sentence; no estate contacted). Full output: (session scratch, not retained)
`python -I attacks.py` last line: `TOTAL 58 cases, 49 OK, 9 FINDING: ['A3-local-writes', 'E6b-all-status-float', 'D6-library-no-sha', 'C6-library-subset', 'F1-disarm-after-mode-read', 'F2-no-consistent-snapshot', 'F5-replay-accepted', 'R2-single-forger-accepted', 'R3-redirect-followed']`

| Area | Cases | Held | Finding |
|---|---|---|---|
| Read-only (A1 x3, A2, A3, A4, A5, R1) | 8 | 7 | A3 |
| Stale/forged /health: build + identity (B1-B7, R2, R3, F5) | 10 | 7 | R2, R3, F5 |
| Partial service lists (C1-C6) | 6 | 5 | C6 |
| Sha prefix (D1-D6) | 6 | 5 | D6 |
| Identity spoofing via fields (E1-E5, E5b, E6b, E7-E9, R4) | 11 | 10 | E6b |
| TOCTOU (F1-F4) | 4 | 2 | F1, F2 |
| Secrets in output (G1-G6) | 6 | 6 | - |
| Retry/timeout (H1, H2 x3, H3, H4, R5) | 7 | 7 | - |
| **Total (counted from rows)** | **58** | **49** | **9** |


#### Findings
| # | Sev | Finding | Evidence | Conf |
|---|---|---|---|---|
| F-1 | MEDIUM | **Composite, not atomic, armed check (TOCTOU).** A live run makes 9 probes (preflight; run_stage2 override; baseline counters; write_override check; counters; then override, mode, healthy and counters as 4 separate probes). `stage_done` follows probe 9 with no armed re-read. F1: the estate disarmed after probe 7 -> rc 0, `stage_done`. F2: after preflight, no probe saw override AND enforce together -> rc 0, `stage_done`. | attacks.out F1, F2; stage2_driver.py:107-115; stage_controller.py:439-443 | HIGH |
| F-2 | LOW-MED | **Identity is self-asserted and unauthenticated.** One loopback process answering all eight paths with the right `service`/`build_sha` strings passes preflight and `healthy()` (R2). Redirects are followed, including to another loopback port serving a forged body (R3; urllib's default `HTTPRedirectHandler`, stage2_estate_readonly.py:117). Same trust model as estate_probe, so not a regression. | attacks.out R2, R3 | HIGH |
| F-3 | LOW | **No nonce or time binds an answer to its request.** A transport replaying one cached `S2PROBE` line for every probe records `stage_done` (F5). Only matters if the transport is not trusted (pg-run is the operator's wrapper). | attacks.out F5; :216-227 | HIGH |
| F-4 | LOW | **Preflight is weaker than the driver check.** `_identity_ok` skips non-200 rows (:258-260), so a service with status `True`/`"200"`/503 and the correct strings passes preflight. The run then aborts in the driver and writes `rollback_step` x2 + `rollback_failed`, with a "ROLLBACK FAILED ... act by hand" alert, from a read-only tool. That fails closed, but the result is a noisy alarm instead of exit-2 `refused`. The runbook documents this (v1.2-deploy-rollback.md:2345-2350). Also, status `200.0` is accepted everywhere (E6b; `200.0 == 200`; reachable only via a forged transport answer). | attacks.out E4, E5, E5b, E6b, F4 | HIGH |
| F-5 | LOW | **The library defaults are weaker than the CLI.** `ReadOnlyStage2Estate(..., expected_build_sha=None)` skips the build check (D6; :266-268). A 2-service estate given to `run_stage2` completes while ledger is down (C6). Today only the CLI and the tests construct it (callers below). | attacks.out D6, C6 | HIGH |
| F-6 | INFO | **Writes beyond the records file.** `<records>.lock` (stage_controller.py:225-231; persists, empty; A3). pg-run temp script, mode 0600, removed in `finally` (:328-338; A5). pg-run's self-copy under `~/.stage0-run/` on the estate host (docstring :29-32; pg-run is not in the repo, NOT VERIFIED). No estate HTTP write: only GET, no credential header, 0 body bytes, `HTTP_PROXY` ignored, HOME tree unchanged (R1). | attacks.out A2, A3, A5, R1 | HIGH (local); LOW (pg-run) |
| F-7 | LOW | **Timeouts are bounded only by the transport.** The probe has a 10 s per-socket-op timeout. `subprocess.run(timeout=timeout+120)` allows up to 1020 s per probe (:311, :333) x 9 probes. There is no retry anywhere: transport timeout or non-zero rc -> one call, then `refused: probe_transport_failed` (H1, H3). A mid-run failure aborts, with no `stage_done` (H4). | attacks.out H1-H4, R5 | HIGH |
| - | OK | **Secrets.** The go sentence is never in stdout or records (G1, G5). An argv go sentence is not echoed (G2). Transport/`/health` strings are not echoed (G3, G4). The probe has no credential or env read (G6). | attacks.out G1-G6 | HIGH |
| - | OK | **Sha prefix.** A 7-char `--build-sha` with `--live` -> `live_needs_full_build_sha` (D1). A reported 7-char, upper-case, trailing-space or 64-char-truncated sha -> `build_sha_mismatch` (D2-D5). A sha changing mid-run -> no `stage_done` (F4). | attacks.out | HIGH |

#### Mutants (worktree only; `git checkout -- .` after each; every replacement asserted to apply exactly once; file byte-identical after; `git status --porcelain` empty at end)
Runner: (session scratch, not retained) results: (session scratch, not retained) Oracle 1 is `pytest -q -x tools/tests/test_stage2_estate_readonly.py`. Oracle 2 is attacks.py, which kills a mutant when its outcome set differs from baseline (CB9 includes the real loopback group).
| Behaviour (claimed in PR body/docstring) | Mutants | Killed by PR tests | Killed by PR tests or harness | PR-test survivors |
|---|---|---|---|---|
| CB1 writes raise | 4 | 3 | 3 | M4 |
| CB2 one probe per read, never cached | 4 | 4 | 4 | - |
| CB3 mode from kill-switch /health | 4 | 4 | 4 | - |
| CB4 healthy = 200 + identity + exact build | 4 | 3 | 4 | M13 (harness kills) |
| CB5 CLI refusals | 6 | 6 | 6 | - |
| CB6 not live: one plan row, no probe | 4 | 3 | 4 | M26 (harness kills) |
| CB7 go sentence: file/stdin, never printed | 4 | 4 | 4 | - |
| CB8 --live stub needs stub records | 4 | 2 | 2 | M32, M34 |
| CB9 probe: GET only, no proxy, plain inputs, bounded | 6 | 4 | 5 | M35 (harness kills), M40 |
| **Total (summed from rows)** | **40** | **33** | **36** | |

Survivor notes: M4 (`RuntimeError`->`Exception` base) is equivalent here: the driver catches `Exception` (stage2_driver.py:124; stage_controller.py:450). M13 (status==200 dropped) is near-equivalent for real probe output, because urllib raises on non-2xx before the body is read, so `service` is never set; it matters only for a forged answer. **M34 (stub run gets the process alert env)** means a `--stub-snapshot` run could send real `stage_transition` alerts, and no test pins it. **M35 (`ProxyHandler({})` removed)** means an `HTTP_PROXY` on the host would route the `/health` GETs; only R1 pins it. M32 (stub check on full path vs file name) and M40 (64-char truncation) are not pinned.

#### In-repo callers affected
Only `tools/tests/test_stage2_estate_readonly.py` and the runbook paragraph `docs/runbooks/v1.2-deploy-rollback.md:2331-2351`: `grep -rl "stage2_estate_readonly\|ReadOnlyStage2Estate"` at 5f33067ac; same set on origin/main via `git grep`. It imports `stage2_driver` and `stage_controller` (:62-63), and neither changed in this PR (3 files: `git show --stat`). No commits since the merge touch these three tool files (`git log 5f33067ac..origin/main -- <files>` is empty). HIGH.

#### Conditions (follow-up cards, not a revert)
1. **C-1 (F-1, F-4):** take override, mode, identity, build and counters from ONE snapshot per check. Make preflight require `_healthy(snap)` (all eight 200 + identity + build). Add a final single-snapshot armed check before `stage_done` (e.g. a `check_armed()` on the estate that `recreate_killswitch` uses instead of four reads). Pin F1/F2 as tests.
2. **C-2 (F-2):** refuse redirects in the probe opener (an `HTTPRedirectHandler` subclass that raises). Pin R3.
3. **C-3 (tests):** pin M34 (stub run sends no alert), M35 (no proxy), M13 (a non-200 status is never healthy), M32 (stub check uses the file name) and E6b (an integer status only).
4. **C-4 (F-5):** make `expected_build_sha` required, and all eight enforced, in `ReadOnlyStage2Estate` itself, not only in the CLI.
5. **C-5 (F-3, optional):** a per-probe nonce echoed in the `S2PROBE` line.

#### Scope
Read fully: stage2_estate_readonly.py (478 lines), stage2_driver.py (147), stage_controller.py:128-175, 220-260, 260-490, runbook :2330-2352. Not read: the PR test file body (used as an oracle only), and pg-run.py (not in the repo). No GitHub comment, push, commit or estate request. Fake go sentence and fake strings only. The worktree is removed at the end.


### #1058 post-merge (roley.reviewer, e2d1511)

Merge commit (squash): e2d151110d5e5546b5f9ee6e091d61be01571823, merged 2026-11-13 by the PR author. Base 8eeb4bc72; compared against main ce1ffae89. Scope: STATE.md (+2 lines), tasks/next-session-portal.md (+2 lines). Docs only. Mutants do not apply to docs; a claims table replaces them.

**FORBID/CORRECT (first line):** the added STATE.md text says the old "GB10 is log_only burn-in" statement "was true on 2026-09-14". It was not: STATE.md:224-231 (Dogfood step 1, dated 2026-09-08) records that the GB10 "runs ENFORCE" and that the log-only pilot gate is "deliberately not being run there". The correction therefore misdates the error. [HIGH, STATE.md]

**OPPOSE (objections before verdict)**
1. The added sentence asserts live estate posture ("armed to enforce, Stage 3 REQUIRE, 2026-11-10") with no evidence in the repo. docs/DOSSIER.md:30 says estate deployment status is deliberately not stated in docs, and commit 968cc2c (2026-11-02, C-1134 class C8) scrubbed such lines. [HIGH]
2. The runbook requires a G21 gate record and a clean Stage 2 before Stage 3 (docs/runbooks/v1.2-deploy-rollback.md:2302-2304). The only 2026-11-10 repo evidence is Stage 2 tooling (b63a14779 "record an already armed Stage 2", 5f33067ac). Nothing records Stage 3. [HIGH]
3. The PR body says "Needs independent review before merge". GitHub get_reviews returns []. It was merged by its author, so the stated gate was skipped. [HIGH, GitHub MCP]
4. The correction is appended, not edited. STATE.md:347-348 still reads "GB10 remains the private burn-in estate (log_only)", which contradicts STATE.md:224-231 before and after this PR. [HIGH]

**ASSUMPTIONS**
1. The merge sha is the squash commit e2d1511; the PR head e10a88f is not on main. [HIGH]
2. Claims are judged against repo text only. No deployed service was queried, per the hard limits.
3. A public GitHub repo-metadata lookup is allowed. It is not a deployed service.

**REASONING**
1. `git diff e2d1511^ e2d1511` gives 4 added lines and 0 removed lines. Part (2) is therefore vacuous: nothing was removed, and no removal needs justifying.
2. Each added statement was split into atomic claims and checked at e2d1511 and at main. STATE.md, DOSSIER and tasks/ are identical at both for these facts.
3. README.md and ROADMAP.md contain no GB10 or burn-in posture statements (grep at main), so they cannot contradict. docs/DOSSIER.md:30 and :36 are the same-fact documents.

**Claims table**

| # | Claim (added text or commit message) | Verdict | Source | Conf |
|---|---|---|---|---|
| 1 | The "GB10 = log_only burn-in" sentence "was true on 2026-09-14" | FALSE | STATE.md:224-231 (ENFORCE since 2026-09-08); STATE.md:1311 (both estates armed 2026-09-14) | HIGH |
| 2 | GB10 "armed to enforce (Stage 3 REQUIRE, 2026-11-10)" | UNVERIFIABLE | No Stage 3 record in repo; DOSSIER.md:30 says "not in source" by policy; runbook :2302-2304 | HIGH |
| 3 | GB10 "is no longer only a burn-in estate" | TRUE (date basis wrong, see 1) | STATE.md:224-231; DOSSIER.md:36 (burn-in window not running by decision) | HIGH |
| 4 | "Fly remains the product estate" | TRUE | STATE.md:346-347 ("PRODUCT estate"); agents/ssl-*/SKILL.md:35-37 name both estates | MEDIUM |
| 5 | GitHub repo SpinStateLabs/force-field-console exists | TRUE | Public GitHub repo metadata (private=false) | HIGH |
| 6 | It was renamed from force-field-portal on 2026-11-12 | UNVERIFIABLE | Old name not reachable from this session (403, scope-limited); no rename record in repo | LOW |
| 7 | The local checkout is still the old path and its origin points at the new name | UNVERIFIABLE | Operator machine state, outside the repo | LOW |
| 8 | Older STATE.md entries keep the old name | TRUE | STATE.md:36-37; tasks/agent-usage.md:110,124,125 | HIGH |
| 9 | next-session-portal.md text below the note keeps the old name | TRUE | tasks/next-session-portal.md:5,34,56,93 | HIGH |
| 10 | Commit message: crosswalk TODO-CITE already resolved on main | TRUE | services/compliance-crosswalk/tests/test_regwatch_api.py:218-219 | HIGH |
| 11 | PR body: federation README documents fedbroker sign | TRUE | services/federation-broker/README.md:70 | HIGH |

Totals (counted from the table, 11 rows): TRUE 7 (rows 3,4,5,8,9,10,11), FALSE 1 (row 1), STALE 0, UNVERIFIABLE 3 (rows 2,6,7).

**Part 3, public-repo hygiene.** The diff contains no emails, hostnames, IPs, secrets or tokens. Both added lines contain a Windows user-profile path with the operator's local username (C:\Users\<username>\dev\...). That is low-grade personal data in a public repo. It matches existing precedent (STATE.md:238 and more, docs/runbooks/token-renewal.md:266), so this PR did not introduce a new class of leak. Commit trailers carry only noreply addresses. [HIGH]

**Part 4, contradictions.**
- STATE.md:347-348 (log_only burn-in) versus STATE.md:224-231 (ENFORCE since 2026-09-08). The PR leaves both standing and adds a third, misdated note.
- STATE.md:349 (enforce armed) versus DOSSIER.md:30 (deployment status not stated in docs, by policy). This is a policy conflict, not a factual one.
- README.md and ROADMAP.md: no conflict.

**CONCLUSION: PASS WITH CONDITIONS** on e2d1511. It is docs-only, purely additive, and the rename and crosswalk facts check out. The conditions are:
1. Fix row 1: change the validity date to 2026-09-08, or reword to "superseded by the 2026-09-08 dogfood decision at line 224".
2. Row 2: either cite an in-repo record (G21 gate record or Stage 3 stage_done) or delete the Stage 3 and date claim, to comply with the 968cc2c status-scrub policy. Until then it is an unverified security-posture claim.
3. Record this review on comms. The author-merge skipped the review the PR itself requested.
4. Optional: replace the username path in the two notes with a placeholder.
No BLOCK: no secret or runtime impact, and every defect is correctable in docs.


### #1064 post-merge (roley.reviewer, 123b71b)

**VERDICT: PASS WITH CONDITIONS on 123b71b5.** Corpus is clean, labels consistent, sweep deterministic, no non-test consumer today. Conditions: regression-only and synthetic-only are unguarded by any test (8/8 mutants survive), the sweep's config plumbing is unpinned (M11), and the PR body's review claim is uncorroborated.

**Subject.** Merge `123b71b508daa9b02db92ead53ab3fcfb84bcd7a` (squash, parent `546199519` = #1063), PR head `f7ea3149229fff4e953971bef1682845317707b5`, PR base `78498a94d` (#1059). Source: GitHub MCP `pull_request_read get`; `git log -1 --format=%P`. HIGH.
Files: `defence-shield/agent-incident-retro/src/agent_incident_retro/synth_corpus.py` (+65), `.../tests/test_synth_corpus_s4.py` (+35). `git diff f7ea31492 123b71b50 -- <both files>` is empty: merged content equals the PR head. HIGH.

#### Tests on the merge sha (venv (session scratch, not retained) Python 3.13.18; install per `.github/workflows/ci.yml:37,49` with integration constraints)
- `(cd defence-shield/agent-incident-retro && python -m pytest -q tests)` (ci.yml:96): `242 passed in 3.70s`. HIGH.
- `pytest -q tests/test_synth_corpus_s4.py tests/test_calibrate_s4.py`: `8 passed in 1.43s`. HIGH.
- GitHub check runs on the PR head: 7/7 success (tests 3.11-3.14, compose-smoke, compose-upgrade-smoke, fly-image-smoke). Source: `pull_request_read get_check_runs`. HIGH. Note: head was based on #1059, not #1063; the merged combination was not CI-tested pre-merge (inferred from parents; MEDIUM). My run above covers the merged tree.

#### ASSUMPTIONS
1. "Corpus" = the output of `generate_corpus()`; the PR adds no data files (only the 2 .py files above). HIGH (git show --stat).
2. Defaults (seed 11, 300/12/8) are the population that matters; non-default parameters are edge cases. MEDIUM.
3. "Real hostname/email" scan is pattern-based; I cannot prove absence of real data beyond the patterns, but every value is code-generated from literals I read in full. HIGH for this file pair.

#### REASONING
**(1) Sensitive content: NONE FOUND.** Generated seed-11 corpus (3050 lines, 320 clients) and both PR files scanned for AKIA/ASIA, sk_live/sk_test/rk_live, ghp_/gho_/ghs_/github_pat_, xox[abprs]-, -----BEGIN, JWT (eyJ..), AIza, email, phone, password/secret/token/api_key: 0 hits in all three. HIGH (grep -E -c). High-entropy (>=20 char) tokens: none. Every client IP is in RFC 5737 ranges (192.0.2/24, 198.51.100/24, 203.0.113/24); the only non-doc dotted quad is the Chrome version string in the UA. HIGH. No hostnames in the corpus. Targets are 8 page shapes plus two canonical test payloads (one SQLi, one XSS, imported from pre-existing `synth.py:34-35`) and a `/.env` probe. HIGH. No rotation needed.
**(2) Labels: CONSISTENT; balance matches the PR.** Counter = 300 benign / 20 rogue (12 pivoters + 8 cadence bots), equal to PR body "300 benign humans, 12 pivoters, 8 cadence bots". HIGH. Labelled set == set of IPs in the log (both differences empty). Identical (request line, UA) appearing under both labels: 0. Exact duplicate log lines: 0. HIGH. Labels are a dict keyed by IP, so a duplicate input cannot hold two labels; but overlaps silently overwrite: `generate_corpus(pivoters=95)` yields 98 rogue labels, not 103 (pivoter IPs 203.0.113.100+ collide with cadence bots), and `humans=600` emits 95 invalid IPs (e.g. 198.51.100.256). HIGH (measured). Defaults unaffected (LOW severity).
**(3) Regression-only: HOLDS TODAY, UNGUARDED.** `grep -rn synth_corpus|generate_corpus` on the merge tree and on `origin/main` (b3ba53f3a): only `tests/test_synth_corpus_s4.py` imports it. HIGH. `calibrate.py`, `cli.py`, `engine.py`, `models.py` do not reference it; RetroConfig defaults remain 1800/300/20/0.35 (`models.py:139-142`). HIGH. But the module lives under `src/` (ships in the wheel, `pyproject.toml` packages = src/agent_incident_retro) and no test forbids a non-test import: mutants M15/M16/M17/M23 (calibrate tuning from the corpus, calibrate/cli/engine importing it) all survive 242/242. HIGH.
**(4) Sweep determinism: DETERMINISTIC.** `python -m agent_incident_retro.calibrate corpus11.log --labels labels11.json` (full default 3x3x3x3 grid) run twice, PYTHONHASHSEED=1 and =2: 81 lines each, identical sha256 `e7b37d48dd8b695f...`, `cmp` equal. HIGH. All 81 points = (tp 20, fp 0, fn 0, tn 300, absent_benign 0), matching the comms record `20261121-2242-don.reviewer-postmerge-pr1060-1063.md:9`. HIGH. Corpus itself is byte-identical across 3 processes with PYTHONHASHSEED 0/7/99 (hash `0ef11eed042ddd8b`). HIGH.
**(5) Claimed review: UNCORROBORATED.** PR body says "Independent review: PASS on f7ea31492." (GitHub MCP `get`). `f7ea31492` is the real PR head. HIGH. GitHub reviews: `[]`; PR comments: `[]`. HIGH. `origin/comms`: no file mentions `f7ea314` or the branch `w3/b5-synthetic-corpus`; mentions of #1064 are only (a) `20261121-2055-don.reviewer-pr1062-2bd9451.md:6` (notes #1064 landed), (b) `20261121-2242-don.reviewer-postmerge-pr1060-1063.md:9,23` (uses the corpus; "Read partly: synth_corpus.py"; it is a review of #1060/#1063, dated 8 days after merge), (c) `20261122-0035-roley.reviewer-CORRECTION-audit-section3.md:7` ("1064 ... no record anywhere"). C-1064 card hits in TASK-QUEUE are an unrelated October card id. HIGH. Conclusion: no trace of a pre-merge review of f7ea31492 exists in either source. Merged by the PR author (merged_by == user) 31 min after opening. HIGH.

**Other findings**
- F1 (MEDIUM) M11: `sweep` ignoring the grid (`RetroConfig()` instead of `RetroConfig(**cfg)`) passes all 242 tests. #1064's insensitivity test makes every point identical, so it cannot detect this, and `test_calibrate_s4.py` does not either. Gap is inherited from #1060/#1063 but #1064 is the test that claims to pin sweep plumbing. HIGH (measured).
- F2 (LOW) `synth_corpus.py:6` docstring claims "several rogue shapes, a few awkward benign clients"; the code has two rogue shapes and no awkward benign clients (only human browsers). HIGH (read lines 34-62). Overstates coverage; the open B-S4B5-CORPUS-SHAPES card (`20261121-2055-...pr1062...md:13`) is the fix path.
- F3 (LOW) Test name `test_flagged_set_is_insensitive_to_the_four_thresholds` but its grid has three; `session_gap_s` is absent. PR body admits this. HIGH.
- F4 (LOW) M14 (count CLEAR/any finding as flagged) survives: findings carry only non-CLEAR verdicts and the corpus has no AUTHORIZED client, so FLAGGED filtering is untested on this corpus. MEDIUM.
- F5 (LOW) Generator overflow/collision (see (2)); no parameter validation.

#### Mutants (worktree only; `git checkout -- .` after each, tree clean after every run; full suite `pytest -q tests`)
| # | Behaviour | Mutant | Result |
|---|---|---|---|
| M01 | B1 determinism + 20/300 labels | unseeded RNG | KILLED (1 failed) |
| M02 | B1 | flip one rogue label to benign | KILLED (3 failed) |
| M03 | B1 | drop the benign set | KILLED (3 failed) |
| M04 | B1 | seed ignored | KILLED (1 failed) |
| M05 | B1 | bot IPs collide with pivoters | KILLED (3 failed) |
| M06 | B1 | flip one benign label to rogue | KILLED (3 failed) |
| M07 | B2 defaults pinned (20,0,0,300) | pivot payload made benign | KILLED (2 failed) |
| M08 | B2 | drop bot debug probe | KILLED (2 failed) |
| M09 | B2 | one benign human probes /.env | KILLED (2 failed) |
| M13 | B2 | tp/fn predicate swapped | KILLED (3 failed) |
| M18 | B2 | session_gap default 1800->4800 | KILLED (1 failed, test_detection_pins_c148) |
| M10 | B3 sweep plumbing / insensitivity pin | FLAGGED = ESCALATE only | KILLED (3 failed) |
| M11 | B3 | sweep ignores grid config | SURVIVED |
| M12 | B3 | sweep returns first point only | KILLED (2 failed) |
| M14 | B3 | every finding counts as flagged | SURVIVED |
| M24 | B3 | pivot_window_s dropped from cfg | SURVIVED |
| M15 | B4 regression-only | sweep pulls labels from corpus | SURVIVED |
| M16 | B4 | calibrate computes a value from corpus at import | SURVIVED |
| M17 | B4 | cli imports corpus | SURVIVED |
| M23 | B4 | engine imports corpus | SURVIVED |
| M19 | B5 synthetic-only content | placeholder email added to a UA | SURVIVED |
| M20 | B5 | benign IPs moved off RFC 5737 | SURVIVED |
| M21 | B5 | AKIA-shaped fake key in a page | SURVIVED |
| M22 | B5 | pivoter IPs moved to RFC 1918 | SURVIVED |

Totals counted from the table: 24 mutants; KILLED 13 (B1 6, B2 5, B3 2); SURVIVED 11 (B3 3, B4 4, B5 4). B1 6/6 and B2 5/5 are well pinned; B3 2/5; B4 0/4 and B5 0/4 have no guard.

#### CONCLUSION
**PASS WITH CONDITIONS on 123b71b5** (post-merge; conditions become follow-up cards, nothing to revert).
- C1 (MEDIUM): add a test that fails if any non-test module imports `synth_corpus` (B4 guard; kills M15/M16/M17/M23).
- C2 (MEDIUM): add a test that every corpus IP is in RFC 5737 and the text matches no secret/email pattern (B5 guard; kills M19-M22). The repo is public.
- C3 (MEDIUM): add a sweep test where two grid points give different (tp,fp,fn,tn) on a small fixture, so config plumbing is pinned (kills M11/M24).
- C4 (LOW): fix the docstring (F2) and test name (F3); validate generator parameters (F5).
- C5 (process): record that the PR body's "Independent review: PASS on f7ea31492" has no trace on GitHub or comms; this post-merge review is the first record.
Confidence in verdict: HIGH (all evidence measured on the merge sha).

### #1070 post-merge (roley.reviewer, 750824b)

Status: COMPLETE. Servers stopped; worktree removed.

Merge sha: 750824b8a598c0d8c4bd5a9a49ab4e1f8787fd89 (squash; parent 6bc2c80fa = #1069). Source: GitHub MCP pull_request_read get (merged 2026-11-13T23:41:31Z, head e1efa94) and `git show --stat` HIGH.
Scope: 1 file, services/ops-console/src/ops_console/static/console.html, +314/-251. Source: git show --stat HIGH.

#### (1) Diff, file by file (static analysis of 6bc2c80fa -> 750824b8a)
- Only file: console.html. All three `<script>` blocks (one is `type="application/json" id="setup-steps"`, two JS) are BYTE-IDENTICAL before/after (extracted and `diff`ed: lengths 12021/34136/33439 both sides). Source: python extraction + diff HIGH. Minor inaccuracy in PR body: it says "both script blocks"; there are three (two JS + one JSON). LOW impact.
- Element ids: 107 before, 107 after, identical sorted set. HIGH.
- Inline handlers (`on*=`): 30 before, 30 after, identical multiset. HIGH.
- No new innerHTML / template-literal sinks possible: JS unchanged. Existing sinks route server data through `esc()` (e.g. halt result, bulk result). HIGH (source read).
- External resources: none before or after. No http(s)/protocol-relative src/href, no `@import`, no `@font-face`, no CSS `url()` except the in-SVG `url(%23g)` in the data: favicon (unchanged). Fonts are local `var(--mono)`/`var(--sans)` stacks. HIGH.
- CSS exfil vectors: no `content: attr(...)`, no attribute-selector+url() pattern. HIGH.
- Markup: header gains nav (moved, not new) + FLEET HALT button (moved from agents toolbar); `#opbar` div -> `<details>` collapsed; sections reordered into `.area-*` grid; headings split into `h2` + `.h-note` span with same words; `label for=` added (15), `aria-label` on opid/opkey; inline `style=` removed from halt dialog in favour of classes. No attribute removed (Counter diff of name/type/required/pattern/for/aria/role/autocomplete/disabled/data-*: removed = {}). HIGH.
- New CSS `:has()` (3 rules) is presentation only. `#drawer` gains `visibility:hidden` when closed (improvement: closed drawer leaves tab order). HIGH.

#### (2) CSP / meta
- `<meta>` set identical (charset, description, color-scheme, theme-color, viewport). No CSP meta before or after; diff touches no Python, so any server-sent CSP header is unchanged. Source: regex extraction + git show --stat HIGH.

#### (3) Identity / token / secret exposure
- JS unchanged and ids unchanged, so no new data field is rendered. Operator id/key inputs are the same elements (`#opkey` still `type="password"`, `autocomplete="off"`); now inside a collapsed `<details>`. `#secretbar` still `display:none` by default and toggled by unchanged JS on 401. No previously `display:none` element was un-hidden (old 5 display:none rules all retained or superseded: `#verdict` still display:none until ALLOW/BLOCK/ESCALATE). HIGH.

#### (4) FLEET HALT
- Button moved into `<header>` (still `onclick="openHalt()"`). `<dialog id="halt">` is outside `<main>` (lines 790-804 new), so it opens from the Setup view too (main hidden there) - disclosed in PR. Fields halt-op/halt-reason/halt-confirm present with same ids; `#halt-go` still `disabled` in markup; `haltReady()` still requires op.trim && reason.trim && confirm === "HALT"; `fleetHalt()` still POSTs all three to /api/fleet/halt with operator headers. HIGH (source).

#### (5) Accessibility (LOW)
- Improvements: labels bound via `for=` on halt-op/reason/confirm and harness/ledger fields; aria-labels on operator inputs; `:focus-visible` outline on summary; reduced-motion rule; closed drawer `visibility:hidden`. No `outline:none` added. Drawer close button text "close ✕" -> "close" (fine). Residual (pre-existing, not a regression): halt dialog has no `aria-labelledby`/`aria-describedby` linking to its h3/p; confirm input has no `required`/`aria-required` (enforcement is JS-disabled button). LOW.

#### Tests on 750824b (venv (session scratch, not retained) Python 3.13.18, local editable installs from the worktree)
- services/ops-console: `471 passed, 1 warning in 144.83s (0:02:24)` - matches PR claim of 471. HIGH (run).
- tools/tests/test_ci_external_ref_guard_c101.py: `31 passed in 3.12s` (includes "shipped console page has no hit"). HIGH (run).

#### Live render (Chrome via Playwright, /usr/bin/google-chrome) on 750824b
- Local stack only, loopback ports: sealed-ledger :18102, agent-registry :18101, ops-console :18100 (other upstreams pointed at closed 127.0.0.1:9, shown unavailable). FIELD_DATA_DIR under (session scratch, not retained)
- Hostile data via the real registry API (so it also reaches the ledger as `registry.registered` events, 3 seen in /api/overview): agents a1/a2/a3 with name=owner=domain = `<img src=x onerror=alert(1)>`, `"><svg onload=alert(2)>`, `</td><script>alert(3)</script>`.
- Steps: load (3 s), click every agents row (4 drawer opens), click ledger rows (4), open FLEET HALT from header, navigate to #setup and open FLEET HALT there.
- Result: JS dialogs = 0, page errors = 0, external requests = 0, `img[src=x]` = 0, `svg[onload]` = 0, `<script>` count stays 3, payload text visible as text = true at every step. NO SCRIPT EXECUTED. HIGH (run; script (session scratch, not retained)).
- Halt gate in real Chrome: halt-go disabled initially / after op only / after op+reason / with "halt" lowercase; enabled only with op+reason+"HALT"; disabled again when op is blanked to spaces; dialog opens from #setup view. HIGH (run).
- Also: the jsdom hostile-payload harness tests (test_dashboard_escaping.py + test_innerhtml_audit_c457.py) ran, not skipped: `75 passed`. HIGH (run).

#### Server-side halt enforcement (context for B2 mutants)
- api.py FleetHalt: `operator: str = Field(min_length=1)`, `reason: str = Field(min_length=1)`, `confirm: Literal["HALT"]`, `extra="forbid"`; test_console_features.py::test_fleet_halt_requires_typed_confirm pins confirm None/"halt"/"yes" refused. Source: api.py L234-242, tests L315 HIGH. Gap: server min_length=1 accepts whitespace-only operator/reason ("  "); client trims. Pre-existing, not introduced by #1070. MEDIUM (read, not run).

#### Mutants (20; applied in (session scratch, not retained) only, `git checkout -- .` after each; raw: (session scratch, not retained))
Detectors: T = 12 ops-console test files that read console.html (`pytest -x`); C = tools/tests c101; P = my Chrome probe (render.mjs: dialogs/sinks/external requests/halt gate).

| # | Beh | Mutant | T | C | P | Result |
|---|-----|--------|---|---|---|--------|
| 1 | B1 escape | esc() identity | FAIL | pass | alert x9 | KILLED |
| 2 | B1 | esc() drops `<` | FAIL | pass | page errors | KILLED |
| 3 | B1 | esc() drops quotes | FAIL | pass | clean | KILLED |
| 4 | B1 | halt result `d.domain` raw | FAIL | pass | clean | KILLED |
| 5 | B1 | bulk-result error raw | FAIL | pass | clean | KILLED |
| 6 | B2 halt | typed HALT not required | pass | pass | gate opens w/o HALT | KILLED (P only) |
| 7 | B2 | operator not required | pass | pass | blankOp enables | KILLED (P only) |
| 8 | B2 | reason not required | pass | pass | not probed | SURVIVED |
| 9 | B2 | HALT case-insensitive | pass | pass | "halt" enables | KILLED (P only) |
| 10 | B2 | `disabled` removed from halt-go markup | pass | pass | clean | SURVIVED (equivalent: openHalt() sets disabled=true) |
| 11 | B2 | header FLEET HALT onclick removed | pass | pass | dialog never opens (probe crash) | KILLED (P only) |
| 12 | B2 | POST sends confirm:"HALT" literal | pass | pass | clean | SURVIVED (masked while client gate intact) |
| 13 | B3 ext | Google Fonts `<link>` | pass | FAIL | external req | KILLED |
| 14 | B3 | CSS `@import` CDN font | pass | FAIL | external req | KILLED |
| 15 | B3 | CDN `<script src=//...>` | pass | FAIL | external req | KILLED |
| 16 | B3 | CSS `url(https://...)` | pass | FAIL | clean | KILLED |
| 17 | B4 secrets | opkey type=text | pass | pass | clean | SURVIVED |
| 18 | B4 | opkey autocomplete=on | pass | pass | clean | SURVIVED |
| 19 | B4 | #secretbar visible by default | pass | pass | clean | SURVIVED |
| 20 | B4 | saveOperator puts key in a GET URL | pass | pass | clean (not exercised) | SURVIVED |

Totals (counted from the table): 20 mutants. Killed by repo suites (T or C): 9 (#1-5, #13-16). Killed only by my probe: 4 (#6, 7, 9, 11). Survived all: 7 (#8, 10, 12, 17, 18, 19, 20), of which 1 equivalent (#10).
Per behaviour, repo suites: B1 5/5, B2 0/7, B3 4/4, B4 0/4. Including probe: B1 5/5, B2 4/7, B3 4/4, B4 0/4.

#### Objections to a clean PASS (FORCE O)
1. The repo tests do not pin the client-side FLEET HALT gate or the header button's wiring (B2 0/7). #1070 moved that button, and a later "styles only" PR could disconnect it with the suite still green. Mitigation: the server rejects any confirm other than "HALT" and an empty operator or reason (HIGH, api.py L234-242), so the UI cannot halt without the typed word. The remaining risk is a dead button during an incident, not a bypass.
2. Nothing pins `#opkey type=password` or `autocomplete=off`, or the page's "never in a URL" promise (B4 0/4). #1070 wrapped these fields in `<details>` without a test. A future markup edit could put the operator key on screen or in a URL with all tests green.
3. #1070 merged without a review record, and its "Not verified" list admits the halt dialog and drawer were never screenshotted. This review covers those gaps on loopback only, not on a locked (shared-secret) or live estate. MEDIUM.
Steelman for PASS: all three script blocks, the ids, the inline handlers and the meta tags are byte- or set-identical; the CSS adds no exfiltration vector; the live hostile render executed nothing. The conditions are pre-existing test gaps, not defects added by #1070.

#### Verdict: PASS WITH CONDITIONS (750824b)
- "Layout and styles only": TRUE for behaviour (JS byte-identical; no CSP/meta, data-exposure or external-resource change). HIGH.
- XSS: none. Hostile agent name/owner/domain in Chrome produced 0 dialogs and 0 injected nodes. HIGH.
- Conditions (follow-up PR, not a revert):
  C1. Add a dashboard test that the header `button.halt` opens `#halt`, and that `#halt-go` stays disabled unless operator.trim, reason.trim and confirm === "HALT" are all set (kills #6-9, #11).
  C2. Pin `#opkey` type=password and autocomplete=off, and that saveOperator writes no URL (kills #17, #18, #20).
  C3 (LOW). Server: reject whitespace-only operator/reason in FleetHalt (strip before min_length). Add aria-labelledby on `<dialog id="halt">`.
- PR-body inaccuracy (LOW): says "both script blocks"; there are three (one JSON).

Cleanup: local servers stopped, worktree removed (see below).

### #1074 post-merge (roley.reviewer, ba86175)

Status: COMPLETE

CORRECTIONS (premise of the review brief)
1. #1099 (503 retry) is NOT on main: PR state "open", merged=false (GitHub MCP pull_request_read get #1099); `git log origin/main | grep 1099` empty. Its interaction can only be reasoned about from its PR body, not tested on main. HIGH.
2. estate_probe never follows redirects: `_NoRedirect.redirect_request` returns None (tools/estate_probe.py:328-330 @ba86175), so a 3xx is answered as HTTPError status 3xx; there is no "redirect follow" request to time out. HIGH.
3. kill/revive are not subcommands; they are POSTs inside `catalogue` (estate_probe.py:673,686,592) and `refused-kill` (:763). `registry` is a subcommand (:802). HIGH.

Merge sha: ba861753ccca0bdd171bd89dfe618892312e7845 (main log `#1074`); head 7ccdc12; base 507f0109c. origin/main at review: b3ba53f3a.

#### Attack cases on ba86175 (local fake servers on 127.0.0.1 only; harness (session scratch, not retained) logs parse_merge.log, behav_merge.log)

Value parsing (`registry` against a never-answering local server; exit/elapsed/last line):
| input | flag | env FIELD_PROBE_TIMEOUT |
|---|---|---|
| 0, -1, abc, inf, nan, 1e9 | exit 2 refused | exit 2 refused |
| -inf, 3601, 0x10, 1e-400 (underflows to 0.0) | exit 2 refused | (not run) |
| "" | exit 2 refused | default 20 s (exit 3 after 20.07 s) |
| " " / "\t" | " " exit 2 | default 20 s (20.08 s) |
| U+0663 (Arabic-Indic 3) | accepted as 3 s (exit 3, 3.06 s) | same (3.08 s) |
| U+FF15 (fullwidth 5) | accepted as 5 s (5.06 s) | same |
| "1_0" | accepted as 10 s (10.07 s) | same |
| " 2 " | accepted as 2 s | same |
| 1e-300 | accepted; every request times out at once, exit 3 (fail closed) | same |
| 3600 | accepted (harness killed the run at 15 s; a single request may block 1 h) | - |
Verdict on parsing: no value disables the timeout or yields an infinite/zero socket timeout; every refusal is exit 2 before any send. Python float() leniency (unicode digits, underscores, surrounding whitespace) is accepted but always yields a finite value in (0,3600]. HIGH (commands above).

Precedence: flag 1 + env 30 -> 1.06 s; valid flag + junk env -> flag wins, env never validated (exit 3); junk flag + valid env -> exit 2; env 1 alone -> 1.07 s. Matches probe_timeout (estate_probe.py:199). HIGH.

Behaviour:
| case | result | fail-closed? |
|---|---|---|
| registry --agent, server never answers, t=1 | exit 3 UNREADABLE, 1.06 s | yes |
| pin, never answers, t=1 | exit 1, `{"pin": null ...}`, 3.06 s (3 sequential requests x 1 s) | yes |
| health --only ledger, never answers, t=1 | exit 1, FAILED line, 3.06 s | yes |
| registry, 302 -> second local server | exit 3 (HTTP 302), not followed, 0.06 s | yes (no redirect follow exists) |
| connect to a full-backlog local listener, t=2 | exit 3, 2.07 s (connect timeout applies) | yes |
| refused-kill, POST /killswitch/kill hangs, t=2 | exit 1, FAILED "refused 409 (got 0)", 2.07 s | yes |
| _restore_canary, POST /killswitch/revive hangs, t=2 (in-process) | False, [FAIL] RESTORE ..., 2.0 s, "CANARY MAY STILL BE KILLED" printed | yes |
| Estate.call on hang | (0, {"transport_error": "TimeoutError"}) | yes |
| trickle 1 byte / 3 s, t=2 | exit 3, 2.06 s | yes |
| **slowloris body 69 B at 1 byte / 0.5 s, t=2** | **exit 0 PRESENT after 34.09 s** | data correct, but the timeout did NOT bound the request |
| **slowloris headers+body at 1 byte / 0.5 s, t=2** | **exit 0 PRESENT after 78.6 s** | same |

FINDING F1 (MEDIUM severity, HIGH confidence): `--timeout` is a per-socket-operation timeout (urllib `timeout=` -> socket connect/recv), not a per-request deadline. Evidence: slowloris rows above; code `_OPENER.open(req, timeout=self.timeout)` then `resp.read(MAX_RESPONSE_BYTES + 1)` (estate_probe.py:366-367). The help text "timeout of every request ... a request that outlasts it fails the check" (estate_probe.py:976-978) and the PR body ("per request") are false for a server that keeps sending. Upper bound per request is ~16 MiB x timeout (MAX_RESPONSE_BYTES, :137), i.e. effectively unbounded; a deploy gate can hang far past its budget. It is NOT fail-open: no case produced PASS/exit 0 from a timeout; the slowloris PASS returned the server's genuine (valid) answer. Pre-existing semantics (default 20 s had the same property), so not a regression, but the PR's claim is wrong.

FINDING F2 (LOW, HIGH): total command time = number of sequential requests x timeout (pin 3 x 1 s above; health issues >10 requests, test_estate_probe_timeout.py:194 asserts len(calls) > 10). With the accepted maximum 3600 s, one `health` can legally run for hours against an estate that answers just under the timeout per read. No total/command deadline exists.

FINDING F3 (LOW, HIGH): float() leniency: "1_0" -> 10, U+0663 -> 3, U+FF15 -> 5, " 2 " -> 2 accepted. Not fail-open (always finite and in range); a typo like "1_00" silently means 100. Tests do not pin this.

FINDING F4 (LOW, HIGH): env "" / whitespace -> silent default 20 s, while flag "" / " " -> exit 2. Asymmetric but fail-safe (default is finite); the empty-env case is pinned (test_an_empty_env_timeout_means_the_default), whitespace is not.

FINDING F5 (INFO): 1e-300 accepted (> 0) -> every request times out instantly -> all checks FAIL. Fail-closed, harmless.

#### Same attacks on current origin/main b3ba53f3a (includes #1084; #1099 NOT merged)
behav_main.log: all 11 behaviour rows identical to the merge sha (registry 1.06 s exit 3; pin 3.07 s exit 1; 302 not followed; connect 2.06 s; refused-kill exit 1; restore False; slowloris body exit 0 after 34.08 s, headers+body exit 0 after 78.58 s). probe_timeout is unchanged between ba86175 and b3ba53f (`git diff ba861753c b3ba53f3a -- tools/estate_probe.py` touches only the heavy guard). HIGH.

#1084 interaction (base `http://probe.invalid`, a reserved TLD, so nothing can reach an estate):
- `--timeout abc pin` -> exit 2 "--timeout must be ..." (timeout validated first, nothing sent).
- `--timeout 1 pin` -> exit 2 heavy-route refusal, nothing sent.
- `--timeout 1 --allow-heavy health --only crosswalk` -> exit 1 FAILED (DNS failure -> status 0). 
Ordering in main(): probe_timeout before the heavy guard (main @b3ba53f: `timeout = probe_timeout(...)` then `_heavy_routes`/`_refuse_heavy`); the Estate.call backstop raises SystemExit(2) before urlopen, so the timeout never applies to a refused call. No conflict. HIGH.
Note: DNS resolution (getaddrinfo) is NOT covered by the socket timeout (general knowledge, urllib/socket.create_connection). LOW-severity, MEDIUM confidence; not measured.

#1099 (open PR, head 63f752df): per its body the retry loop caps total waiting at the call's --timeout. Because F1 shows --timeout is per-read, any "never past the call's --timeout" budget in #1099 must be measured against a wall clock, not assumed from the socket timeout. Untested here (not on main). LOW.

#### In-repo callers affected (@b3ba53f)
CLI (inherit env FIELD_PROBE_TIMEOUT; a junk value now exits 2 where it used to be ignored):
- .github/workflows/ci.yml:359 `docker exec estate python3 /platform/tools/estate_probe.py --base http://127.0.0.1:8080 health --expect-build-sha` (no --timeout).
- .github/workflows/ci.yml:489 `estate_probe.py --base "$BASE" health --expect-perimeter --expect-build-sha` (no --timeout).
- integration/fly/Dockerfile:50,54 (copies the tool; documented in-VM health command).
Library (build `ep.Estate(...)` with the ctor default 20 s; ignore flag and env, as the PR body states):
- tools/phase_g_check.py:819, tools/d16_record_check.py:123, tools/phase_g_stage0_check.py:107, tools/stage1_window.py:160.
No caller in the repo passes --timeout or sets FIELD_PROBE_TIMEOUT (grep, only docs/reviews/2026-11-21-roadmap-audit.md:450 mentions #1074). HIGH.

#### Test runs (venvs (session scratch, not retained) [merge] and venv-main [main], CI install recipe from .github/workflows/ci.yml:30-50; `CI=1 python -m pytest -q -p no:cacheprovider`)
| sha | target | last line |
|---|---|---|
| ba86175 | tools/tests/test_estate_probe_timeout.py | `24 passed in 36.98s` |
| b3ba53f (main) | tools/tests/test_estate_probe_timeout.py | `24 passed in 36.89s` |
| ba86175 | tools/tests | `1 failed, 4604 passed, 12 skipped, 1 warning in 643.20s (0:10:43)` |
| b3ba53f (main) | tools/tests | `1 failed, 4725 passed, 12 skipped, 1 warning in 695.23s (0:11:35)` |
The 1 failure on both is tools/tests/test_deployment_agent_cli_manifest.py::test_the_manifest_validates_with_field_core_offline: "delegation.expiry 2026-11-22 is in the past - the delegation has lapsed". A date time-bomb unrelated to #1074 (the file does not reference estate_probe: grep count 0). HIGH. Separate issue: it is red on main today.

#### Mutants (worktree (session scratch, not retained) @ba86175, `git checkout -- .` after each, status clean after the run; target test_estate_probe_timeout.py; logs mutants.log)
| behaviour | mutant | last line | result |
|---|---|---|---|
| B1 refuse bad | M1 0 accepted | 2 failed, 22 passed | KILLED |
| B1 refuse bad | M2 junk->default | 3 failed, 21 passed | KILLED |
| B1 refuse bad | M3 nan guard lost | 5 failed, 19 passed | KILLED |
| B1 refuse bad | M4 no upper bound | 5 failed, 19 passed | KILLED |
| B1 refuse bad | M5 bad env->default | 6 failed, 18 passed | KILLED |
| B2 precedence | M6 env beats flag | 1 failed, 23 passed | KILLED |
| B2 precedence | M7 env ignored | 7 failed, 17 passed | KILLED |
| B2 precedence | M8 empty flag->default | 1 failed, 23 passed | KILLED |
| B2 precedence | M9 env name typo | 7 failed, 17 passed | KILLED |
| B3 every request | M10 main drops timeout | 7 failed, 17 passed | KILLED |
| B3 every request | M11 call uses default | 8 failed, 16 passed | KILLED |
| B3 every request | M12 attest ignores | 2 failed, 22 passed | KILLED |
| B3 every request | M13 GET gets timeout=None | 8 failed, 16 passed | KILLED |
| B3 every request | M14 timeout=None everywhere | 8 failed, 16 passed | KILLED |
| B4 fail closed | M15 transport error -> (200, []) | 24 passed | SURVIVED |
| B4 fail closed | M16 pin prints partial + exit 0 | 3 failed, 21 passed | KILLED |
| B4 fail closed | M17 finish() always 0 | 2 failed, 22 passed | KILLED |
| B4 fail closed | M18 registry unreadable -> exit 1 (absent) | 24 passed | SURVIVED |
| B5 default 20 | M19 default 30 | 2 failed, 22 passed | KILLED |
| B5 default 20 | M20 unset env -> 3600 | 2 failed, 22 passed | KILLED |
| B5 default 20 | M21 unset env -> None | 2 failed, 22 passed | KILLED |
| B5 default 20 | M22 Estate ctor default None | 1 failed, 23 passed | KILLED |
Totals from the table: 22 mutants, 20 KILLED, 2 SURVIVED (B1 5/5, B2 4/4, B3 5/5, B4 2/4, B5 4/4).
Survivors re-run against test_estate_probe.py + test_estate_probe_c105.py: M15 `1 failed, 198 passed` KILLED; M18 `27 failed, 172 passed` KILLED. So the repo kills both; the PR's own file does not pin "a timeout is reported as status 0 / transport_error" nor registry exit 3 on timeout. No mutant/test exists for a total per-request deadline (F1), because the code has none.

#### Verdict: PASS WITH CONDITIONS on ba861753c
STEELMAN AGAINST (why BLOCK could be argued): (1) the help text and PR claim "a request that outlasts it fails the check" is false under slowloris (F1), and a deploy gate operator may rely on it as a wall-clock bound; (2) the maximum 3600 s x >10 sequential requests in health lets a gate run for hours (F2); (3) the PR merged with no review on record and the PR body admits the full tools/tests suite was not run.
WHY NOT BLOCK: no input disables the timeout or turns a timeout into PASS/exit 0 (36 parsing cases, 11 behaviour cases on both shas); every refusal is exit 2 before any send; kill/revive/refused-kill/registry/pin/health all fail closed on a hang; redirect is never followed; F1 is pre-existing semantics, not a regression. HIGH.
CONDITIONS (follow-up PR, not revert):
C1. Either enforce a per-request wall-clock deadline (e.g. read in chunks against time.monotonic(), abort -> status 0) or correct --timeout help (estate_probe.py:976-978) and module comment to "per socket operation (connect / each read)". Add a slowloris test. (F1)
C2. Add to test_estate_probe_timeout.py: a hang server asserting Estate.call returns status 0 and `registry --agent` exits 3 (kills M15/M18 locally).
C3. Decide and pin float() leniency ("1_0", unicode digits, whitespace env); suggest `re.fullmatch(r"[0-9]+(\.[0-9]+)?", raw)` (F3/F4).
C4. Fix the stale "5-18 s" comment (estate_probe.py:188-189 vs PR body "5-63 s"), already listed as a LOW by the author.
Confidence in verdict: HIGH.

Status: COMPLETE. Worktrees wt, main, mut removed after the run; all fake servers were in-process daemon threads of attack.py and exited with it.

### #405 (in #1016) post-merge (roley.reviewer, 347b720)

**VERDICT on 347b720: PASS WITH CONDITIONS.** `_registry_reason` does what C-1068 claims: no registry status text, body, header or transport text reached a reply, ledger row or header in any probe. Conditions: close the 5 surviving regex mutants with tests (F-PM405-3). Two kill-path defects outside #405's diff were found on the same code path (F-PM405-1, F-PM405-2). Both are still on current main and become builder cards; neither was introduced by #405.
**Current main (61e6b6a): the same verdict.** `_STATUS_ONLY`, `_registry_reason` and the 6 call sites are unchanged at the same lines (api.py:331-346, 625/641/714/800/816/853; `git diff 347b720 origin/main` shows no change to these lines; grep of both worktrees). F-PM405-1 reproduces on main.

ASSUMPTIONS:
1. "Registry response" means what field_core `RegistryClient` raises (packages/field-core/src/field_core/clients.py:390-457). An injected non-RegistryClient registry object is test-only.
2. The 502 `detail` is JSON-encoded by FastAPI `HTTPException`, and none of the 6 sites sets `headers=`.
3. Mutants were run against the full kill-switch suite with `-x`. KILLED means at least one test failed.

**Provenance (HIGH: `git range-diff acaf5f2..fc6b549 1e017ecf4..347b720`; GitHub MCP `pull_request_read` get/get_commits on #405 and #1016):**
- #405 head `fc6b549` (state closed, draft, merged=false) has 2 commits: `f101fe7` (C-504) and `fc6b549` (C-1068).
- In #1016 these map with `=` (patch-identical) to `64b66ff` and `347b720`. `1e017ec` (S6-1) is #1016's own commit.
- So the "rebuilt" commits carry the same patch as the BLOCKed head. That means the reviewer's BLOCK reasons (C-1058) apply unchanged, except for whatever `fc6b549` already fixed (F-405-2).
- `347b720` is an ancestor of origin/main (`git merge-base --is-ancestor`, rc=0 after `--deepen=400`; the clone was shallow).

**What `_registry_reason` does (HIGH, api.py:331-346 @347b720):**
- If the exception has a `__cause__`, it returns `type(cause).__name__`.
- Otherwise it returns `str(exc)` only if it fullmatches `registry returned [0-9]{3}`, and `type(exc).__name__` in every other case.
- Its only use is the 6 `HTTPException(502, ...)` details: kill get (625), kill flip (641), domain list (714), revive get (800), revive flip (816), liveness (853).
- It is NOT used in ledger rows. Those use `_exc_name` (577, 951), and domain `errored` keeps the status only (api.py:752).
- The domain report's per-agent `error` field relays the 502 detail (api.py:749), so its exposure equals the 502's.
- The uncaused text comes from field_core `upstream_error` = `f"{what} returned {status}"`, which never includes the body (errors.py:23-34, HIGH).

**In-repo callers (HIGH, grep of both worktrees):**
- `services/kill-switch/src/kill_switch/api.py` (the 6 sites above).
- `services/kill-switch/tests/test_error_type_name_only_c504.py:156-166`.
- `tools/tests/test_boundary_echo_lint_c505.py:71,419`: lists `_registry_reason` in `SAFE_CALLS`. The echo lint therefore trusts the helper's regex and would NOT catch a loosened regex (see F-PM405-3).

**Suite (HIGH, run here; venv (session scratch, not retained) main run with PYTHONPATH pinned to the main worktree srcs, import paths verified):**
- 347b720: `470 passed, 1 warning in 18.72s`
- origin/main 61e6b6a: `494 passed, 1 warning in 20.35s`

**Attack probes (HIGH, scripts/probe.py and probe2.py: real `RegistryClient` over `httpx.MockTransport`, fake canary `...FAKEKEY...`, no network):**

| # | Registry behaviour | Kill-switch result | Leak |
|---|---|---|---|
| 1 | 503, canary in body, reason phrase, header and CRLF | 502 `registry returned 503` | none |
| 2 | status 1000 / 99, canary body | 502 `RegistryUnreachableError` | none |
| 3 | 200 HTML with canary | 502 class name | none |
| 4 | 200 JSON list `[canary]` | 502 class name | none |
| 5 | transport error, canary and fake userinfo in the URL | 502 `ConnectError` | none |
| 6 | PATCH 403 (refused) | 502 `registry returned 403`, no `kill.agent` row | none |
| 9 | PATCH 204 | 502 `registry returned 204` | none |
| 7 | PATCH **200, body `status: active`** | **200 KillReport `status: killed`**, `kill.agent` ledgered | none (F-PM405-2) |
| 8 | PATCH **404** (agent gone mid-kill) | **500 Internal Server Error** | none (F-PM405-1) |
| 8b | revive PATCH 404 | 404 handled (api.py:814) | none |
| D | domain kill, a1..a3, a2 PATCH 404 | **500; a3 never PATCHed; no `kill.domain` row** | none (F-PM405-1) |

- Helper direct: `"registry returned 503\n"`, Arabic-Indic digits and `"abc"` all return the class name. Injection via the status code is impossible because httpx's `status_code` is an int (HIGH).
- Echoing secrets: not possible through `_registry_reason`. The cause path returns a class name only, and the uncaused path is digits plus fixed text (HIGH, probes 1 and 5).
- Header injection: none; there is no `headers=` on the 502s (HIGH, api.py sites).
- Refusal reported as success: NOT via `_registry_reason`, which runs only on the failure path. It does happen via probe 7 (F-PM405-2).

**Mutants (worktree only, `git checkout -- .` after each; scripts/mut.py):**

| ID | Behaviour | Mutant | Result |
|---|---|---|---|
| M1 | B0 shape | `[0-9]{3}` -> `.{3}` (known) | SURVIVED |
| M2 | B0 | -> `[0-9]+` | KILLED |
| M3 | B0 | -> `\d{3}` (Unicode digits) | SURVIVED |
| M4 | B0 | -> `[0-9]{1,3}` | SURVIVED |
| M5 | B0 | prefix -> `.*returned ` | SURVIVED |
| M6 | B0 | -> `[0-9]{3}.*` | KILLED |
| M7 | B0 | -> `[0-9]{3}\s?` (allows a trailing newline) | SURVIVED |
| M8 | B2/B3 | `fullmatch` -> `match` | KILLED |
| M9 | B2/B3 | `fullmatch` -> `search` | KILLED |
| M10 | B1 cause | -> wrapper class name | KILLED |
| M11 | B1 | -> `str(cause)` | KILLED |
| M12 | B1 | -> `str(exc)` | KILLED |
| M13 | B1 | cause branch removed | KILLED |
| M14 | B1 | -> `repr(cause)[:20]` | KILLED |
| M15 | B2 relay | status-only never relayed | KILLED |
| M16 | B2 | relayed `.upper()` | KILLED |
| M17 | B2 | relayed as fixed `registry error` | KILLED |
| M18 | B2 | relayed `text[:-1]` | KILLED |
| M19 | B3 replace | else -> `str(exc)` (pre-fix) | KILLED |
| M20 | B3 | else -> `text[:40]` | KILLED |
| M21 | B3 | else -> `""` | KILLED |
| M22 | B3 | else -> `_scrub(text)` | KILLED |
| M23 | B3 | else -> first line | KILLED |
| M24 | B4 sites | api.py:625 -> `str(exc)` | KILLED |
| M25 | B4 | api.py:641 -> `str(exc)` | KILLED |
| M26 | B4 | api.py:714 -> `str(exc)` | KILLED |
| M27 | B4 | api.py:800 -> `str(exc)` | KILLED |
| M28 | B4 | api.py:816 -> `str(exc)` | KILLED |
| M29 | B4 | api.py:853 -> `str(exc)` | KILLED |

**Totals (counted from the table): 29 mutants, 24 KILLED, 5 SURVIVED (M1, M3, M4, M5, M7). Kill rate 24/29 = 82.8%. Per behaviour: B0 2/7, B1 5/5, B2 4/4, B2/B3 2/2, B3 5/5, B4 6/6.**

The commit's claim "a loosened shape fails" (347b720 message) holds only for M2, M6, M8 and M9, not for loosening in general (HIGH).

**Findings (become builder cards):**
- **F-PM405-1 MEDIUM (pre-existing, not from #405; on main): an AgentNotRegisteredError from the kill flip is uncaught.**
  - `_kill_one`'s flip catches only `RegistryUnreachableError` (api.py:639-641). field_core `set_status` raises `AgentNotRegisteredError` on 404 (clients.py:453-454).
  - Single kill returns a bare 500.
  - **Domain kill aborts mid-loop.** The agents after the failing one are never halted, and the `kill.domain` row is never written (probe D, reproduced on 347b720 and main).
  - Revive already handles this (api.py:814).
  - Fix: catch `AgentNotRegisteredError` in the flip and map it to 404, which becomes a per-agent `error` in a domain kill. Pin it with a 3-agent domain test.
  - Blame: lines 638-640 predate #405 (`b07f648`, 2026-10-28; shallow boundary).
- **F-PM405-2 LOW-MEDIUM (pre-existing; on main): a registry that answers the PATCH 200 but keeps `status: active` produces a successful KillReport and a `kill.agent` ledger row.**
  - The `set_status` return value is ignored (api.py:639, 461-467). Probe 7.
  - Realism: this needs a faulty or hostile registry. LOW confidence on likelihood, HIGH on behaviour.
  - Fix: check that the returned record's `status == "killed"`, else 502.
- **F-PM405-3 LOW (test gap, #405's own code): 5 regex survivors (M1, M3, M4, M5, M7).**
  - M5 and M7 widen what can be relayed: an arbitrary prefix, or a trailing newline. M3 and M4 are near-equivalent today because the status is an int.
  - `SAFE_CALLS` in the C-505 lint trusts the helper, so nothing else guards it.
  - Fix: add helper cases `"registry returned abc"`, `"registry returned 50"`, `"registry returned ٥٠٣"`, `"x registry returned 503"` and `"registry returned 503 "` to `test_registry_reason_relays_only_the_status_only_shape_without_a_cause`. Also consider `re.ASCII`.
- **F-PM405-4 INFO (wording):** a 403 refusal and a 204 are reported as "registry unreachable", which is misleading for an operator reading a refusal (probes 6 and 9). Cosmetic only.
- **Not reviewed:** the lifecycle-manager half of `64b66ff` (outside the card's focus). The ops-console half of C-504 is on PR 348 (#405 body; not verified here).

CONCLUSION: #405's `_registry_reason` is sound against hostile and malformed registry responses: no echo, injection or secret leak in 11 probes, and 24/29 mutants killed. It is PASS WITH CONDITIONS for the F-PM405-3 tests. F-PM405-1 is the most serious item: a domain halt that stops halting. It is a separate pre-existing defect on the same path and still present on main.

