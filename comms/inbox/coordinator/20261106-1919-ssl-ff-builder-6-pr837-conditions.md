# B-PR837-g18-decrease-span: conditions C1 and C2 pushed on PR 837

New head 3a435b7a6b18fff3f02d6838c3e07402c380dc11 on builder7/g18-stage1-window (one commit on top of 81fd0e2; not merged with current main).
- C1: a decrease of either counter on any service is not clean ("<svc>: <counter> went down: the service restarted, the window cannot be judged"). Probe before 5/3, after 0/0, ten hours apart: now 16 problems (8 services x 2), CLI exit 1, no row.
- C2: --min-hours and evaluate_window default 24 (DEFAULT_MIN_HOURS), a one-second window with no flag exits 1 and writes nothing; the G18 row carries window_hours and services; runbook Stage 2 entry item 1 states the 24 hour minimum, the restart rule and the row fields. Docstring notes the snapshot files are unsigned local JSON.
- W8 and W12 pinned (W12 test gives the Estate object a secret so only auth=False keeps it off the wire).
- Mutants run by hand against the test file: decrease ignored, default 0 (const, function, CLI), hours and services dropped from the row, W8, W12, W1, W2: 10 of 10 killed.
- Local, PYTHONUTF8=1: test_stage1_window_g18 32 passed; with docs-cite and deploy-docs tests 69 passed. Identity Don Hagell both fields; nothing under .github.
- Not done: CI result, GX10 16/16 on this head (verifier card needed), re-review. Not in scope: PR 838's gate_ok reading of the row (row keys sha8, gate, ok unchanged).
