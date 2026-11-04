# builder-5: queue empty, fallback scan of packages/field-core

Queue returned EMPTY after S4-2. Public functions in packages/field-core/src/field_core whose name appears in no file under packages/field-core/tests (word match; indirect coverage via callers is possible, so each needs a look before a card):
alerts.py: send_test, write_topic_file. authn.py: shared_secret. cli.py: verify_chain_cmd, alert_test_cmd, alert_topic_init_cmd. guarded_operator.py: all_routes. operator_auth.py: shown_claim, recorded_path, valid_event_prefix, decode_registry_document, parse_headers, note_breakglass, append_failure_status. operator_health.py: registry_view, internal_routes_enabled, verify_hash_answer, rotation_state, install_routes. pricing.py: units_to_usd_str.
Proposal: one test-only card per module (operator_auth, operator_health first: security-relevant parsing). First 20 of the scan only.
