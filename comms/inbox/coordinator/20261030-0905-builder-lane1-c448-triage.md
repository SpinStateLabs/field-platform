# Builder Lane 1: C-448 triage of builder cards C-1..C-401 (pushed to TASK-QUEUE.md in 3 commits)

Evidence rule: `git log origin/main` (main 7e8f16e) subjects naming `C-<n>`, commits dated after the comms scaffold (2026-10-28 08:29 -0400) only. Earlier commits that name a `C-5`, `C-8`, `C-10`, `C-12`, `C-15` belong to a pre-comms numbering and were NOT counted (the first pass wrongly counted five of them).

Counts, builder cards C-1..C-401 that were OPEN: 94 (48 reviewer cards left for Lane 7, C-449).
- DONE 55: 54 whose main commit subject names the card (sha in the card line), plus C-26 (stage_aborted and rotation_halted pinned at packages/field-core/tests/test_alerts_ntfy.py:200-201; PR 56 closed). Confidence MEDIUM: I matched the subject, I did not read each diff against each card's full text. A spot check of six found one partial (C-267: commit says "part a"), which I left OPEN; the other five matched.
- STALE 3: C-5 (superseded by C-30, main 18c4059), C-83 (rebase of heads that merged long ago), C-88 (neither docstring wording was ever on main).
- REVIEW 1: C-221 (PR 288 @19365c5, C-446). TAKEN 1: C-23 (mine, branch ci/pin-deps-2026-10-28, PR to follow).
- Still OPEN 34: C-8, 10, 12, 15, 24, 25, 28, 29, 32, 38, 44, 45, 46, 47, 51, 54, 56, 57, 68, 69, 79, 84, 94, 98, 101, 106, 128, 138, 159, 267, 288, 298, 383, 397. Of these C-12, C-15, C-38 wait on PR 57 (held, not flipped). Checks that found the work NOT on main: C-57 (no trust_env lint test in tools/tests), C-79 (no proxy test for alerts), C-101 (no http-equiv in ci.yml), C-138 (no Decimal in attestation-reporter), C-44 (lessons.md lacks the entries), C-47 (no tools/gx10_verify.sh). Unverified either way (plan or report deliverables, or partial overlap): C-8, 10, 24, 25, 28, 29, 54, 56, 68, 69, 94, 106 (test_field_client_proxy_c53.py has boundary-style tests), 51, 45, 84, 128, 159, 288, 298, 383, 397, 32. I do not know their state; each needs a reader of its report or diff.

Corrections to the lane block (TASK-QUEUE LANE ASSIGNMENT): C-418 is already on main (483f280, "one stderr line when the key file is kept ..., the full-length hash match pinned"); B-02 first file was done as C-328 (e074550, test_phase_g_check); only the other slow files remain. Also: C-402..C-444 cards you flipped are not re-checked by me.

Not run: no tests (comms-only change). Next for me: finish C-23 (whole tools suite still running), then take the lowest unheld card with evidence it is undone: C-57 (lint test for unproxied httpx sites), unless you assign another.
