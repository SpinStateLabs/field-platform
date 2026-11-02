# Lane 1: withdraw from C-1172, keep C-1171
Read the coordinator ruling (20261103-1330, Lane 12 owns C-1172, PR 456 head 77f0b8a2). Withdrawn. My duplicate draft PR 458 (branch lint/auth-headers-c1172, head a13e25dc) is closed; the branch stays on origin unmerged, nothing else touched.
- Evidence for PR 456's reviewer: its four commits and mine have identical patch-ids in the same order (5ac0553a, 511d45c0, 3e053ad8, 99e67375), so the two rebuilds carry the same patches; my head had 35 of 35 lint tests passing on b39287c1 (Windows).
- C-1171 stays mine: PR 444's six commits rebuilt on b39287c1 on branch batch/lifecycle-cli-344-425-c1171, patch-ids identical to PR 444's; the lifecycle-manager suite is running (not yet pushed). Report follows.
