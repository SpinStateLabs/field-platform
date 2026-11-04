# Lane O reviewer: clarification to my PR 422 report; verdict unchanged

The PR 422 report says the merge result is "printed below" my command output. Stated plainly: `git merge-tree --write-tree origin/main pr422` (origin/main 97dcfec1) printed a tree id, 8735bda4ae3f7a1682e7d73fc90a639eb946519c, with no CONFLICT line: the head merges CLEAN onto current main (run, HIGH), although it is 212 commits behind. The rebuild condition C1 stands for the batch-rebuild and CI/GX10 reasons, not for a textual conflict.
