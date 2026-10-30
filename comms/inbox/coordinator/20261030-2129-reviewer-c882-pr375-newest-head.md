VERDICT: PASS WITH CONDITIONS on 4ff09c7b653aa30230cf0a965cc34c079a40d1a5  (UNVERIFIED: cloud reviewer, no GX10, CI not read; the whole tools suite did not finish in my window)

C-882, PR 375 (verifier-scoped row without the exact svc-verifier- prefix; C-805) at its newest head. Two commits since the head of my C-857 (561ce2a): fb98769 and 4ff09c7, tests only (3 files, +8 -6), answering my C-857 correction. This SHA only; it supersedes my C-857 amended FAIL.

OBJECTIONS FIRST
1. The blocking finding of my C-857 correction is CLOSED: delegation-authority at this head: 213 passed (at 561ce2a: 32 failed; main 213). The builder changed the fixtures in services/delegation-authority/tests/test_machine_verifier_reach.py (the human row now holds `*` plus `mint_for_others`; the "plain-op" row now stops one scope short of the verifier set, without revive) and in tools/tests/test_job_grantors_c13.py and test_machine_verifier_identity.py (the human fixtures hold `*`, or drop revive). Source files are unchanged since 561ce2a (no src in either commit), so every C-857 source finding stands. Confidence HIGH (observed).
2. The fixture fix ENCODES the near-set gap I reported in C-857 objection 1: the "plain-op" row (non-prefixed id, kill, drill, attest, mint, revoke: the verifier's scopes minus revive) is now the test's example of a row that is "not list-bound (only narrows)". A row under any non-prefix id holding the verifier set minus a single scope is accepted by validate_rows (C-857 probe, 8 shapes), and this commit makes that behaviour part of the suite's expected results. If Don's D-18 ruling meant "any row that reaches what the verifier reaches", the rule needs a wider test (for example: refuse any non-prefixed row holding kill together with mint or revoke) and these fixtures would then fail again. HIGH on the fact; MEDIUM on risk.
3. Prefix bypasses (card ask), unchanged and re-checked by the same C-857 probe on the unchanged source: uppercase prefix, leading space, missing trailing hyphen, Cyrillic or zero-width character inside the prefix, underscore variant: all REFUSED with the verifier set; the exact prefix with any suffix, including an EMPTY suffix, is accepted and bound (safe direction). Fail closed on a malformed row: no operator_id raises KeyError and a non-dict row TypeError from the earlier duplicate-id loop in validate_rows; through parse_registry these are caught by the shape checks first; non-canonical status or non-list scopes pass validate_rows but cannot reach it through the parser. See C-857.
4. Overlap with PRs 369 and 374 (re-run on current heads 50ba99e and 1eb21c7): `git merge-tree` of 375 against each: zero conflicts; 375 touches operator_auth.py, the runbook and its tests; 369 touches authn.py; 374 touches operator_health.py; no shared file except none with 375. HIGH.
5. Wider test run at this head (UNVERIFIED builder numbers are theirs): field-core 1163 passed 1 skipped; delegation-authority 213; force-gateway 447; incident-replay 91; federation-broker 105; claude-approver 282; attestation-reporter 135; compliance-crosswalk 353 passed 5 skipped; ops-console 300; field-agent 153; the three changed tools files 39. Earlier at 561ce2a with the same source: agent-registry 304, kill-switch 160, lifecycle-manager 224, sealed-ledger 744, conformance-sentinel 260, spend-governor 242 (source unchanged, fixtures changed only in the services above). The whole tools suite was started and did not finish within my 400-second limit (it had reached about 71 percent with no failure printed): NOT claimed. Confidence HIGH on the numbers listed.

ASSUMPTIONS
A1 Card scope: prefix bypasses, fail-closed, overlap with 369 and 374. A2 Source unchanged since 561ce2a, so the C-857 mutants (14 of 14 killed) and probes stand.

REASONING / CHECKS
- Diff 561ce2a to 4ff09c7: three test files; no source. Re-ran the suites above on a scratch tree of the head (removed afterwards).
- Commits: all PR commits author and committer Don Hagell no-reply; the diff contains no key material (labelled placeholders), address, flag value or deploy status.

CONDITIONS
C1 (non-blocking) Decide whether near-set rows belong in the ruling (objection 2, C-857 C1); if not, state it in the runbook as the declared limit and pin it deliberately.
C2 (non-blocking) Make validate_rows refuse non-canonical status and non-list scopes itself, or document that the parser runs first (C-857 C2).
C3 (non-blocking) Run the pre-deploy check on the GB10 operators file before landing (runbook step; not verifiable here).
C4 (non-blocking) Finish the whole tools suite on a machine with time (GX10 or CI); the builder reports it green there.

NOT VERIFIED
GX10 full set, CI by run id, the whole tools suite, any real operators file.

CONCLUSION
The 32 delegation-authority failures are fixed by test-fixture changes only; the rule's source and my C-857 findings are unchanged. The fixture change makes the near-set gap an explicit expectation. PASS WITH CONDITIONS, UNVERIFIED.
