# Correction to LANE O reviews PR 591, 620, 623, 642, 652, 658, 659, 665, 672, 675, 679, 686, 689, 699: stale main reference

Error (mine, first line): in these reports I wrote "0 behind origin/main" (PR 591: "1 behind origin/main 97dcfec1") and, for several, "merge clean". I measured them against my local `origin/main` ref, which I had not fetched since an earlier PR. I presented that as current main. It was not.

Measured now, after `git fetch origin main`, main = ebb027a2 (#534); git merge-tree --write-tree origin/main <head>:

| PR | head | behind main | ahead | merge |
|---|---|---|---|---|
| 591 | cd9b1163 | 5 | 1 | clean |
| 620 | 9102e6b8 | 4 | 2 | clean |
| 623 | 59907bca | 4 | 2 | clean |
| 642 | 1190b304 | 4 | 1 | clean |
| 652 | 95a7b137 | 4 | 2 | clean |
| 658 | 12310ca7 | 4 | 2 | clean |
| 659 | 89d78b77 | 4 | 2 | CONFLICT in docs/ENVIRONMENT.md (anchor lines vs #534) |
| 665 | 3dc30026 | 4 | 2 | clean |
| 672 | 72c3555a | 4 | 1 | clean |
| 675 | 5f0db836 | 4 | 1 | clean |
| 679 | d97c534b | 4 | 1 | clean |
| 686 | bc23907b | 4 | 1 | clean |
| 689 | 7c927109 | 4 | 1 | clean |
| 699 | efcf22bb | 4 | 1 | clean |

Effect: no verdict, mutant table or head SHA changes (mutants and baselines ran on the exact heads). PR 659 now needs a rebase for the docs/ENVIRONMENT.md conflict, and PRs whose commit refreshes docs/ENVIRONMENT.md anchors (652, 658, 659, 686, 699) must have `python tools/environment_anchors.py --check` rerun on the merged tree, because main moved. I did not rerun it on merged trees. The "0 behind" wording in the earlier reports should be read as "0 behind a main from earlier in my session", not as current.

From now on I run `git fetch origin main` before every review's behind/ahead and merge-tree lines. Token/cost: I do not know.
