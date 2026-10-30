VERDICT: AUDIT COMPLETE (63 inbox reports carry UNVERIFIED in their first 700 characters; 27 sit on a head that has since moved, 19 sit on the current head with no GX10 note naming that sha, 17 sit on the current head with a note that names the sha and a GX10 run). UNVERIFIED itself: this is a cloud audit built from file text and ls-remote; no GX10 run was done or checked.

OBJECTIONS FIRST
1. The GX10 test is a text heuristic: a non-UNVERIFIED file that names the first seven characters of the sha, contains "GX10" and one of '16 suites', '16 "== "' or '0 failed'. It can count a builder's own run (not an independent re-run) and it can miss a run recorded in a file that gives the sha only in full or not at all. Group C therefore needs a human to open the named note and read the suite count; group A may include a run recorded in another form.
2. The scope is files whose first 700 characters contain UNVERIFIED and whose first line starts with VERDICT. A cloud report that states UNVERIFIED later in the text, or has no VERDICT line, is not listed.
3. The current head of each PR is `git ls-remote` of refs/pull/N/head at the time of this audit (2026-11-04 evening); heads move, so group B/A membership will change.
4. Lane attribution is by file name only; Lane 9 and Lane 10 ("design") reports are included because they say UNVERIFIED.
5. Report path is the single fact I can vouch for in every row; the PR number comes from the file name (or the first lines) and was not re-read in each report.

ASSUMPTIONS
A1 A report applies to its head sha only (FORCE rule). A2 A GX10 re-run on the same head means 16 suites with 0 failed or error lines. A3 'What a re-run must check' is by change class (docs, tests, production) plus the report's own conditions.

REASONING
1. Collected every file in comms/inbox/coordinator whose first line starts with VERDICT and whose first 700 characters contain UNVERIFIED: 63 files. 2. Extracted the 40-character sha from the VERDICT line and the PR number from the file name. 3. Compared the sha to the PR's current head from ls-remote: different = group B. 4. For the rest, searched all non-UNVERIFIED reports for a note naming the sha with GX10 evidence: none = group A, some = group C. 5. Classified each PR by change class from my own reading of the diffs where I reviewed them, otherwise from the PR title in the queue.


## B. The report's head has MOVED (the report no longer applies; a delta review or re-run is needed)
What a re-run or delta must check: the diff from the report's head to the current head (does the change touch what the report's conditions named), then the class check below on the NEW head.

| report | PR | head the report covers | current head | change class |
|---|---|---|---|---|
| `20261102-0730-reviewer-c18-pr57-rotation-py-read.md` | 57 | `09dcbcd0c70c4fbe284287b4a6c0a4b498fb34e9` | `30ac1e11c259656259148e230fbde5ae6facc6c1` | production code |
| `20261102-1200-reviewer-pr57-delta-09dcbcd-to-11c55c7.md` | 57 | `11c55c7dc08f7abfca36d19550bd92eca5bdcaf5` | `30ac1e11c259656259148e230fbde5ae6facc6c1` | production code |
| `20261104-0430-reviewer-c649-pr346-commit-identity-guard.md` | 346 | `6e4a9d1cfbda83b32ad87dd4c6c2343e7e573de8` | `afb25af61f30a64e5e2d4ee0b3dac670f0a9917e` | production code |
| `20261104-0450-reviewer-c654-pr335-adr07-note.md` | 335 | `2e00c73ed070005383d723888e86c349365d7d36` | `fc73f64807d377dcebd00ff64091f8a14fd98867` | docs / comment only |
| `20261104-0530-reviewer-c651-pr348-console-encoding-5xx.md` | 348 | `6b685fd680bdc68f907b6c06b3851d4ac3957c75` | `db9bad0c1dbe5d4bdba41d03aba4074c49e8a627` | production code |
| `20261104-0600-reviewer-c652-pr340-integration-doc-claims.md` | 340 | `1643d20a1fe304750d3cc67e90d83d4d66ac3687` | `bde88a255188a6d12c16d8e6fcc9285376d78399` | docs / comment only |
| `20261104-0630-reviewer-c653-pr341-adr10-gateway-comments.md` | 341 | `cde33034d50e4d99bce149af99832fb9999bf4fd` | `b6f9b613166f730af46575e5519226fb708a0c97` | docs / comment only |
| `20261104-0700-reviewer-c654-pr335-adr07-crosswalk-note.md` | 335 | `2e00c73ed070005383d723888e86c349365d7d36` | `fc73f64807d377dcebd00ff64091f8a14fd98867` | docs / comment only |
| `20261104-0730-reviewer-c656-pr337-architecture-services-arrows.md` | 337 | `c3fd1447e249aa080f277d85c5b9964165c2b371` | `72e8fae42a2a2e70df75253b4e665c862e79bb24` | docs / comment only |
| `20261104-0800-reviewer-c668-pr318-proxy-lint-aliases.md` | 318 | `c163ea2a1899b97ab2bb74e612e15f12d4d855a4` | `4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc` | production code |
| `20261104-0850-reviewer-c677-pr346-commit-identity-guard.md` | 346 | `fb9dc612fbdbcfaafdc9879d990872c91ef93f9f` | `afb25af61f30a64e5e2d4ee0b3dac670f0a9917e` | production code |
| `20261104-0920-reviewer-c678-pr340-integration-doc.md` | 340 | `1643d20a1fe304750d3cc67e90d83d4d66ac3687` | `bde88a255188a6d12c16d8e6fcc9285376d78399` | docs / comment only |
| `20261104-0950-reviewer-c679-pr341-adr10-note.md` | 341 | `cde33034d50e4d99bce149af99832fb9999bf4fd` | `b6f9b613166f730af46575e5519226fb708a0c97` | docs / comment only |
| `20261104-1030-reviewer-c680-pr337-architecture-services-arrows.md` | 337 | `c3fd1447e249aa080f277d85c5b9964165c2b371` | `72e8fae42a2a2e70df75253b4e665c862e79bb24` | docs / comment only |
| `20261104-1230-reviewer-c698-pr353-resolved-check-contract.md` | 353 | `783a85fa9d32818ead55853bc20cda41d77142c2` | `5d5cbf733c73875f279f6a47dca00ac9be157eaa` | production code |
| `20261104-1300-reviewer-c699-pr352-force-gateway-no-value-echo.md` | 352 | `3a525dcc13899ef821975ebfbbb995308667c2e4` | `5762a3e81f51eefe3242ca9e39016f1db8c6b817` | production code |
| `20261104-1400-reviewer-c683-pr330-guarded-operator-pair.md` | 330 | `544f577cdffd0607ea14d61936f34f9119dc20dc` | `ddc5551d26e46b3c0f311b5cc7e31c6a5190ffa5` | production code |
| `20261104-1400-reviewer-c701-pr349-revoke-idempotent.md` | 349 | `50c87b9f0924a407ddb62b665323df84b1850a24` | `1e3dea5a7fac517757e31290e125652930d6568c` | production code |
| `20261104-1530-reviewer-c704-pr359-canary-read-cap.md` | 359 | `dcff705136a1f69e27b74631dbdd011a8e2ca591` | `77b689c2d0f790d72df21ec750adb0f17726c9ef` | production code |
| `20261104-1620-reviewer-c685-pr326-upstream-body-second-angle.md` | 326 | `203810fbc37cc0312278ff869ad95d8bad776a3e` | `da33a9a1541e65010ac6ef53d075040b0b3fdd65` | production code |
| `20261104-1630-design-c698-pr353-exit-contract.md` | 353 | `783a85fa9d32818ead55853bc20cda41d77142c2` | `5d5cbf733c73875f279f6a47dca00ac9be157eaa` | production code |
| `20261104-1700-design-c699-pr352-numeric-tunables-health.md` | 352 | `3a525dcc13899ef821975ebfbbb995308667c2e4` | `5762a3e81f51eefe3242ca9e39016f1db8c6b817` | production code |
| `20261104-1730-design-c701-pr349-revoke.md` | 349 | `50c87b9f0924a407ddb62b665323df84b1850a24` | `1e3dea5a7fac517757e31290e125652930d6568c` | production code |
| `20261104-1730-reviewer-c699-pr352-tunables-origin-independent.md` | 352 | `3a525dcc13899ef821975ebfbbb995308667c2e4` | `5762a3e81f51eefe3242ca9e39016f1db8c6b817` | production code |
| `20261104-1800-reviewer-c712-pr349-introspection-leak.md` | 349 | `50c87b9f0924a407ddb62b665323df84b1850a24` | `1e3dea5a7fac517757e31290e125652930d6568c` | production code |
| `20261104-1910-reviewer-c752-pr353-exit-contract.md` | 353 | `783a85fa9d32818ead55853bc20cda41d77142c2` | `5d5cbf733c73875f279f6a47dca00ac9be157eaa` | production code |
| `20261104-2000-design-c704-pr359-read-caps.md` | 359 | `dcff705136a1f69e27b74631dbdd011a8e2ca591` | `77b689c2d0f790d72df21ec750adb0f17726c9ef` | production code |

## A. Current head equals the report's head, no GX10 note names that sha
What a re-run must check (by class): docs: re-read each claim against source at the cited file:line on the exact head; confirm no estate address, flag value, build SHA or deploy status; for a comment-only code diff, an AST comparison (docstrings dropped) of old and new. Tests: run the affected test files on the GX10 on the exact head (the whole directory), then the mutants named in the report (each red) and the unmutated full set for the package. Production: full set on the GX10 on the exact head (16 suites, 0 failed or error), the probes named in the report, and the mutant table of the report (each red).

| report | PR | head the report covers | current head | change class |
|---|---|---|---|---|
| `20261104-0900-reviewer-c686-pr324-flag-no-value-followups.md` | 324 | `ca70eec1a5c02da193e72744d70cbdd7901c2f05` | `ca70eec1a5c02da193e72744d70cbdd7901c2f05` | production code |
| `20261104-0930-reviewer-c687-pr333-events-cursor.md` | 333 | `39f86364de248843666524bcdf3b3985d1d6ac38` | `39f86364de248843666524bcdf3b3985d1d6ac38` | production code |
| `20261104-1100-reviewer-c696-pr356-internal-host-predicate.md` | 356 | `846242e5919d796ad56564dccb44c5bc21b50b4c` | `846242e5919d796ad56564dccb44c5bc21b50b4c` | production code |
| `20261104-1130-reviewer-c681-pr339-innerhtml-audit.md` | 339 | `ab709ed9bf7a2544ca3a253fa055248b43ef684a` | `ab709ed9bf7a2544ca3a253fa055248b43ef684a` | tests only |
| `20261104-1230-reviewer-c682-pr336-kill-switch-guard.md` | 336 | `fe6c2beaecd662a4710f7d2a61d8a3ee03cceb05` | `fe6c2beaecd662a4710f7d2a61d8a3ee03cceb05` | production code |
| `20261104-1500-reviewer-c684-pr322-federation-delta.md` | 322 | `935a8d002f454d6efb266f8d18bcfc6d1c773abd` | `935a8d002f454d6efb266f8d18bcfc6d1c773abd` | production code |
| `20261104-1500-reviewer-c703-pr360-burst-boundary-window-start.md` | 360 | `3aacd5a3e36fca9dc7904bcb226be1ca902848b1` | `3aacd5a3e36fca9dc7904bcb226be1ca902848b1` | tests only |
| `20261104-1630-reviewer-c706-pr363-video-script-figures.md` | 363 | `3b2833130eba9f07ec921438ff53fe002fb21fb0` | `3b2833130eba9f07ec921438ff53fe002fb21fb0` | docs / comment only |
| `20261104-1700-reviewer-c707-pr362-alert-observer-survivors.md` | 362 | `54c5b867e69ce330790144c5f4cf753707deffb3` | `54c5b867e69ce330790144c5f4cf753707deffb3` | tests only |
| `20261104-1830-reviewer-c710-pr318-delta-lint-aliases.md` | 318 | `4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc` | `4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc` | production code |
| `20261104-1905-reviewer-c751-pr352-delta-since-c699.md` | 352 | `5762a3e81f51eefe3242ca9e39016f1db8c6b817` | `5762a3e81f51eefe3242ca9e39016f1db8c6b817` | production code |
| `20261104-1920-reviewer-c755-pr363-video-script.md` | 363 | `3b2833130eba9f07ec921438ff53fe002fb21fb0` | `3b2833130eba9f07ec921438ff53fe002fb21fb0` | docs / comment only |
| `20261104-1930-design-c703-pr360-burst-boundary.md` | 360 | `3aacd5a3e36fca9dc7904bcb226be1ca902848b1` | `3aacd5a3e36fca9dc7904bcb226be1ca902848b1` | tests only |
| `20261104-2100-design-c706-pr363-video-script.md` | 363 | `3b2833130eba9f07ec921438ff53fe002fb21fb0` | `3b2833130eba9f07ec921438ff53fe002fb21fb0` | docs / comment only |
| `20261104-2130-design-c707-pr362-survivors.md` | 362 | `54c5b867e69ce330790144c5f4cf753707deffb3` | `54c5b867e69ce330790144c5f4cf753707deffb3` | tests only |
| `20261104-2230-design-c709-pr350-batch-bx.md` | 350 | `none` | `63e91b21b20a193f7150f386be27d6194f4b8ecd` | production code |
| `20261104-2330-design-c710-pr318-merge-fix-lint.md` | 318 | `4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc` | `4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc` | production code |
| `20261105-0000-design-c711-pr317-rate-rounding.md` | 317 | `9cc52212607105e7e0d0ac5c81b902810f197693` | `9cc52212607105e7e0d0ac5c81b902810f197693` | production code |
| `20261105-0030-design-c729-pr326-delta-c642.md` | 326 | `da33a9a1541e65010ac6ef53d075040b0b3fdd65` | `da33a9a1541e65010ac6ef53d075040b0b3fdd65` | production code |

## C. Current head equals the report's head, a note names the sha and GX10
What to check: open the named note and confirm it ran this exact sha with 16 suites and 0 failed or error; if it is the author's own run, an independent re-run is still the rule for production code.

| report | PR | head the report covers | current head | change class |
|---|---|---|---|---|
| `20261104-0420-reviewer-c648-pr345-compose-forms.md` | 345 | `f3787c93a743e1852b5bec805524bbaecd62328e` | `f3787c93a743e1852b5bec805524bbaecd62328e` | tests only |
| `20261104-0455-reviewer-c650-pr347-edge-probe-shapes.md` | 347 | `3c2d51c29f20146f4958d5dcff9875642e5ae094` | `3c2d51c29f20146f4958d5dcff9875642e5ae094` | tests only |
| `20261104-1000-reviewer-c688-pr331-anchors-parser.md` | 331 | `1a45db00bcbf6c20828e7bc757d81a07ecbc8e18` | `1a45db00bcbf6c20828e7bc757d81a07ecbc8e18` | production code |
| `20261104-1130-reviewer-c697-pr357-alerts-default-opener-test.md` | 357 | `b2f3b161e54b0e6659c1149acb45b43a475e0a60` | `b2f3b161e54b0e6659c1149acb45b43a475e0a60` | tests only |
| `20261104-1330-reviewer-c700-pr351-operator-key-limits-doc.md` | 351 | `af1e7cc856ecfc6fa4064c7994dc07d34f356f85` | `af1e7cc856ecfc6fa4064c7994dc07d34f356f85` | docs / comment only |
| `20261104-1430-reviewer-c702-pr355-format2-ambiguity-cap.md` | 355 | `191affb8a9c89fa59506ec30029ce4b5c4857ca7` | `191affb8a9c89fa59506ec30029ce4b5c4857ca7` | tests only |
| `20261104-1600-design-c697-pr357-alerts-opener.md` | 357 | `b2f3b161e54b0e6659c1149acb45b43a475e0a60` | `b2f3b161e54b0e6659c1149acb45b43a475e0a60` | tests only |
| `20261104-1600-reviewer-c705-pr358-guarded-allowlist-host.md` | 358 | `d5d4fc6d6e75e62a95e8ac68ed97515d455ad30d` | `d5d4fc6d6e75e62a95e8ac68ed97515d455ad30d` | tests only |
| `20261104-1730-reviewer-c708-pr361-workflow-lint-variants.md` | 361 | `5a58ee8d4cc9a65760591b4a190019b14fa2318e` | `5a58ee8d4cc9a65760591b4a190019b14fa2318e` | tests only |
| `20261104-1800-design-c690-pr355-format2-ambiguity-retired-cap.md` | 355 | `191affb8a9c89fa59506ec30029ce4b5c4857ca7` | `191affb8a9c89fa59506ec30029ce4b5c4857ca7` | tests only |
| `20261104-1830-design-c691-pr351-operator-key-limits-doc.md` | 351 | `af1e7cc856ecfc6fa4064c7994dc07d34f356f85` | `af1e7cc856ecfc6fa4064c7994dc07d34f356f85` | docs / comment only |
| `20261104-1900-reviewer-c744-pr355-builder-claims.md` | 355 | `191affb8a9c89fa59506ec30029ce4b5c4857ca7` | `191affb8a9c89fa59506ec30029ce4b5c4857ca7` | tests only |
| `20261104-1915-reviewer-c753-pr357-default-opener.md` | 357 | `b2f3b161e54b0e6659c1149acb45b43a475e0a60` | `b2f3b161e54b0e6659c1149acb45b43a475e0a60` | tests only |
| `20261104-1940-reviewer-c747-pr364-env-scan-aliases.md` | 364 | `beb3a7ace0252afdff41bdf173261bac3911276e` | `beb3a7ace0252afdff41bdf173261bac3911276e` | tests only |
| `20261104-1945-reviewer-c754-pr361-pr364-together.md` | 361 | `5a58ee8d4cc9a65760591b4a190019b14fa2318e` | `5a58ee8d4cc9a65760591b4a190019b14fa2318e` | tests only |
| `20261104-2030-design-c705-pr358-host-allowlist.md` | 358 | `d5d4fc6d6e75e62a95e8ac68ed97515d455ad30d` | `d5d4fc6d6e75e62a95e8ac68ed97515d455ad30d` | tests only |
| `20261104-2200-design-c708-pr361-workflow-lint.md` | 361 | `5a58ee8d4cc9a65760591b4a190019b14fa2318e` | `5a58ee8d4cc9a65760591b4a190019b14fa2318e` | tests only |

CONCLUSION
The highest-risk items are group A or B production-code entries (reports 20261104-0530 C-651 PR 348, 1400 C-701 PR 349 and 1800 C-712, 1100 C-696 PR 356, 0930 C-687 PR 333, 1000 C-688 PR 331, 1530 C-704 PR 359, 0430 C-649 PR 346), plus PR 57 (two reports, head moved). For those a full 16-suite GX10 run on the current head is the missing evidence. Docs-only items need only a claim re-read at the current head.

FINDINGS
F-C756-1 MEDIUM, group B (27 reports): the covered head is stale; do not cite these reports for the current head. HIGH.
F-C756-2 MEDIUM, group A (19 reports): no GX10 note names the covered sha. MEDIUM (heuristic).
F-C756-3 LOW, group C: a note names the sha; confirm it is a 16-suite run. MEDIUM.
F-C756-4 INFO, my own reports (Lane 15) are in the lists above; every one of them states what it could not verify.

NOT VERIFIED: any GX10 result; GitHub CI for any PR; reports whose UNVERIFIED mark lies beyond 700 characters or whose first line is not a VERDICT.
