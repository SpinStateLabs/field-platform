builder Lane 12: after MERGE 24 (main cd3b7690, m1b) my open PRs against it, read with git merge-tree (not CI):
- PR 474 (C-1189, head 4be156f67731558dcfc7d73348d85f26703a52ae): CONFLICT in tools/tests/test_422_handler_installed_c1114.py only. PR 476 installed the helper in kill-switch, so main no longer lists kill-switch in NOT_YET and my edit to the kill-switch reason line has nothing left to change.
- PR 475 (C-1190): clean. PR 481 (C-1198): clean.
- PR 479 (C-1197): still CONFLICT in tasks/todo.md line 569 only (see my note 37489950).

PR 474 resolution for the batch rebuild: DROP my change to test_422_handler_installed_c1114.py entirely and keep the new file tools/tests/test_422_not_yet_pins_c1189.py unchanged. Tested on a scratch branch from main cd3b7690 with only that new file added: test_422_not_yet_pins_c1189.py plus test_422_handler_installed_c1114.py = 43 passed (local, relative PYTHONPATH). Its docstring line about kill-switch is now history, not wrong; I can reword it if wanted.

No push to PR 474 or 479 (frozen heads; 474 has no verdict named in my notes but I did not touch it either). Options: (a) coordinator applies the two resolutions in the batch; (b) tell me and I push the rebase to 474 (it has no PASS I know of, so only CI resets). Still open on 475: Lane 15 conditions F-Q121-1 and F-Q121-2 (my note 69011667). Read, not measured.
