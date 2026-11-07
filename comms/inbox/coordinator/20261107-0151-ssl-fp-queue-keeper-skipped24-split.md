queue-keeper: check of the 24 PRs the merge writer skipped, against origin/main ff06b3398 (d6db6930 is its ancestor), 2026-11-07. Method: git merge-tree --write-tree origin/main <pr head>; result tree == main tree means already applied (HIGH); exit 1 means conflict (HIGH).
ALREADY APPLIED (8): 478, 552, 555, 628, 666, 803, 823, 824. Superseded; close needs Don's per-set OK. NOT closed by the keeper.
CONFLICT (15): 352, 399, 443, 453, 465, 479, 481, 660, 689, 747, 772, 779, 784, 789, 792. Builder rebase cards B-M12RB-PR<n>-<head7> pushed (per-head dedupe checked, none existed).
CLEAN MERGE WITH CHANGES (1): 362 (ef85243): merges cleanly and still carries changes; not applied and not conflicting, so no card made. Ask the merge writer why it was skipped at cherry-pick.
Heads checked: 478 079e1b7, 552 86082cc, 555 55cb95c, 628 93b9c32, 666 82b2411, 803 5cedddb, 823 81811f2, 824 d70cab7.
