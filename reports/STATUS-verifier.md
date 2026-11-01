# Verifier (cloud, Lane 8) status for the coordinator

STOPPED on the principal's instruction. No loop, no polling, no runs in progress.

Per-head reports for every head verified are in this directory (newest report per PR and head wins; a result applies to one full head SHA and names the main it ran on).
Last main seen: 9468b184 (batch cb12). Merge status of every open head was re-checked against each main move up to that point; whole-suite results exist for most heads on 9468b18 or an older main, and the report for each head names which.
Not re-run when stopped: PR 409 and PR 410 were in flight (results not written); heads that moved after the last poll.

Open items for whoever restarts the lane:
- Main moves about hourly and a full pass over every open head takes several hours, so suite results on the newest main are partial; merge status is cheap and current.
- Flaky: services/sealed-ledger/tests/test_ledger_latency_100k.py::test_health_stays_o1_at_100k_while_this_process_appends (fixed p95 bound, failed 2 of the first 5 solo runs, then 15 passes).
- The cloud gate merges the head as a whole; a head that is itself a merge of main can conflict when its commits are cherry-picked (C-1097 note).
- Python 3.13 only; Actions runs for heads are not readable without credentials.
