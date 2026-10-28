# C-118 reviewer report: PR 76 test/revoke-refusal-record @2bbfb9276156b448c9e06dd154146359e3d46553 (C-116: F-C111-1, F-C111-2)

VERDICT: PASS on 2bbfb92. F-C111-1 fixed. F-C111-2: acceptable to leave unguarded for now (condition below); it does not need a guard before the verifier goes live.

OBJECTIONS FIRST
1. A comment that states a limit is not a control; the 403/404 distinction on revoke stays decorative while two GETs answer the same question.
2. The new test compares four fields of the two refusal rows but not `agent_id`, which the code sets differently on the two paths.
3. A ledger-polling test can flake.

ASSUMPTIONS
1. Head 2bbfb9276156b448c9e06dd154146359e3d46553 on main 0b44dee (GX10 `~/ff-work/wt-fieldrev-76`). [HIGH]
2. The verifier's reach (revoke only canary tokens) is enforced by `check_list_bound_reach` after the token lookup (api.py:353-370), as reviewed in C-114. [HIGH]

REASONING
1. delegation-authority suite on GX10: 162 passed (161 on batch B plus the one new test). [HIGH]
2. Mutants on api.py revoke 403 branch, delegation suite: V2 plain `HTTPException(403)` KILLED; V3 `action="mint"` KILLED; V4 `claimed` dropped KILLED; new V6 wrong `path="/tokens"` KILLED; new V7 status 401 KILLED (2 tests). 0 survivors of 5. [HIGH]
3. Flake check: the new test run 8 times in isolation, 8 passed (0.26-0.28 s each). The append is a best-effort worker-thread write, so the 3 s poll is the right shape. [MEDIUM: 8 runs under no load; a loaded CI runner could be slower than 3 s]
4. No behaviour change in api.py: diff is the comment block only (+6/-3 lines in a comment). [HIGH]
5. F-C111-2 judgement: not guarding `GET /tokens` and `GET /tokens/{id}` is acceptable. Reasons: (a) learning a token id gives the verifier no action it lacks: revoke still requires manifest reach; (b) `GET /tokens` is a legitimate read for the console, replay and attestation (the coordinator's list), and P35 F1's comment already states the verifier can list tokens; (c) the risk is disclosure of ids, not authority. Condition: the runbook and any "verifier cannot enumerate" claim must not assert otherwise, and the comment's LIMIT must stay. A read guard is needed only if token ids themselves become secret (they are not today: a token id appears in ledger events, which are also open under the perimeter secret). [MEDIUM]
6. Residual: the two refusal rows are not identical: the known-token path passes `agent_id=token.agent_id` (api.py:368) and the unknown-token path passes none (api.py:347-350), so a ledger reader can tell them apart; the test checks action, status, claimed_id, reason only. Same class as F-C111-2 (ledger reads are open), so LOW (F-C118-1). [HIGH on the code difference]

CONCLUSION
PASS at 2bbfb92. F-C111-1 fixed at 2bbfb92 (5/5 mutants killed). F-C111-2 accepted as a documented limit (INFO). New LOW F-C118-1: refusal rows differ by agent_id.
