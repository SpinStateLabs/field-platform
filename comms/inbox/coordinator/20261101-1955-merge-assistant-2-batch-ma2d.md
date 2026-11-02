# Merge assistant 2: batch ma2d (PR 336) built on main c4ac8c14, GX10 run requested (NOT yet verified)

Branch batch/2026-11-01-ma2d, head ca295ad037cd08c9b9b5403156b9db7b01335aab, on origin/main c4ac8c14 (MERGE 9). 13 commits cherry-picked from PR 336 @853a5b1, no conflicts; author and committer Don Hagell 13129187+dhagell noreply on all 13 (checked). Touches docs/ENVIRONMENT.md and tools/tests/http_env_proxy_allowlist.txt: a rebuild is needed if any other ENVIRONMENT.md batch lands first.

PR 336 evidence (head re-read with ls-remote just before the push: 853a5b1, unchanged; CI 7/7 read at claim time):
- Q-08 PASS (Lane 15) 20261101-0320-reviewer-q08-pr336-kill-switch-self-route-guard.md
- C-1074 PASS WITH CONDITIONS, C1 non-blocking (record Don's F-C525-2 ruling in the repo) 20261101-0330-reviewer-c1074.md
- builder Lane 12 16/16 on 853a5b1e (older main) 20261031-1900-builder-lane12-c1061-conditions.md, 20261031-2000-builder-lane12-c1064-conditions-and-gx10.md (does not count for this head)

GX10 verifier B asked (queued). Not checked: the C1 condition's status beyond the reviewer's "non-blocking"; whether Don's F-C525-2 ruling is now in the repo; cloud merge-into-main; later reviewer findings after those files.
