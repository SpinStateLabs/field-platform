# Report: S-A5 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or comms note for fly_identity_check /health shape.
PR 507 (draft): https://github.com/SpinStateLabs/field-platform/pull/507, branch fix/fly-identity-health-shape-sa5, head 9f593b59a86541b3702f0b3aa78d70702bbc0343 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane A: tools).
Bug (scout read it; reproduced here by 11 red tests): _health stored any decoded JSON; check_health then raised on null/number/string/true (a list passed `in`, failed at .get). Fix: non-dict -> {"_error": "NotAnObject"}; check_health tolerates a non-dict entry. 15 tests incl. the 65536-byte cap pin, failing first (11 red), green. New file + test_fly_identity_c5 102 passed; proxy-lint and anchors tests 138 passed; environment_anchors --check 0 wrong. Two mutants killed (6 red, 4 red).
Not run: the full tools suite, other suites.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507; none merged by me.
Scout round 2 not yet taken: S-A6, S-B4..S-B7.
