# fp-merge-b: batch m11b needs GX10 (priority 0); supersedes m10b

RUN:BRANCH batch/2026-11-09-m11b@069acc1
Head: 069acc14102310aa49763d809bf9ed9b9d298507 (https://github.com/SpinStateLabs/field-platform/pull/1051), on main 117ee0f4 (ls-remote checked). Rebuild of m10b: all 18 PRs cherry-picked clean, none left out.
PRs: 912 875 892 953 957 960 976 977 978 979 980 982 983 985 986 987 990 1013
Author+committer Don Hagell noreply on all 20 commits; nothing under .github/.
Drop the m10b run request (head d179ae1); vehicle PR 1050 to close.
