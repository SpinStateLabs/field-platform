From verifier (cloud). Cloud merge-into-main check, NOT a GX10 run; no suites run. origin/main moved to 32b6eaa389092a4695e36d35e9046560eb612d9d (stacked batch: ENVIRONMENT.md anchors for PRs 358, 359, 348; is_guarded C-1071; PR 402 content C-1043 landed; I did not read STATUS, so I do not know the coordinator record).

Newly RED against this main (were clean on b5826200):
- PR 409 2c089ebbb799c9b639309d33cb29889fa66fac61 RED: conflicts in packages/field-agent/src/field_agent/liveness.py
- PR 381 d46e1917a00669637cbd881b93e7e1e3005e0942 RED: conflicts in docs/ENVIRONMENT.md
- PR 372 1b8f9e3f7d453e95848b6a3cae0a271223421410 RED: conflicts in packages/field-agent/src/field_agent/liveness.py
- PR 336 853a5b1eb81d748146d17486ac9d269fb68bea93 RED: conflicts in docs/ENVIRONMENT.md

PR 402 (9f5a447ee47c4260661f23d61845beaca7a7c137) now merges clean because its content is on main; the PR head is still open.

Totals over the open heads (PR 57, Batch PR 398 skipped): 43 clean, 21 conflict. PRs 358, 359, 348 still conflict as heads (their content landed under new shas). No head moved (PR 425 186998a7a72e8d724c0f4e7b4b9c682a3b50366d, PR 308 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4, PR 411 896345e8105b12cdb2e4c03eecc3b3650342a68c).

verifier (cloud)
