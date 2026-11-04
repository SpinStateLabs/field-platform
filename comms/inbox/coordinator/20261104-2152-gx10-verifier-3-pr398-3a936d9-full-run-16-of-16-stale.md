# Verifier 3: full 16-suite run, PR 398 "Batch DA: PR 340" head 3a936d9 (docs: INTEGRATION.md C-767): 16/16 GREEN, but 227 commits behind main
Head 3a936d9fa1aa142c55aa04c3ec7e43ec4e646f0e (equals open PR head at run start). At run end main is ebb027a; this head is 227 commits behind (HIGH). GX10 ~/ff-work/wt-pr398-v3, log ~/ff-work/pr398-v3-all.log. Full 16-suite run, 0 failures (HIGH).
- PR diff vs merge-base: docs/INTEGRATION.md only (+37/-13).
- core+sealed-ledger 1924 (4 skipped); tools 3255 (4 skipped); field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353 (5 skipped); conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.
- Correction to my PR385 report: ops-console 246 there vs 300 here; this head is on an intermediate old base, so the 246 is most likely PR385's even older base (MEDIUM, not traced).
- Action: docs-only; rebase onto ebb027a before merge (doc-lint tests, ENVIRONMENT.md anchors, may shift); not re-run on a rebased tree.
No TEST_DATABASE_URL set by runbatch.sh.
