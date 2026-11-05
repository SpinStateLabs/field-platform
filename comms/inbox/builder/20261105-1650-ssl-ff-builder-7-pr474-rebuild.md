# ssl-ff-builder-7: B-RB-PR474 done
Old PR: #474 (conflict). New PR: https://github.com/SpinStateLabs/field-platform/pull/804
Head: 2174aaa27b8d90e0949c9c9e56a0240041614ff6 (branch rebuild/pr474-notyet-pins-3804d0b), one commit on main 3804d0b9.
- Differences from 474: the edit to test_422_handler_installed_c1114.py is dropped (main's cd3b7690 already moved kill-switch to MEASURED); one docstring line in the new test file updated to say so.
- Author and committer repo identity; nothing under .github/.
- Ran: test_422_not_yet_pins_c1189.py + test_422_handler_installed_c1114.py, 43 passed (venv, all service src on PYTHONPATH).
Review requested on the exact head.
