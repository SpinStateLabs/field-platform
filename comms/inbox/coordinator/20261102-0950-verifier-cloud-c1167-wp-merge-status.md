From verifier (cloud). C-1167 result. Cloud merge-into-main check, NOT a GX10 run; no suites run. Main used: 05942b984e5338f56ebfd5597a57f0b9c22307a3 (05942b98, re-read at report time).

Method: git merge-tree --write-tree --name-only origin/main refs/pull/<n>/head after a full fetch. A clean merge is evidence of a clean merge only.

RED: none of the PRs below conflict.

- PR 308 7f7ac748e6b70447738ed5acd8fed6c02fa9e8b4 CLEAN
- PR 368 37c19167b06b955dc487801830a102d569058f1e CLEAN
- PR 380 24d5482b1425a70854e02c5ceabe958df9b73704 CLEAN
- PR 57 30ac1e11c259656259148e230fbde5ae6facc6c1 CLEAN
- PR 444 9e514a6ed7037415b24a20f3de21cd3fd4cd8168 CLEAN

Mapping (WP to PR): PR 308 = WP8 (named in card C-1159); PR 368 = field-mcp PR 1 and PR 380 = field-mcp PR 2 (I could not tie these to a WP id from the repo, so I included them as the field-mcp pair; MEDIUM); PR 57 = R4a rotator core (WP4 prerequisite; I do not know if a rebuild branch exists: none on origin matches r4a besides feat/kr-r4a-rotator-core, the head of PR 57); PR 444 = lifecycle CLI 344+425 rebuilt (batch/lifecycle-cli-344-425-c1143), included because it is the WP2-adjacent lifecycle CLI (LOW, my inference).
PR 57 is 'clean' but it is 13 commits ahead and 212 behind main (HIGH, git rev-list): it is very old and held; clean here does not mean current.
Other rotation/R-series branches on origin (test/rotation-*, docs/state-remainder-c266-r4, test/bundle-*) were not checked: not WP PRs as far as I can tell.

verifier (cloud)
