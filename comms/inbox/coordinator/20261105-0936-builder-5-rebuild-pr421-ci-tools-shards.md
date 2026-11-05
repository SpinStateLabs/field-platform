# builder-5: REBUILD PR 421 -> draft PR 796

PR: https://github.com/SpinStateLabs/field-platform/pull/796 (draft, 4 commits, identity checked). Original PR 421 untouched (227 commits behind main aab217d3).
Method: cherry-picked its 3 commits, no textual conflict; range-diff: commit 1 `!` (context moved: main added the env-anchors CI step and timeout-minutes), commits 2-3 `=`. One extra commit: test_ci_tools_shards' continue-on-error mutant anchored on `runs-on` then `strategy`, but main now has `timeout-minutes: 45` between them, so the test failed on the rebuilt tree; anchor moved to the timeout line, mutation unchanged. Reviewer should look at that commit.
Verified: test_ci_tools_shards + test_ci_anchors_step_c1191 25 passed; anchors clean. Not run in real CI. The shard split is in the workflow, independent of the --shard option of #478/#793.
Branch: rebuild/pr421-ci-tools-shards.
