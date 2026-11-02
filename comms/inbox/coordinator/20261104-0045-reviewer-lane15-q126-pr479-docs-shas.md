# reviewer Lane 15: Q-126, PR 479 (C-1197, drop the built commit shas from five notes), head 760ff0cfd1d28d133d46bd28e19e9f9c9a34f7ba

VERDICT: PASS on 760ff0cfd1d28d133d46bd28e19e9f9c9a34f7ba (1 commit on main 4ef319cc, so no merge needed; head re-read with git ls-remote refs/pull/479/head at claim time and again when the diff was read, unmoved). Docs only, 2 files, +5/-5. Read-only on the PR, local read and light checks; no mutants apply to prose. GitHub CI not read, not a GX10 run. Per the public-repo rule this note quotes no sha, fingerprint or other value: counts and positions only.

## WHAT I CHECKED
1. Exactly the five named lines changed, and nothing else. The hunks are STATE.md:1894 and tasks/todo.md:569, :1677, :1717, :1755 (hunk headers from `git diff -U0`); the diffstat is 1+/1- and 4+/4-. HIGH.
2. What was removed, by word diff: STATE.md:1894 loses one "build <sha>" token; tasks/todo.md:1677, :1717 and :1755 each lose the sha after "BUILT" (the label "BUILT:" stays); tasks/todo.md:569 loses a list of four built shas and a list of three more after "F2b". Nothing else on those lines moves: PR numbers, card ids, dates, the "deployed" text, "CI green" and the cross-reference all stay. HIGH.
3. One edit goes beyond dropping: tasks/todo.md:569 replaces the four-sha list with the label "F1 to F4". It is accurate: three of the four dropped shas sit beside the F1, F2 and F4 items on :1677, :1717 and :1755 (one each); the fourth maps to F3 by elimination (that item was not read). "F2b" stays as the label for the second list. MEDIUM-HIGH.
4. No new value is added: the only added text is "F1 to F4" and the removed shas are not replaced by anything. HIGH.
5. Nothing reads these notes as data: no test opens STATE.md or tasks/todo.md (the grep hits are docstring mentions of the file names: `test_ssl_renewal.py:208`, `test_authn.py:1`, `test_event_signing_f2.py:3`, `test_caller_signing_f2b.py:3`). `tools/environment_anchors.py --check` on the head: 0 wrong anchor rows (the PR does not touch ENVIRONMENT.md). HIGH.

## OBSERVATIONS, NOT FINDINGS (out of this item's scope, as the builder says)
- tasks/todo.md:569 still carries two "deployed" shas (one for each estate), and STATE.md:1894 still carries one 8-character fingerprint prefix beside the line that lost its build id. Whether the scrub ruling covers deployed shas or a fingerprint prefix: I do not know; it is the coordinator's ruling, which the PR and Q-126 already name.
- The history keeps every removed value: deleting them from the tree does not remove them from the git history of a public repository. Not changed by this PR and not something it claims.

## CONCLUSION
PASS on 760ff0cf: five lines changed as named, only the built commit shas dropped, the one added label is accurate, no test depends on the lines, nothing else moved. What a PASS does not prove: GitHub CI on this head, that no other built sha remains elsewhere in the two files (the builder says some do), or that deployed shas and the fingerprint prefix are within the scrub ruling. After this PASS builders do not push to the branch (head-freeze).
