Builder-N1: B-REBUILD-PR484@d43f7ec DONE. Draft PR 583 "rebuild of #484", branch rebuild/pr484-field-agent-actions, head 4885dc54848e91c1ecc1d4925770433ac9b5ed4f on main 97dcfec1. Old head d43f7ec1246be39e3c041c2a2c9a12fe9e4a9a7d (merge-base cd3b7690) named in the body with the range-diff.
Range-diff: `1: d43f7ec1 = 1: 4885dc54`, identical patch, clean cherry-pick, no change beyond the base. One new test file only (packages/field-agent/tests/test_actions_surface_c1206.py). PR 484 untouched.
Claim check: no existing rebuild PR or branch for #484 (open PR list, ls-remote, comms grep). [HIGH]
Ran: the new test file 5 passed (needs the service src dirs on PYTHONPATH because field-agent conftest imports agent_registry); environment_anchors --check 0 wrong; the four tools tests 260 passed, 1 failed (known c57 baseline).
NOT verified: other 15 suites, CI, GX10 (UNVERIFIED). Reviewer PASS and GX10 16/16 were on the OLD head; the new head is a different SHA and needs its own.
Decisions needed: none.
