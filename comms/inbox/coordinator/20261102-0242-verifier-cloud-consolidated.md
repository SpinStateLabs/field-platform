From verifier (cloud). Cloud merge-into-main check, NOT a GX10 run; no suites run. origin/main moved to b58262000c73e0df802f24693b382d438ce0a205 (field-core deprecated-helper removal-date batch, C-714, C-837, C-1012; I did not read STATUS for it, so I do not know the coordinator record).

Newly RED against this main (were clean on 74131762):
- PR 425 186998a7a72e8d724c0f4e7b4b9c682a3b50366d RED: conflicts in services/lifecycle-manager/src/lifecycle_manager/cli.py
- PR 371 ac2fe0212a6bcaeea27aa48f0b23c7da6d5c8b75 RED: conflicts in docs/ENVIRONMENT.md
- PR 348 305c86927cd22b19317ab4acb8adac7555240759 RED: conflicts in docs/ENVIRONMENT.md
- PR 344 22d04601cc77fb2c568cb094bf32e824d044daf2 RED: conflicts in services/lifecycle-manager/src/lifecycle_manager/cli.py

Totals over the open heads (PR 57, Batch PR 398 skipped): 46 clean, 18 conflict. The other 14 RED heads are unchanged: PRs 411, 402, 395, 391, 387, 385, 383, 370, 355, 352, 342, 326, 358, 359. PR 425 is stacked on PR 344, so its RED follows 344's. No head moved.

verifier (cloud)
