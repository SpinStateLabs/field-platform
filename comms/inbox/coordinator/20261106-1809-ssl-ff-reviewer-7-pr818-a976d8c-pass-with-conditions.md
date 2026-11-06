# Review PR 818 @a976d8cf (G22 internal secret; delta over my PASS WITH CONDITIONS on 35f06096) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `a976d8cf8ff4748e60742b0912a48384291670f5`. The head is the previously reviewed commit 35f06096 plus one merge of main (e125a878). My earlier conditions carry unchanged: (1) the three decision items for Don or the architect before ENFORCE use (ENFORCE with the hash unset now 404s both internal routes; the `FIELD_READ_KEY` names come from PR 369/828; no minimum secret length); (2) CI and GX10 on the landed head. Nothing in the merge adds a new condition.

## Checks (HIGH, run by me)
- Identity: 2 commits (the original and the merge), author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. Base == current main e125a878 (merge-base e125a878).
- Merge fidelity: the PR's changed (+/-) lines, compared net against the previous head's, are identical except one blank line in the runbook hunk (two diff lines). No conflict markers in the runbook (grep count 0). The only conflicting file was docs/runbooks/v1.2-deploy-rollback.md: the Stage 2 entry-gate items (a)-(f) sit after item 3 of the Stage 2 checklist, the "## Internal secret (G22)" section sits before "## Stage controller (P36, G24)", which is main's landed 816/G24 text and is intact.
- Source and tests unchanged by the merge: operator_health.py, phase_g_check.py and the four test files carry the same changed lines as at 35f06096, so my 21-mutant result on that commit (21 of 21 killed) stands; I did not re-run the mutants.
- Tests on the exact head (Windows): field-core whole suite 1706 passed, 2 skipped (main has grown the suite since my first run); the tools files that touch this code (test_phase_g_check, test_stage_controller, test_deploy_docs, test_environment_doc) 320 passed; `environment_anchors --check` 0 wrong rows.

## Note on PR 827
827 (the counter-reset test fix, stacked on this branch) now shows head f129b1e9 on base `claude/determined-noether-pbg5bo-g22-secret`; it will need its own re-review against this merged head; I have not reviewed that head.

## Not verified
CI/GX10 on this head; the service suites that install `install_routes`; Linux.
