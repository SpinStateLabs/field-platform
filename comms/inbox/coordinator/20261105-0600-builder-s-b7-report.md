# Report: S-B7 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or comms note for registry CLI bad input.
PR 510 (draft): https://github.com/SpinStateLabs/field-platform/pull/510, branch fix/registry-cli-bad-input-sb7, head 62fe8e3144f86051fe4bd38ff6c5f7bf446719e3 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: registry).
Bug (R, 10 red tests): `registry add` with an invalid slug raised pydantic.ValidationError; `registry scan` with a missing file or directory raised FileNotFoundError/IsADirectoryError (docstring promises exit 2). Fix: named message, exit 2, field names or file name and exception TYPE only, never the content. Also covers the CLI half of scout P-2 (missing n8n path, invalid n8n JSON); P-2's scanner-shape and substring-match items untouched.
14 tests, failing first, green; registry suite 325 passed; environment_anchors --check 0 wrong (run BEFORE push this time, per my correction note 20261105-0500); two mutants killed (5 red, 6 red).
Test-premise correction: a 200-character slug is ACCEPTED (registered); I did not investigate whether a slug length cap is wanted. Possible follow-up card for the coordinator.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510; none merged by me.
Scout round 2 not taken: S-A6, S-B4, S-B5, S-B6.
