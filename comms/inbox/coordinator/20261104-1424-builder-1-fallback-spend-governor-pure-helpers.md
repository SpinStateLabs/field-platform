# builder-1 FALLBACK proposal (Lane 2): spend-governor pure helpers no test names

Scan: public module-level functions per service whose name appears in no file under that service's tests/ (ast + regex over services/*). Most hits are CLI commands exercised by their command string (false positives). Real candidates, no test names them:

1. services/spend-governor/src/spend_governor/usage.py:96 `evaluate_rogue(policy, canonical_model, priced, window_tokens_after)`: pure policy arithmetic behind /usage's rogue findings. tests/test_usage.py:71-101 reaches each kind through the API only; not pinned: the burst boundary (`>=` limit, so limit-1 does not fire, limit does), `policy is None`, `token_rate_limit is None`, an empty allow-list never fires rogue_model, an unpriced model with an allow-list violation yields BOTH findings in the order unpriced, rogue_model, rogue_burst, and the detail text (no secret, names the model and the limit).
2. services/spend-governor/src/spend_governor/core.py:840 `window_action_rows(rows)`: Option A precedence for one action's window (sentinel-metered rows win when any exist, else the self-reported rows). Reached only through api.py:193 /status. Not pinned: metered-only, self-only, mixed (self rows dropped), a non-"sentinel" source string counts as self, input order kept, empty input.
3. services/federation-broker/src/federation_broker/engine.py:127 `canonical_ed25519_public_pem` (4 lines): not examined beyond the name.
4. services/attestation-reporter/src/attestation_reporter/signing.py:108 `signer_public_pem`, render.py:110 `find_browser`, :120 `render_pdf`: not examined.

Building 1 and 2 as one tests-only PR (services/spend-governor/tests/test_pure_policy_helpers.py) if the next claim attempt is still EMPTY. No source edit; a behaviour that contradicts its docstring becomes a finding.
