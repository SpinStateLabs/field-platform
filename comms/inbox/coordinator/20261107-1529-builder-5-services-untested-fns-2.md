# builder-5: queue empty (2026-11-07), fallback scan of six services

dispatch.sh next returned EMPTY. Scan: public top-level functions in services/{agent-registry,delegation-authority,kill-switch,spend-governor,federation-broker,conformance-sentinel}/src whose name appears (whole word) in no file under that service's tests/. Name-only match: indirect coverage through a caller is possible, so each needs a look before a card.
Highest value first:
1. agent-registry/redaction.py: redact, redact_text, check_size (secret redaction and size cap on registry input; no test names any of them).
2. kill-switch/api.py: set_status_on_behalf.
3. federation-broker/engine.py: canonical_ed25519_public_pem (key normalisation on a trust path).
4. delegation-authority/cli.py: is_guarded, operator_pair, dry_run_mint_gate, doa_check (CLI gate helpers).
5. agent-registry/api.py: data_path, unresolvable_manifest_ref (also data_path in delegation-authority, spend-governor, federation-broker).
Low value (CLI shells): version/list_cmd/serve/add_contract/clauses in the six cli.py files.
Proposal: one test-only card per item 1-3 (redaction first). Not scanned: ops-console, lifecycle-manager, attestation-reporter, sealed-ledger, tools/.
