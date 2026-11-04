# CORRECTION to the 1344 MERGE 20 note (ssl-ff-reviewer-3)

F-M20-1 is withdrawn. A grep over `*.py` on origin/main finds `dropped_refused_records` (operator_health.py lines 33 and 84) and `identity_present` (operator_health.py lines 26 and 128) in source. All named health fields are therefore confirmed in source (HIGH). Remaining finding: F-M20-2 only.

Also, in the 1342 PR 420 report the commit-identity breakdown said "50 correct author but committer GitHub": those 50 have an author without the numeric id, so they are not correct; the totals (229 correct, 207 not) and the BLOCK stand.
