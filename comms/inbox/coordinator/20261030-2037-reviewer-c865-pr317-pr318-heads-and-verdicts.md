VERDICT: PASS on 9cc52212607105e7e0d0ac5c81b902810f197693 (PR 317); PASS WITH CONDITIONS on 4383a07f9a14d0ba66aeec2560acb4fe8d70f6bc (PR 318, superseded by PR 381)  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-865. The card says neither PR has a verdict on its current head. That premise is wrong for both, and the first line of this report is the correction: PR 317's current head 9cc5221 has C-711 (PASS, comms/inbox/coordinator/20261105-0000-design-c711-pr317-rate-rounding.md, the file name says "design" but its first line is a verdict on 9cc5221); PR 318's current head 4383a07 has C-710 (PASS WITH CONDITIONS on 4383a07). I fetched both heads this session; neither has a commit after those verdicts. So "what changed since the last verdict": nothing for either. Each verdict applies to its own SHA.

OBJECTIONS FIRST
1. PR 317: nothing found open that blocks. My own probe agrees with C-711: conformance_percent equals an independent exact integer half-up reference on 82,000 pairs (every pair with total up to 399, plus 1,800 random pairs with totals up to 10^6, 10^9, 10^12, 10^18, 10^30, 10^50): 0 differences. Ties print as the README says (1/16 gives 6.3, 3/16 gives 18.8, 1/8 gives 12.5, 5/8 gives 62.5). Bad input is refused (bool, float, string, None raise TypeError; negative or allows > total raise ValueError); zero verdicts gives None. Confidence HIGH (observed).
2. PR 317: two precision mutants survive (context precision 60 lowered to 28 and to 12): the tests use ratios only up to 300 (C-711 said the same). They concern counts a ledger cannot hold (a total near 10^12 or more for precision 12). LOW, as C-711 says.
3. PR 318: C-710's conditions F-C710-1 (the lint's binder does not visit annotated assignments or walrus targets, and does not resolve a from-import-as base name), F-C710-2 (header limits omit setattr and decorator use), F-C710-3 (class-as-value rule flags print/log/repr arguments and can flag a same-named unrelated class), F-C710-4 (docstring caller list is a grep, not exhaustive) are unchanged because the head is unchanged. I did not re-probe them. Confidence MEDIUM (second-hand).
4. PR 318 is superseded: the builder's note says PR 381 (head b00bd96) carries 318's five commits (equivalent of 4383a07 is a3ca065) plus PR 330's six plus one, and that PRs 318 and 330 are to be closed. A reviewer verdict on 318 therefore has little merge value; the reviewer who reads 381 inherits C-710's conditions. Confidence HIGH on the note.

ASSUMPTIONS
A1 "Newest head" = what pull/N/head serves now. A2 The earlier verdicts' scope is what they state.

REASONING / CHECKS
- Heads: PR 317 9cc5221 (3 commits: c0f07da, 6f0afdd, 9cc5221; 177 attestation-reporter tests pass); PR 318 4383a07 (tools/tests/test_http_env_proxy_lint_c57.py 99 passed; lifecycle-manager 229 passed).
- PR 317 mutants on engine.py (each restored, nothing committed): HALF_EVEN KILLED; HALF_DOWN KILLED; bool check removed KILLED; `allows > total` check removed KILLED; `allows < 0` check removed KILLED; the zero-total return removed KILLED; quantum 0.01 KILLED; the "rounded half up" note removed KILLED; call site reverted to `round(...)` KILLED; precision 28 SURVIVED; precision 12 SURVIVED. Nine of eleven.
- Commits: all author and committer Don Hagell no-reply on both PRs. No address, flag value, credential or deploy status in PR 317's diff (3 files, +201 -1).
- What a reviewer must run: for 317, `services/attestation-reporter` suite (177 tests, ~20 s) on any machine; the GX10 16-suite set is the builder's. For 318 do nothing; review 381 instead (lint test file 99 tests, lifecycle-manager 255 on 381, the tools suite).

CONDITIONS
C1 (non-blocking, 317) Add a rate test above ratio 300 or accept the two precision survivors as stated. C2 (non-blocking, 318) Carry F-C710-1 to 4 to the review of PR 381. C3 (coordinator) Correct the card premise: both heads already have verdicts; PR 381 needs the next review.

NOT VERIFIED
GX10 set, CI, PR 318's lint conditions at file:line (second-hand), PR 381's code.

CONCLUSION
PR 317 is correct and well pinned (9 of 11 mutants die; 82,000 pairs agree with an exact reference). PR 318 has not changed since its verdict and is replaced by PR 381. UNVERIFIED.
