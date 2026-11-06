# B-COND-PR808-7a5378a: no push; the only condition is structural

Head stays 7a5378a8 (OPEN). Reviewer-7's single condition: 808 is stacked on PR 795's branch (rebuild/pr368-field-mcp-tier1, head 5dd1a2ac), so it cannot land before 795. Nothing to change in the code. When 795 merges: rebase 808 on main and check the commit's patch-id is unchanged (a builder card at that point, or tell me).
LOW follow-ups for B-FU-PR808-*: stub-suite test for scripts/mutants.py (red baseline exit 2, ERROR vs KILLED, args passthrough); shlex POSIX mode eats backslashes (use forward slashes in the docstring); whether any test needs the sibling src dirs (mutant M3 survived).
