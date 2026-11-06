# B-COND-PR646-032ca35: no push; both conditions are verification

Head stays 032ca35f. Conditions: C1 GX10 16/16 on the head rebased on current main (clean merge-tree per the reviewer), C2 CI green: verifier and CI work, no builder code, no code defect in the four changed lines.
LOW follow-ups for B-FU-PR646-*: (1) the displayed build_sha site (M4) is unpinned; (2) the same `$`-with-`.match` bug class remains in tools/volume_admin.py at five sites (_MANIFEST_NAME at lines 204 and 223, _KEY_NAME at 255, 286, 317), names that reach file paths: an S3-18 sweep card, builder-sized; (3) the pattern shapes P1 to P4 (agent length bound, space in agent, hash minimum, upper-case hex) survive all tests and are out of this PR's claim. I did not touch the PR so its reviewed head stays frozen.
