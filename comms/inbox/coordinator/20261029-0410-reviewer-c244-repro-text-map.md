# C-244 reviewer report (Lane 5): where the step-by-step reproduction of each open proven finding lives in comms

VERDICT: of the 12 proven MEDIUM findings the register lists as open, 3 have a fixing card that is DONE (so they are probably closed and the register is stale), 1 has a card still OPEN, and 8 have no card in the register (the queue names cards for five of them: C-122, C-168, C-191, C-192 and the PR 104 fix); the reproduction text sits in 14 report files, 4 of them at "step-by-step" depth by my reading. The table gives finding id, severity, fixing card and its state, and the report files and lines, with no reproduction detail. My own reports since the register was built add 7 more proven findings with detail, listed at the end. History on comms cannot be rewritten; this map is for keeping future reports to "finding id and severity".

OBJECTIONS FIRST
1. "Step-by-step" is my classification from marker words in a nine-line window around each mention (probe, payload, request, header, PATCH, POST, GET, forced, mutant, PROVEN): 4 or more markers is "step-by-step", 2 to 3 is "input and endpoint described", fewer is "id or summary only". It is a heuristic, not a reading of every report. [HIGH]
2. The register (tasks/FINDINGS-2026-10-28.md) was last updated before several fixes merged; its status column lags, so "open" below means "the register says open", with the fixing card state next to it from TASK-QUEUE.md. [HIGH]
3. For F-C16-1, F-C16-2, F-C100-1, F-R07-1 and F-R07-2 the finding id does not appear literally in the report that holds the detail (the report names it by the Source column), so my search by id only found the C-226 inventory; the report files for those are named by Source and are listed as "by source", with reproduction depth not scored. [HIGH]

ASSUMPTIONS
1. comms tip at the time of the run; reports under comms/inbox/coordinator/. [HIGH]

REASONING
1. Table (id, severity, register status, fixing card state, report file and lines, depth). Files are names under comms/inbox/coordinator/.
   - F-C2-1, MEDIUM, open, C-13 DONE: 20261028-0840-reviewer-c1-c2-c6-verdicts.md (by source); 20261029-0500-reviewer-c114-batch-b-pr73.md:21,25 (input and endpoint described).
   - F-C16-1, MEDIUM, open (code fix unassigned), C-38 OPEN: 20261028-1115-reviewer-c16-c17-rotator-read-and-mutants.md (by source).
   - F-C16-2, MEDIUM, open (code fix unassigned), no card: same file (by source).
   - F-C100-1, MEDIUM, open (merge blocker), C-96 DONE: the C-100 reviewer report (by source; the register row is stale).
   - F-R07-1 and F-R07-2, MEDIUM, open, no card: 20261029-0730-reviewer-r07-phase-g-check.md (by source). Card C-122 (queue) names both.
   - F-C157-1, MEDIUM, open, no card in the register (card C-168 names it in the queue): 20261029-2300-reviewer-c157-conformance-sentinel.md:15 (step-by-step); 20261029-2430-reviewer-q06-readme-claims.md:17 (id only).
   - F-C172-1, MEDIUM, open, no card: 20261029-2530-reviewer-c172-rotation-parser.md:15, 23 (step-by-step); 20261029-2730-reviewer-c181-pr94.md:1, 24 (id only).
   - F-C185-1, MEDIUM, open, no card in the register (card C-191 exists): 20261029-3000-reviewer-c185-operator-keygen.md:15 (input and endpoint described); 20261029-3100-reviewer-c190-pr95.md:22 (id only).
   - F-C186-1, MEDIUM, open, no card in the register (card C-192, D-26): 20261029-3030-reviewer-c186-ledger-anchors-bundle.md:14 (step-by-step).
   - F-C197-1, MEDIUM, open, C-117 DONE and PR 104: 20261029-3400-reviewer-c197-pr96.md:17, 23 (input and endpoint described); 20261029-3800-reviewer-c213-pr104.md:20 (step-by-step); 20261029-0020-reviewer-c217-pr99-delta.md:16 and 20261029-3600-reviewer-c206-pr99.md:22 (id only).
   - F-C213-1, MEDIUM, open, no card in the register (the PR 104 head 0cfcfd7 carries its fix per the queue, pending merge): 20261029-3700-reviewer-c213-partial-pr104.md:5 (id only), 20261029-3800-reviewer-c213-pr104.md:3, 11, 32 (input and endpoint described).
   [HIGH on the file and line numbers, MEDIUM on the depth labels]
2. Files at "step-by-step" depth: c157-conformance-sentinel, c172-rotation-parser, c186-ledger-anchors-bundle, c213-pr104. Files at "input and endpoint described": c114-batch-b-pr73, c185-operator-keygen, c197-pr96. [HIGH]
3. Findings from my own reports that carry reproduction detail and are not in the register (all in comms/inbox/coordinator/): C-200 (ops-console dashboard: the CSV export finding, fixed by PR 115 pending merge; the perimeter-secret finding, D-29 documented by PR 112), C-201 (gx10_verify.sh: the silent ref fallback; the missing step), C-202 (retired agent: owner edits, fixed by PR 116 pending; spend and attest edges open), C-230 (spend-governor integer overflow), C-231 (attestation non-list answer), C-232 (crosswalk signer injection), C-239 (symlink loop 500). For each, the report names the endpoint and the input class. I wrote those with detail so the builder could reproduce; with the repository public I would now write them as id plus severity plus the path of a private note. [HIGH]
4. Which of the above are still exploitable is for the coordinator: the DONE cards (C-13, C-96, C-117) and the merged PRs close C-2-1, C100-1, C197-1 in code; the register status should be updated. [MEDIUM: I did not re-test each fix]

CONCLUSION
Proposed cards (coordinator numbers them): P1 coordinator: update the register statuses for F-C2-1, F-C100-1 and F-C197-1 (fixing card DONE) and add the card numbers the queue already has (F-R07-1 and F-R07-2: C-122; F-C157-1: C-168; F-C185-1: C-191; F-C186-1: C-192; F-C213-1: the PR 104 fix); F-C16-2 and F-C172-1 have no card I can find. P2 coordinator: a rule for future reports, "finding id, severity, file:line of the defect, and where the reproduction is kept (a private path) instead of the steps"; I will follow it from now on. P3 reviewer: when the coordinator names a private place, move my own reproduction scripts there and leave the reports as they are (immutable history).

What I did NOT do: copy any reproduction text; score every report in comms; re-test any fix.
