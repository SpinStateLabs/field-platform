# Lane O reviewer: correction to my PR 466 report; verdict unchanged

The PR 466 report says the head is "22 commits behind main cd3b7690". Measured now: main is 97dcfec1 (two commits past cd3b7690: PR 520 DOSSIER and PR 532 start_role_session). The head is 22 commits behind origin/main 97dcfec1 and 20 behind cd3b7690 (git rev-list --count pr466..<sha>). The 22 in the report is the count against 97dcfec1, the cd3b7690 label was stale. Merge-tree onto 97dcfec1 not re-run.
