# Q-03 reviewer report: docs/runbooks references to paths, services, modules, images, volumes (tree of PR 91, main 4cf73d5 + registry guard)

VERDICT: no stale reference found. 113 repo-path references, 110 resolve; the other 3 are explained. One runbook sentence about the registry was false before PR 90/91.

OBJECTIONS FIRST
1. A reference check proves a name exists, not that the command around it works; flags, arguments and expected outputs were not run.
2. I extracted only backticked paths under known roots, compose service names after `docker compose ... exec|run|logs|restart|up|stop`, `python -m` modules, image tags and `field-*` names; commands in fenced blocks outside those shapes were not checked.
3. The live GB10 and Fly estates were not consulted (container, volume and secret names there can differ from the repo).

ASSUMPTIONS
1. Files: `docs/runbooks/ntfy-alerts.md` (182 lines), `token-renewal.md` (1,490), `v1.2-deploy-rollback.md` (2,064). Tree: `git ls-files` on `~/ff-work/r08c` at 7b4d6f7. [HIGH]

REASONING
1. Repo paths (roots tools/, services/, packages/, integration/, docs/, manifests/, plugins/, agents/, tasks/, defence-shield/, .github/): 113 references; 110 resolve to a tracked file or directory. Not found: `integration/demo/.env` (v1.2-deploy-rollback.md:161 and 9 more): a runtime file, `.gitignore:16 *.env`, correct to be absent; `tasks/stage0-assemble-operators.py` (:1242) and `tasks/stage0-keys.ps1` (:1250, :1251): the runbook says the assembler is "outside this repo" (the Force-Field repository) and names `stage0-keys.ps1` as a Force-Field script; `git log --all` finds neither in this repository. Not stale; but a reader of this repo alone cannot run those steps. LOW, INFO (F-Q03-1). [HIGH]
2. Compose service names used after `docker compose ... exec|run|logs|restart|up|stop`: 3 distinct names found, all present in `docker-compose.yml` or `docker-compose.gb10.yml` (20 services). [HIGH]
3. `python -m` modules: only `field_agent.canary`; importable from the repo trees. [HIGH]
4. Images: the runbook names `python:3.12-slim` (matches both Dockerfiles); compose/Fly use `caddy:2-alpine` (not named in the runbooks). [HIGH]
5. Volumes and container names: the compose file declares `caddy_data`, `field-attest-keys`, `field-data`, `field-keys`, `field-manifests`; the runbook's other `field-*` names are ad hoc backup/staging volumes or containers (`field-data-pre`, `field-data-post`, `field-manifests-pre`, `field-backups`, ...) and the container names `field-platform-<svc>-1` rely on the compose project name, which is fixed in the file (`docker-compose.yml:11 name: field-platform`), so they are stable. 40 `field-*` tokens, none unresolved against a compose volume that should exist. [MEDIUM: names compared, not created]
6. Content check, one sentence: v1.2-deploy-rollback.md:1774 "`retired -> active` is refused in the registry" was false with the operator layer OFF until PR 90/91 (F-C155-1); it is true after the guard. LOW, F-Q03-2 (fixed by PR 91). [HIGH]

CONCLUSION
The runbooks reference what exists. Add one sentence to the stage-0 section that the two `tasks/stage0-*` scripts live in the Force-Field repository, with its path. Not done: running any runbook command; flags and outputs.
