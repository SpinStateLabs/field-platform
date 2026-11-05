# builder-5: REBUILD PR 400 -> draft PR 798

PR: https://github.com/SpinStateLabs/field-platform/pull/798 (draft, 14 commits, identity checked on all). Original PR 400 untouched (235 behind main aab217d3).
Method: cherry-picked all 14 commits, no conflict. range-diff: 10 identical; 4 `!` are author-metadata only. The original authored those four as `dhagell@users.noreply.github.com` (not the required 13129187+ form), so they are re-authored; plain `git cherry-pick` KEEPS the original author even with GIT_AUTHOR_* set (and `--reset-author` is not a cherry-pick option), so I used `cherry-pick -n` + `commit -C <sha> --reset-author`. Worth knowing for the other rebuilds: check ALL authors before pushing.
Verified: test_compose_* (8 files) + env lints: 1187 passed, 2 failed, both failing identically on unmodified main here (POSIX path assumptions: symlink-to-/etc test, fake-docker script test); anchors clean. Not run on Linux/GX10.
Branch: rebuild/pr400-compose-stack.
