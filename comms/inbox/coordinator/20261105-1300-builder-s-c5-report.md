# Report: S-C5 (scout round 3), builder. UNVERIFIED (cloud, no GX10). HIGH CARE: signed attestation evidence.
Claim check: no branch or note for strict /verify ok handling.
PR 518 (draft): https://github.com/SpinStateLabs/field-platform/pull/518, branch fix/verify-ok-must-be-true-sc5, head e6b0b657b849a435e516aa9e4e20ce70e087b3d5 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: attestation, incident-replay).
Bug (R, 16 red attestation + 15 red replay): attestation _integrity published INTACT for any truthy `ok` ({"ok":"false"}, {"ok":1}...) in a signed pack; incident-replay read the same bodies as intact. Fix: intact only for `ok is True`; False unchanged (BROKEN / CHAIN BROKEN); busy unchanged; any other ok = no verification result (attestation: unavailable; replay: unverified), fixed text, no echo.
Behaviour change for the reviewer: a /verify body with NO ok key used to read BROKEN (reason None), now unavailable/unverified. The real sealed-ledger always answers a boolean; I did not read its response model line by line.
38 tests; attestation-reporter 275 passed, incident-replay 115 passed; anchors --check 0 wrong; one mutant per service killed.
Not run: other suites.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513, 514, 517, 518; none merged by me.
Round 3 not yet taken: S-C2, C3, C4, C6, C7, C8; docs/CI S-D1..D8 (S-D6 timeout-minutes is ci.yml: one ci.yml PR per batch).
