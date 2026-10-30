# Builder Lane 1: C-44 PR 297 ready (docs only, light run applies)

- PR 297 (draft), branch `docs/lessons-c44`, exact head `3bb2510d496e778c1d56d16b7fc5aa48ab8e5195`, one commit on main 3ee2e5d. `tasks/lessons.md` +16 lines, three entries (squash-merged branches, author and committer identity, venv `sys._base_executable`); each sourced to the card and its reports.
- Tests: none touch the file (grep of tools, packages, services: no hit); no suite run by me. NOT run: GX10. CI not read yet. Ask: reviewer card (light, docs only).
- Open for you: C-451 waits for PR 288 to merge (built and committed on its head, ops-console suite 246 passed). PR 291 is 7 of 7 green (addendum in the C-23 note); its follow-ups (C-450 S1 build-constraint, S2 whole-workflow scan, S3 comment in ci-constraints.txt) wait for your cards. PR 295 (C-57) has a note. Next for me: C-101 (fly-image-smoke regex), then C-138.
