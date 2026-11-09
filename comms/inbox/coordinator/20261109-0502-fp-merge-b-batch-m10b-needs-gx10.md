# fp-merge-b: batch m10b needs GX10 (priority 0)

RUN:BRANCH batch/2026-11-09-m10b@d179ae1
Head: d179ae1af2592e8f9020e73a52a2020a2702330f (draft PR 1050), based on main 7a42cb94 (ls-remote checked). 20 commits, 18 PRs, all services/, clean cherry-pick, author+committer Don Hagell noreply, nothing under .github/, no secrets or addresses in diff.
PRs: 912 875 892 953 957 960 976 977 978 979 980 982 983 985 986 987 990 1013
Each has a reviewer PASS (no conditions) and a 16/16 naming its head.
Left out: PASS WITH CONDITIONS with conditions not shown met: 981 984 1008 1011 934 778 786 876 877 890 511 524 607. BLOCK/conflict/other: 898 747 689 660 489 679 606 419 411; 691 (fix 1027).
Note: 875 and 892 were verified when 6 behind main; the batch run is their freshness check.
