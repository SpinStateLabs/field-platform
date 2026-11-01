# rebase builder: PR 402 carried onto main 7de2a064; PR 326 skipped

- Old PR 402 head: 9f5a447ee47c4260661f23d61845beaca7a7c137 (Lane 15 Q-30 PASS)
- New branch: rebase/402-20261101, head 5086c1245eca38488a7b0ec78a088dc2d516e898, on main 7de2a064be460689b85d2957fde8fdd3478687fb. Identity checked: Don Hagell <13129187+dhagell@users.noreply.github.com> (author and committer).
- Two commits cherry-picked (c0e6c02c, 9f5a447e); no merge commit in the PR.

## Conflict (tools/tests/test_renew_token_pins_c212.py, commit c0e6c02c)
Main holds PR 412's version of this file. As you directed, the final content is PR 402's: the file is byte-identical to the PR 402 head (`git diff refs/pr/402 HEAD -- tools/tests/test_renew_token_pins_c212.py` is empty).
FLAG for you: taking 402's file whole DROPS five assertions that main's 412 version has and 402 does not: is_guarded refuses `/x/delegation/tokens` (path that only contains an allowlisted one), `/delegation/tokens/extra/path/more`, accepts `/delegation/tokens/<id>/revoke?x=1`, refuses `/delegation/tokensX?x=/delegation/tokens`, and the 412 test name for the sign pin is replaced by 402's. Whether renew_token.py still satisfies them is unproven here (the test file no longer asserts them). If you want them kept, say so and I add them as one extra commit on this branch (a change to what the PR does, so your call). 402's own `/delegation/tokens/abc/def/revoke` and `tokens//revoke` cases are kept.

## Evidence
- range-diff acaf5f24..refs/pr/402 vs 7de2a064..HEAD: see the branch; the file is identical to the PR head, other paths are untouched by the PR.
- Tests: tools/tests/test_renew_token_pins_c212.py: 53 passed (py -3, local).

## Needed before merge
Old verdict and GX10 run do NOT carry over: reviewer delta verdict (Lane 7 or 17) and a GX10 run on 5086c1245eca38488a7b0ec78a088dc2d516e898 (verifier A or B; tests only, light run is enough per PROTOCOL if the change is test-only). PR 402 branch not touched.

## PR 326 skipped
Verdict conflict on head da33a9a (FAIL C-791 vs PASS WITH CONDITIONS C-729/C-770, none of the conditions closed) and groomer/merge assistant mark it superseded by PR 372 (head 1b8f9e3). Not rebased.
