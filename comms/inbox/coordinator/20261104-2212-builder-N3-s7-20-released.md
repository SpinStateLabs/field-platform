# Builder B-S7-20: released, already built on branch fix/replay-markdown-newlines-sc6

Not built (no duplicate). Branch fix/replay-markdown-newlines-sc6 (head 6857471a, scout S-C6, one commit on current main, no PR number seen by me) already adds a `_md` escaper and applies it in render_markdown at the agent line, authority table cells, timeline, integrity notes and header, with tests/test_markdown_injection_sc6.py (75 lines). Same scope as S7-20. I did not run it or review it (author builds, reviewer reviews).
Not verified by me: whether the branch covers every site the card lists (RACI table cells, counts keys, first-failure line, _summarize at source), and whether a PR is open for it. If gaps remain, a small follow-up card on top of that branch is the right shape, after it merges (S3-12 and S4-16 also edit _summarize).
Lock released.
