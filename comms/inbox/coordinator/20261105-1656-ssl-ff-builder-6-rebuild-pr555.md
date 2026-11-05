# builder-6: rebuild of PR 555
Old PR 555 (head 55cb95c1) -> new PR 812 https://github.com/SpinStateLabs/field-platform/pull/812, head abf5d4417d60fe0d72a560d5171d31c32eb4c46d, base main 869cf2ed.
Clean cherry-pick of da2054d6 (merge commit dropped). Author+committer Don Hagell noreply. No .github changes.
Ran (PYTHONUTF8=1): spend-governor suite 332 passed, 4 skipped, 1 failed: test_governor_store_concurrency (deadlock, 8 threads after 60 s). Same failure reproduced on clean main 869cf2ed in my Windows env (baseline, HIGH); new test file passes.
Review requested.
