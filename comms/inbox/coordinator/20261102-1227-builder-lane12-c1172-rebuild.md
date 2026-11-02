# Builder Lane 12: C-1172 report (PR 445 + 449 rebuilt on main b39287c1)

Branch rebuild/c1172-pr445-449-l12, head (full): 77f0b8a296c33a69bef9d2654c4e8ec8f9ae0937, base main b39287c14410144dfcb1e7e35f383dc37671f4bb, draft PR opened (number in the PR list; see comment).
Sources read from git ls-remote: PR 445 head 307b1cf0ab81e0e65d805908f4c077cd38e697bf, PR 449 head ece150d74add33fd8c611606e355dbb8778ab1d1 (445 is an ancestor of 449). Cherry-picked 3d291ddb, 307b1cf0, efc38180, ece150d7 in that order: no conflicts. Patch-id (stable) of all 4 equals the original (HIGH, measured). Both identities noreply on all 4.
Results (HIGH, measured): test_auth_headers_outside_core_c1149.py 35 passed on the head; environment_anchors.py --check 0 wrong rows. The allowlist still equals the scan on b39287c1.
NOT RUN: the 16 suites (GX10), CI (just opened). PR 445 and 449 heads untouched; they can be closed once this lands.
