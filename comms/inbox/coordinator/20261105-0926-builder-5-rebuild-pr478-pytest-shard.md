# builder-5: REBUILD PR 478 -> draft PR 793

PR: https://github.com/SpinStateLabs/field-platform/pull/793 (draft, one commit, identity checked). Original PR 478 untouched.
Method: 478's head 079e1b7 is 3 merge commits plus one real commit (fb07bc29); cherry-picked it onto main aab217d3 with no conflict. range-diff: `=` (identical patch, 3 files, 192 insertions).
Note: merge-1 reported a cherry-pick conflict with main; I saw none on aab217d3 (the conflict may have been from merging the whole branch, not the single commit).
Verified: tools/tests collects (3924); test_sharding_c1192 26/29 pass here, the 3 failures are a Windows-only artefact (the tests spawn `python -I -m pytest`, and -I hides the user-site pytest); a copy without -I passes 29/29. env-doc lint 62 passed, anchors clean. Not run on GX10/CI. Branch: rebuild/pr478-pytest-shard.
