# C-158 addendum: PR 89 docs/crosswalk-readme-c139-r2 @4cf73d57a60c072f666da923631a8044457f7443 (rebase of PR 88)

VERDICT: PASS on 4cf73d5; my C-158 verdict on PR 88 (79fccf8) carries.

REASONING
1. Base is current main 70fa59f (merge-base equals main); one commit above it; diff vs main: 1 file (`services/compliance-crosswalk/README.md`), +3/-3; author `Don Hagell <13129187+dhagell@users.noreply.github.com>`. [HIGH]
2. `git range-diff 79fccf8~1..79fccf8 4cf73d5~1..4cf73d5`: `1: 79fccf8 = 1: 4cf73d5`. (The `git patch-id` pipeline printed nothing in my Windows shell this time; the range-diff `=` is the evidence.) [HIGH]
3. mapping.py CONTROLS on 70fa59f recomputed on the GX10: FC-E-04, FC-E-05, FC-E-06 each `{osfi-e23: pending-text, eu-ai-act: pending-text, iso-42001: pending-purchase, nist-ai-rmf: pending-text}`; 13 controls, 16 of 52 entries cited: the README's new sentence ("None of FC-E-04, FC-E-05 and FC-E-06 cites anything yet; every entry is pending ...") and "16/52" match. The guard-test row and the claim-word scan are unchanged from the C-158 report (no complian*, certif*, guarantee, satisf*, assur*, conform* in the added lines). [HIGH]

CONCLUSION
PASS at 4cf73d5. F-R16-1 and F-R16-2 fixed at 4cf73d5 (merge pending).
