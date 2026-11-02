gx10 verifier A, C-1152: suite-count drift check across the landings MERGE 12 to 15, versus the full run on main 05942b984e5338f56ebfd5597a57f0b9c22307a3. Counts and suite names only. All numbers come from the reports named below (HIGH for the transcription, I re-read each report); nothing was re-run for this card.

Sources: main 05942b98 = my C-1135 run (20261102-0300-...-c1135-profile.md); MERGE 12 cb19 = my 20261101-2119 report; MERGE 13 rb-stack2 = verifier B 20261102-0351; MERGE 14 cb21 = my 20261102-0020; MERGE 15 PR 431 = verifier B 20261102-1245 (its head IS main 05942b98).

Passed counts per suite (skips: core+sealed 4, tools 4, compliance-crosswalk 5 in every run; 0 failed everywhere):
suite | cb19 | rb-stack2 | cb21 | PR 431 = main
core+sealed-ledger | 2340 | 2340 | 2340 | 2346
tools | 3711 | 3717 | 3733 | 3749
field-agent | 153 | 207 | 207 | 207
agent-registry | 306 | 306 | 306 | 306
attestation-reporter | 221 | 221 | 221 | 221
claude-approver | 315 | 315 | 315 | 315
compliance-crosswalk | 369 | 369 | 369 | 369
conformance-sentinel | 260 | 260 | 260 | 263
delegation-authority | 247 | 247 | 247 | 252
federation-broker | 188 | 188 | 188 | 188
force-gateway | 447 | 447 | 447 | 448
incident-replay | 91 | 91 | 91 | 97
kill-switch | 242 | 242 | 242 | 242
lifecycle-manager | 264 | 264 | 264 | 267
ops-console | 300 | 448 | 448 | 457
spend-governor | 285 | 285 | 285 | 291

FINDING: none. No suite count went DOWN across any of the four landings. Every step is flat or up: cb19 to rb-stack2 is tools +6, field-agent +54, ops-console +148 (the stack carries PRs 358, 359, 348); rb-stack2 to cb21 is tools +16 (PR 432 tests); cb21 to PR 431 is core +6, tools +16, conformance-sentinel +3, delegation-authority +5, force-gateway +1, incident-replay +6, lifecycle-manager +3, ops-console +9, spend-governor +6. (The jumps in field-agent and ops-console are as expected from those PRs, MEDIUM, read from the PR file lists in the reports, not re-derived.) Going back one more step, the MERGE 11 run (ma2e) had every count at or below cb19: no drop there either.

Main run agrees with the independent PR 431 run (HIGH): my main profile and verifier B PR 431 run match in all 16 suites and in the skip counts, as they should (same tree). The three-times tools check by verifier B (C-1137) also gave identical counts.

Limits (LOW to MEDIUM): a passed count that stays equal can hide one test removed and one added; only a count that goes down shows up here. The runs were on different bases (each batch on the main at its time), so a flat count across a landing means no net loss, not no churn. cb24 (PR 438 + 433 on this main) is running now; its counts should be at or above the main column, and I will say so in its report.
