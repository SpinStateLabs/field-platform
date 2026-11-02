gx10 verifier B: batch/2026-11-02-cb26 (PR 447, C-1158: a 422 from each of nine services keeps the field name and never the value), FULL 16-suite run, GREEN 16 of 16, 0 failed.

- Head before run and after run (read from GitHub): b39287c14410144dfcb1e7e35f383dc37671f4bb. Not stale.
- Contains current origin/main 40aec3724699c63442478df75170930dd1ef58e1 (cb25)? YES (main unchanged at the final check). This meets the blocking condition C1 of Lane 17's PASS WITH CONDITIONS on PR 447 (a GX10 run after the batch is rebuilt on current main).
- Run time: started 11:43:29Z (GX10 clock), done about 11:59Z (about 17 min). Log (GX10): ~/ff-work/cb26b-all.log (worktree wt-cb26b).
- Suites: core+sealed-ledger 2346 passed 4 skipped; tools 3771 passed 4 skipped; field-agent 207; agent-registry 306; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 256; federation-broker 188; force-gateway 448; incident-replay 97; kill-switch 242; lifecycle-manager 269; ops-console 457; spend-governor 291. All 0 failed.
- Counts vs the PR 449 run on 05942b98 and the PR 446 run: delegation-authority 252 to 256 and lifecycle-manager 267 to 269 (from main's cb25 content), tools 3749 to 3771 (PR 447's 22 new tests, plus cb25); no count went down.
