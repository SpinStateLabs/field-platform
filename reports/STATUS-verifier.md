# Verifier (Lane 8) status for the coordinator

STOPPED on the principal's instruction. No loop, no polling, no runs in progress.

Reports for every head verified are in this directory (one file per head, newest per PR wins; a result applies to its SHA only).
Heads reported GREEN at the time of stopping were verified against main at the time shown in each report; many PRs have since moved heads.
Not verified when stopped (queue at last poll): 340 (new head), 342, 343, 344, 346, 348, 349, 351, 352, 353, 355, 356, 357. Skipped by rule: PR 57 and PRs titled Batch.

Open items for whoever restarts the lane:
- PR 330 report flags one sealed-ledger failure on a first run (1 failed) that passed on rerun and did not reproduce in four more runs; the failing test was not captured.
- 300 with 306 and 305 with 308 were each verified alone; mutual conflicts untested.
- Python 3.13 only; Actions runs for heads are not readable without credentials; ops-console node harness is not run separately.
