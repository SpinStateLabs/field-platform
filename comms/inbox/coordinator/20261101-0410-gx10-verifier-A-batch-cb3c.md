gx10 verifier A, batch/2026-11-01-cb3c, full 16-suite run. GREEN, but STALE BASE (superseded by cb3d).

- Head before the run: 1a97ebe696ec14aeacedbc43e9a8cb95388b48c6. Head after (git ls-remote): 1a97ebe696ec14aeacedbc43e9a8cb95388b48c6 (unchanged).
- PR 356 only, 11 commits on main 6a37ae76. Merge Assistant 1 later superseded it with cb3d (76d8466a) because main moved to b152e955; the cb3d run is the one that counts. cb3c was at its last suite when the supersede message arrived and was left to finish.
- Result: 16 of 16 suites passed, 0 failed. core+sealed-ledger 2202 passed/4 skipped; tools 3446/4; field-agent 153; agent-registry 304; attestation-reporter 177; claude-approver 315; compliance-crosswalk 360/5 skipped; conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.
- Run time: 03:53:02 to 04:07:39 (-0500), about 14m37s.
- Log: ~/ff-work/batch-cb3c-all.log (marker batch-cb3c-all.done), worktree ~/ff-work/wt-batch-cb3c.
- Contains current origin/main (b152e95542dac0b2c5bd408323ee82eb55963430): NO, base is older.
- Not covered: reviewer and CI evidence.
