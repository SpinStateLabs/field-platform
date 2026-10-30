# C-603 cloud read of PR 308 (Phase E, the words), public-safety class scan (Lane 9, UNVERIFIED: scan of added lines plus a read of the new sentinel and gateway wording; no test run; NO value printed anywhere here: class, file and line only)

VERDICT: PASS WITH CONDITIONS on the scan. The head is NOT the card's: the PR is now fc8b363 (a merge of main 5808a5c into the branch), not 7e0deec, and three of the PR's own files changed since 7e0deec. No address, path, estate hostname, mailbox, 40-hex build id or build/release id was added. Deploy-status and flag-state statements and a hardware name were (below).

OBJECTIONS FIRST
1. A scan by regex finds classes I thought of. It cannot find a sentence that states an estate fact in words I did not list. Treat "none found" as "none of these shapes".
2. The card asks two things: claims beyond the code, and public-safety classes. I did the second in full and the first only on the new one-liner rows I read (sentinel, gateway, crosswalk); the 356-line one-liners file is not read line by line.
3. My first scan pass in this session printed nothing because of a pipeline mistake (the script read its own heredoc as input); I caught it by cross-checking with plain grep and reran it from a file. The results below are from the rerun.

ASSUMPTIONS: PR head fc8b363 as fetched from refs/pull/308/head (git, HIGH). Added lines = `git diff origin/main...HEAD` against main 5808a5c.

SCAN RESULT (added lines only; classes: private IPv4, account paths, estate hostnames, mailbox, 40-hex id, build/release id, flag-state wording, hardware name)
- Private IPv4, account path, estate hostname, personal mailbox, 40-hex id, build or release id: NONE (HIGH for these regexes).
- F-C603-1 MEDIUM-LOW, class deploy status / flag state (25 lines in docs/capstone-evidence/v2-one-liners.md at :3, :44, :70, :85, :99, :110, :111, :126, :139, :141, :153, :160, :180, :195 and more; README.md:45; ROADMAP.md:25; STATE.md:329-330; integration/fly/entrypoint.sh:11): sentences state what is or is not armed or live on "either estate" (the repeated "Estate status" paragraph appears 12 times, one per row). Reads as a status claim in a public file; same class as C-514 (open, author of PR 308) which covers the Phase E evidence file only. Extend C-514 to the repeated paragraph and the ROADMAP/README/STATE lines, or ruling C-561 decides the class is allowed. Also: one sentence copied 12 times is 12 places to keep true.
- F-C603-2 LOW-MEDIUM, class estate hardware name (a model name of the estate hosts) in 8 added lines: STATE.md:317 and :330, v2-one-liners.md:3 and :218, integration/fly/README.md:16, integration/fly/entrypoint.sh:10, integration/fly/fly.toml:2, tasks/lessons.md:21. Not an address or a hostname; same ruling as C-561/C-606 (Don). Listed so the ruling covers these lines.
- F-C603-3 head moved: since 7e0deec three of the PR's files changed (ROADMAP.md, STATE.md, docs/capstone-evidence/phase-3.md); the other 21 are byte-identical (blob compare, HIGH). A reviewer who passed 7e0deec has not seen those three: delta card filed.

CLAIMS VS CODE (partial, MEDIUM): the new sentinel row says breaches are blocked "at the agent's action boundary (SDK/@governed; cooperative ...)", which matches what the PR 334 note says the code enforces (mode.py:3-5, engine.py:193-196; my C-608). The gateway row says org-wide "when deployed as the LLM egress proxy (not d...": a conditional, not a claim. The crosswalk row names "ISO/IEC 42001 (pending text purchase)": a stated gap, not a claim. The "shipped" and "built" cells point at module file names I did not open one by one.

NOT VERIFIED: tests (tools/tests/test_e_gate.py, tools/e_gate.py run), the 356-line file read in full, whether the merge into main changed any PR line's meaning.
CONCLUSION: PASS WITH CONDITIONS: carry F-C603-1/-2 into C-514 and the C-561/C-606 ruling; review the three changed files at fc8b363 before merge.
