# Builder Lane 12: no card left that I can take (idle, polling every 5 minutes)

Done and reported: C-24 (owed items), C-28 (send-path grep), C-46 (PR 351, conditions closed under C-724), C-79 (PR 357), C-397 slices 1-3 (PRs 361, 364, 366; PR 361 updated for C-708 F-C708-1), C-772 (PR 369). All code PRs had a full GX10 run on the exact head, 16 suites, 0 failed|error; every code PR names its killed mutants in its report.

Why nothing else is mine (checked against `origin/comms` and the open-PR file lists just now):
- C-45, C-51-class operator-key tests: files touched by open PRs 325, 355, 362, 371.
- C-69, C-94, C-10 (STATE.md), C-466 (tasks/todo.md), C-267, C-581: files touched by open PRs 342, 308, 305, 290, 316, 367 and the C-561 ruling in C-758.
- C-504 (and C-505 after it): the api.py files of kill-switch, lifecycle-manager and ops-console are touched by PRs 318, 330, 336, 344, 348.
- C-714..C-728, C-661, C-670..C-676, C-750: conditions for other authors' PRs.
- C-56: plan only, now overtaken by C-487 and PR 365 (Lane 13); I did not claim it. Close or tell me to write the migration list.
- C-773/C-774: Lane 13. C-757, C-758, C-760: not claimed by me; C-757 and C-760 touch spend-governor and docs I have not checked against open PRs.

Open from my own PRs (decisions or follow-ups, not blockers):
1. C-772 follow-up: pass `service=` in the 13 service call sites and audit the services for state-changing GET routes before any service sets a read key (needs the open PRs on those api.py files to land first; I can take it then).
2. PR 361: F-C708-2 (null `permissions:` block) and F-C708-3 (two workflow walkers) are the card owner's call.
3. PR 364: C-747 F-C747-1 (tuple-unpack alias; annotated or walrus constants in `_own_strings`) not done; I can add it if wanted.
4. C-397 leftovers: F-C395-2 (toJSON of other contexts), F-C391A-2 (10 numeric defaults skipped), F-C391A-3, C-396 P3.

I will re-read `origin/comms` every 5 minutes and take the lowest eligible card; tell me if a card should go to me directly.
