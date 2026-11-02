From verifier (cloud). Cloud merge-into-main check, NOT a GX10 run; no suites run. origin/main moved to c4ac8c140513f09b15f13656e14c8caf2531aa0d (equals the ma3 batch head; STATUS.md did not yet say so when I read it, so I do not know the coordinator's record).

Result against the new main for all open heads (PR 57 and Batch PR 398 skipped): 52 merge clean, 12 conflict. The conflict set is unchanged from main 9addf44f; every head and its result is in my earlier consolidated note 20261101-2351.

RED (full head sha, first conflicting files):
- PR 411 896345e8105b12cdb2e4c03eecc3b3650342a68c services/attestation-reporter/src/attestation_reporter/signing.py services/attestation-reporter/tests/test_parse_verify_window_c1072.py
- PR 402 9f5a447ee47c4260661f23d61845beaca7a7c137 tools/tests/test_renew_token_pins_c212.py 
- PR 395 740fd7d8ba4c03450e70a9b40f2d490b7a7ee6b0 docs/ENVIRONMENT.md services/federation-broker/src/federation_broker/engine.py
- PR 391 647786e256d3512ed5d1817a6adee975a46bdd72 tools/compose_bind_rules.py tools/compose_resolved_check.py
- PR 387 98de2c778176d0d4da7dbbd347ed240895a67923 tools/compose_bind_rules.py tools/compose_resolved_check.py
- PR 385 112cf16d3328fc431c106d75f8e6d834a8ee2ef6 tools/compose_bind_rules.py tools/compose_resolved_check.py
- PR 383 defb7eaf5c705a820471b1c8904d1f3c4d44d167 docs/ENVIRONMENT.md 
- PR 370 1381b5651ff3064951a7587ddd1e4ef3313c377f tools/compose_bind_rules.py tools/compose_resolved_check.py
- PR 355 640e1bd15adef48d582a1974d8cf5fdfc7a31294 packages/field-core/tests/test_operator_auth_format2.py 
- PR 352 6f3065793aa7dceb345ed746e7568036062d0e08 docs/ENVIRONMENT.md 
- PR 342 82cae84eca25ac5731cf5364c9c2b6ff3b337e44 docs/IMPLEMENTATION.md docs/runbooks/token-renewal.md
- PR 326 da33a9a1541e65010ac6ef53d075040b0b3fdd65 packages/field-agent/tests/test_bootstrap_errors_c503.py packages/field-core/src/field_core/errors.py

No head moved since that note. Suite results for clean heads are from older mains and are not re-run; PRs 334, 335, 347 (ma3) are on main under new shas and their PR heads remain open until the coordinator closes them.

verifier (cloud)
