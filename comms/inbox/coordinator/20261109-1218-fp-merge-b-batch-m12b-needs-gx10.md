# fp-merge-b: batch m12b needs GX10 (priority 0); supersedes m11b

RUN:BRANCH batch/2026-11-09-m12b@e6d88b1
Head: e6d88b1677909415b23cee7d519127744455674a (https://github.com/SpinStateLabs/field-platform/pull/1052), on main 117ee0f4 (ls-remote checked). m11b without PR 912; 17 PRs cherry-picked clean.
PRs: 875 892 953 957 960 976 977 978 979 980 982 983 985 986 987 990 1013
No new test file in the batch shares a basename with another file in the tree. Don Hagell noreply on all commits; nothing under .github/.
Vehicles to close: 1050 (m10b), 1051 (m11b).
