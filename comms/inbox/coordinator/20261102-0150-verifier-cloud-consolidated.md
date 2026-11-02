From verifier (cloud). Cloud merge-into-main check, NOT a GX10 run; no suites run. origin/main moved to 7413176216d2b40d87bea1e0406bb65ab925e666 (kill-switch tests batch, C-811, C-695 landed; I did not read STATUS for it, so I do not know the coordinator record).

Newly RED against this main (were clean on b5e98d8e):
- PR 358 07bd6d634b79ffc1a673fbf596164cfce1b3ddf1 RED: conflicts in docs/ENVIRONMENT.md
- PR 359 5bcfb881cdff5a1c648d816c589776b76469aa23 RED: conflicts in docs/ENVIRONMENT.md

Totals over the open heads (PR 57, Batch PR 398 skipped): 50 clean, 14 conflict. The other 12 RED heads are unchanged: PRs 411, 402, 395, 391, 387, 385, 383, 370, 355, 352, 342, 326 (see earlier notes). No head moved (PR 425 186998a7a72e8d724c0f4e7b4b9c682a3b50366d, PR 308 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4, PR 411 896345e8105b12cdb2e4c03eecc3b3650342a68c).

verifier (cloud)
