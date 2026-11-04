# LANE O review: PR 642 (generate_doa_roster --max-ttl-days bounded 1..3650, S3-22) @ 1190b304

Verdict: PASS. UNVERIFIED (cloud, no GX10). Head 1190b304, 1 commit, 0 behind origin/main, Don Hagell numeric noreply. Source +6 in tools/generate_doa_roster.py, tests +99/-... in two files (one new).

Objections first: (1) the older test `test_a_roster_the_service_model_rejects_is_never_written` no longer uses `--max-ttl-days 0`; it now monkeypatches `gen.DoaRoster.model_validate`, so it pins "the generator calls the service model and refuses on its rejection", no longer "the service model rejects a real bad roster". The bound makes the old input unreachable, so this is reasonable, but a real service-side rejection now has no end-to-end pin in that file. (2) The 3650 bound is a policy choice; the only link to the service limit is `MAX_TTL_DAYS <= 999_999_999`, a constant copied into the test, not read from the service. (3) Non-integer text (`--max-ttl-days abc`) is argparse's own exit, not pinned by this PR and not claimed.

Baseline (unmutated, measured): new file + test_generate_doa_roster.py 38 passed; the five older files that import the generator (test_job_grantors_c13, test_deployment_agent_cli_manifest, test_generate_doa_roster, test_machine_verifier_identity, test_doa_roster_job_rows) 103 passed. The whole tools/tests suite did not finish inside my 300 s limit; I stopped it and did not use it. Survivor check was against those five files.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 value below 1 refused | 4 | 4 | 0 | 0 |
| B2 value above 3650 refused | 5 | 5 | 0 | 0 |
| B3 bounds 1 and 3650 and the default 30 still write a loadable roster | 4 | 4 | 0 | 0 |
| B4 refusal text names flag and range, not the value or a path, exit 2 | 5 | 5 | 0 | 0 |
| B5 checked before any input is read | 4 | 4 | 0 | 0 |
| Total | 22 | 22 | 0 | 0 |

Totals counted from the table: 22 = 22+0+0. No invalid, no noapply. Two B5 mutants (move the check after the manifests check; move it after load_records) overlap in intent; counted separately as written.

Not mutated: the argparse `type=int` path, the docstring and help text. Confidence: HIGH on counts, MEDIUM on completeness of the mutant set. Token/cost: I do not know.
