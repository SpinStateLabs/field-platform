# C-659: delta review of PR 308 (head fc8b363, was 7e0deec), public-safety class, Lane 10

Reviewed: PR 308 head fc8b363 (a merge of main 5808a5c). The three files changed since 7e0deec: ROADMAP.md (+13 -12), STATE.md (+7 -3), docs/capstone-evidence/phase-3.md (+3 -1). Then the whole PR's added lines for the F-C603-1 / my F-L10-308-1 class (deploy status and flag state in a public file). Class and file:line only; no value printed.

VERDICT: PASS for the three-file delta (it changes no deploy-status or flag-state wording and no PR line's meaning). The PR as a whole STILL adds statements of the forbidden class in other files (below): a condition for merge, not a defect of the delta. Confidence HIGH (diff and grep run).

## ASSUMPTIONS
1. The delta equals main's own recent content merged into the branch (PR 311's figures); nothing there is the PR's own wording.
2. The class: a sentence that states which flag or arming state an estate is in, or that estates run certain images, in a public file.

## Objections first
1. A delta that is clean says nothing about the 21 unchanged files. The card scopes the three files; the class is PR-wide, so I scanned all added lines: 20 added statements of the class remain (section 3).
2. A merge can change meaning without changing a line (a figure now contradicts a neighbour). The three diffs are self-consistent: the test count line now says 8,308 collected on main a9dc4f3 and keeps the earlier 8,172 breakdown labelled as the earlier figure; the crosswalk figures say "as of the first build" with the current ones beside them. No contradiction found.
Steelman: the delta only brings the branch up to main.

## Results: the three-file delta
- ROADMAP.md: the test-count line moves to "8,308 tests collected on main a9dc4f3 on 2026-10-30 (`pytest --collect-only`, summed over 18 suites; collected, not passed, and not the CI matrix total)" and keeps the older per-package breakdown labelled "the earlier 8,172 at 48acfa6". That is the figure Lane 6 recomputed (C-499) and my C-507 read; collected, not passed, is stated. HIGH.
- STATE.md: the FC-E-04..06 heading goes from "branch ..., DRAFT" to "merged to main as fd01623, #13" (an ancestor of main, per C-499); the crosswalk line becomes "as of the first build ... 10 FC-* controls" with "(Now, on main a9dc4f3: 13 controls, 52 entries, 16 cited.)": the figures match the mapping module (13 controls; 16 cited, 23 pending-text, 13 pending-purchase = 52, my C-609 run).
- docs/capstone-evidence/phase-3.md: the same "as of this phase's first build (now ...)" labelling with a pointer to hardening.md.
- A commit id in these lines is a commit of THIS public repository's main (not an estate build identifier): allowed.
- None of the three diffs adds a sentence about an estate, a flag, an arming state or a deployment.

## Results: the PR-wide class (added by this PR, absent on main)
- README.md:45 and ROADMAP.md:25: "estates run these images and the Phase G arming is live" (2 added): deploy status plus flag state.
- docs/capstone-evidence/v2-one-liners.md:3: "REQUIRE not armed on either estate; Stage 1 LOG-ONLY only" and `:44`, `:70`, `:99`, `:126` and further rows: "Phase G arming (REQUIRE) is not live on either estate" (12 occurrences added); `:5`: a statement that a roster variable is "set on both estates" (flag state).
- integration/fly/README.md:17, integration/fly/entrypoint.sh:11 and STATE.md:318: "since the 2026-09-08 cutover" (3): a deploy-status date for the private estate.
- My earlier finding F-L10-308-1 ("the estates run enforce=0 at this commit") is gone from the PR (the only `enforce=0` hits left are the gateway README and its tests, legitimate).
- Not in this class and fine: "not deployed as such" lines (README.md:52, tasks/todo.md) state what the repository does NOT claim; "Declared" estate-status lines say "not live-verified".

## Findings
F-C659-1 MEDIUM-LOW: replace each statement above with the design fact or the condition ("arming `REQUIRE` turns the guard on; the repository does not state any estate's setting"); the card C-514 listed the class; this delta shows 20 instances that remain. The gate in v2-one-liners.md could carry the rule: a line that names "on either estate" or "both estates" is a finding.
F-C659-2 LOW: add the phrase class (`on either estate`, `on both estates`, `since the ... cutover`, `estates run`) to the public-safety guard of PR 342 as a forbidden-phrase class (it scans addresses, paths and mailboxes today).

## What I did NOT do
Did not compare the 21 unchanged files byte by byte (the card states they are identical); did not recount the test figures (C-499 did). Did not edit the PR.
