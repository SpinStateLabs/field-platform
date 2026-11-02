# Merge assistant 2: batch ma2e (PR 336) rebuilt on main b5e98d8e, GX10 run requested (NOT yet verified)

Main moved c4ac8c14 -> b5e98d8e (cb17), so ma2d (ca295ad0, 16/16 on c4ac8c14) is superseded; do not fast-forward it.

Branch batch/2026-11-01-ma2e, head 7413176216d2b40d87bea1e0406bb65ab925e666, on origin/main b5e98d8e. 13 commits from PR 336 @853a5b1 (head re-read with ls-remote at push time, unchanged; PR still OPEN), cherry-picked clean; author and committer Don Hagell 13129187+dhagell noreply on all 13 (checked). Touches docs/ENVIRONMENT.md and tools/tests/http_env_proxy_allowlist.txt.

Evidence on the PR: Q-08 PASS 20261101-0320-reviewer-q08-pr336-kill-switch-self-route-guard.md; C-1074 PWC, C1 non-blocking 20261101-0330-reviewer-c1074.md; CI 7/7 on 853a5b1 (read last cycle). The ma2d run (20261102-0216-gx10-verifier-B-batch-ma2d.md) was on the old main and does not count here.

GX10 verifier A asked. Not checked: CI re-read this cycle; the open C1 condition beyond "non-blocking"; cloud merge-into-main; whether rb-c1102 (Lane R, verifier B) overlaps ENVIRONMENT.md with this batch.
