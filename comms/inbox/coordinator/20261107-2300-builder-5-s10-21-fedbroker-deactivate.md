# B-S10-21 report (builder-5)
Draft PR 945: fedbroker deactivate/activate verbs. GET /contracts, re-PUT the stored contract with only `active` changed (URL-quoted id, operator-guarded write); unknown id is one line, exit 1; README section added.
Evidence: 6 tests in test_cli_deactivate_contract.py; first 4 fail on the unchanged CLI. Suite 255 passed (one of my own tests fixed afterwards and rerun alone 6/6). Anchors 0 wrong.
Overlap: PR 395 also edits services/federation-broker/README.md (possible small rebase); neither 395 nor 662 touches cli.py.
