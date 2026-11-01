# rebase builder: PR 347 carried as batch/2026-11-01-rb347 on main 9468b184

- PR 347 head 8dae2b33177c34455220d9e152826c2ec04a47fa (Lane 7 Q-57 PASS), read with git ls-remote and gh at 16:0x: head unchanged, draft, mergeable, CI 7/7 pass (compose-smoke, compose-upgrade-smoke, fly-image-smoke, tests 3.11 to 3.14).
- New branch: batch/2026-11-01-rb347, head 5f0f17e2844708dfd477bc216e1bbfbf10506ec5, on main 9468b184383ebe66e94107b76ed7fb2d89bd797a. 9 commits, cherry-picked CLEAN, no conflict, nothing resolved by hand.
- Identity: all 9 commits Don Hagell <13129187+dhagell@users.noreply.github.com> as author and committer (checked per commit).
- range-diff 5808a5cd..refs/pr/347 vs 9468b184..batch/2026-11-01-rb347: all 9 commits `=` (patch-identical). Net change: 3 files, +340 -14, same stat as the PR (integration/demo/fixtures/kr-edge/check_edge_block.py, tools/tests/http_env_proxy_allowlist.txt, tools/tests/test_kr_edge_block_r2.py). Main has not touched those three files since the PR's base 5808a5cd.
- Tests (local, py -3): tools/tests/test_kr_edge_block_r2.py 52 passed, 8 failed: all 8 are the per-service answer test and fail on ModuleNotFoundError fastapi (not installed locally), i.e. not run, not a code failure. GX10 needed.
- Old verdict (Q-57 PASS) and the earlier CI do not carry over by themselves: a delta no-semantic-change check (Lane 7 or 17) and a GX10 full run on 5f0f17e2844708dfd477bc216e1bbfbf10506ec5 (verifier A or B; the coordinator names which) are needed. PR 347 branch untouched.
