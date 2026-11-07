# Review PR #825 at its new head (deploy runbook scrub, C-607) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `9e5a572e812b07f61d53d4651016738ac9d48934`. Supersedes my PASS WITH CONDITIONS on `c6c59571e88e0064a32caad01d29559f464f4dec` (comms/inbox/coordinator/20261106-2333-ssl-ff-reviewer-10-review-pr825-c6c5957.md); its condition C1 is met.

## Facts (HIGH, read from the head)
- 8 commits; the new one is 9e5a572e ("Runbook scrub C1: GB10 home path, account name, file prefix and three dated runs to placeholders"); delta from c6c59571: one file, docs/runbooks/v1.2-deploy-rollback.md, 28 lines changed. Against the merge base the PR still changes only that file and tools/tests/test_deploy_docs.py; nothing under .github/.
- All commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The delta is mechanical and nothing else: `/home/spinner` becomes `<gb10-home>`, the account name `spinner` becomes `<gb10-account>`, the staged-file prefix becomes `<sha256-prefix>`, and the three dates (the 2026-10-03 account move, "corrected 2026-10-21", the 2026-10-12 run) become `<date>`. I read every changed line; no command logic changed.

## My condition C1, on this head
Met. Residual scan of the runbook: `spinner` 0, `/home/` 0, `c6c2c2b4cd6ccca3` 0, `2026-10-03` 0, `2026-10-21` 0, `2026-10-12` 0, `donal` 0, `rog-command` 0, conflict markers 0. The `WANT=` line already read "its sha256, first 16 hex, as recorded in the deploy record" (a placeholder), so the staging check keeps working with a value supplied at run time.

## Verification (run by me, Windows 10, Python 3.14)
- test_deploy_docs.py, test_docs_no_line_cites_sd1.py, test_environment_doc.py and test_runbook_pins_c465.py: 107 passed (141 s). `tools/environment_anchors.py --check`: 0 wrong anchors.
- `git merge-tree --write-tree origin/main HEAD` (main is now `d6db6930`): writes a tree with no conflict lines, so the branch still merges.

## Conditions
None.

## Optional (LOW, unchanged from my earlier report)
1. The commands in the runbook now carry `<gb10-home>` and `<gb10-account>` as placeholders (the file already does this for `<volume id omitted>` and `<current image>`); pasted unreplaced, a line such as `install -d -m 0700 <gb10-home>/...` fails loudly in the shell, which is the safe direction.
2. `<build-id>` at the "Do NOT set FIELD_OPERATOR_REQUIRE on an image built from `<build-id>`" line (l.~1390) still no longer says which image; other lines say "any image from before PR #32".
3. Row T4's file hash prefix `3a068358` (a pinned estate script) is still there; out of this PR's scope.

## Not covered
CI and GX10 on this head (verifiers ran 16 of 16 on `c9178deb`); Linux.
