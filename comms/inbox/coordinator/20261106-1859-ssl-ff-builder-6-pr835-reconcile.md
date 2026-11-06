# B-PR835-g21-breakglass-reconcile: pushed on PR 835, new head 4f053b3

Head 4f053b3590a9 on builder7/g17-operators-template (main merged in first, so one head holds the template and the G21 test).
- G21 test (services/lifecycle-manager/tests/test_provision_alias_listed_require_g21.py): bypass_operator_list allowed only on literal ids svc-killswitch and don-breakglass in docs/templates/operators.g17-template.json; any other row or file fails. Scan split into exemption_rows(root); 7 parametrized mutants (right id wrong file, svc-registry, don-breakglass-2, svc-killswitch-x, job-renewal-gb10, don-admin, svc-verifier-1) each fail; the two allowed rows pass. Template untouched.
- tools/tests/test_operators_template_g17.py: the 7 missing pins (kill/revive on don-admin; mint_for_others on job-renewal-gb10; mint_for_others dropped from job-provision-gb10; bypass on svc-registry; bypass dropped from svc-killswitch; orphan. dropped from svc-lifecycle; bypass dropped from don-breakglass), each with a mutant that yields exactly one violation.
- Local (Windows, PYTHONUTF8=1): lifecycle-manager 295 passed; test_operators_template_g17 24 passed; operator_keygen tests 188 passed, 7 skipped. Not run: full tools suite, CI, GX10 run (verifier card needed on 4f053b3).
- Identity Don Hagell on both fields. No estate touched. Per architect: merge 835 last, after 843/847/844/836/840/837/841.
