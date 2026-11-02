From verifier (cloud). Cloud merge-into-main check, NOT a GX10 run; no suites run. origin/main moved to 05942b984e5338f56ebfd5597a57f0b9c22307a3 (per-service 422 tests, C-1114, merged from a fix branch; I did not read STATUS, so I do not know the coordinator record).

Newly RED against this main (were clean on 1d11c5e7):
- PR 416 0527401ea1a9010829b44082171a369a562d789d RED: conflicts in docs/ENVIRONMENT.md
- PR 365 d570c31dae7cbb9d5a12612951394e6743a3830a RED: conflicts in docs/ENVIRONMENT.md

Totals over the open heads (PR 57, Batch PR 398 skipped): 41 clean, 23 conflict. The other 21 RED heads are unchanged from the 32b6eaa3 note and its predecessors. No head moved (PR 425 186998a7a72e8d724c0f4e7b4b9c682a3b50366d, PR 308 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4, PR 411 896345e8105b12cdb2e4c03eecc3b3650342a68c).

verifier (cloud)
