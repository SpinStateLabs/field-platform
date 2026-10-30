# Verifier (Lane 8) status for the coordinator

Updated 2026-10-30. Main at last check: a9dc4f3de716b7377dbc8e558520b4464cbf76b6. Python 3.13.17 only.

Reported (one report file per head, in this directory): 288, 290 (older main; re-run in progress), 293, 294, 296, 297, 299, 300, 301, 303, 305, 306.
In progress (oldest first): 290 re-run on current main, 308, 309 (workflow: strict-YAML check), 310.
Skipped by rule: 57, "Batch" PRs (302, 304, 307). 292 was a Batch PR.
Closed or already in main: 291, 295 (patch already on main).

Notes:
- 310 is stacked on 293 (its base is a batch-branch commit, not main); its first commit is already on main, so only its second commit is checked.
- 300 and 306 both edit federation-broker engine/api/README/demo.sh. Each was verified alone; mutual conflict NOT tested.
- Public Actions runs for 308, 309, 310 heads: none returned by the unauthenticated API (cannot confirm either way).
- The ops-console node harness is not run separately.

Blockers: none that need money or features. Limits: only Python 3.13 available; no GitHub write tools except the push to this branch.
