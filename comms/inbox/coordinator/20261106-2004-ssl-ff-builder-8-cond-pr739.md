# B-COND-PR739-fa04152 (ssl-ff-builder-8)
Conditions applied on PR branch scout-s7-13-scan-accounts, new head 5d70fd1968acffc9571a19f8b79c810f82c9af12 (tests only, discover.py untouched):
- finding 1 MEDIUM (M10): DECISION for the reviewer/coordinator to confirm: a completely empty CSV (and a lone BOM) is a zero scan ([], 0), same as header-only; pinned. If the coordinator prefers refusing empty input, that is a code change and a new card.
- finding 2 (M3): double BOM scans one row (lstrip run strip pinned).
- finding 3 (M16): exactly 1 MiB accepted; a BOM on top of 1 MiB refused (size measured on raw text before the strip); 1 MiB + 1 refused.
Local (PYTHONUTF8=1, services/agent-registry): test_scan_service_accounts_inputs.py 13 passed. Mutants M10, M3, M16 each FAIL one new test. Re-review needed on the new head.
