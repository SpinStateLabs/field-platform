# ssl-ff-builder-9: B-COND-PR489-1e8f7fe -> pushed to PR 489

PR 489 new head a447c4450a38ad140b1e1148b23e2720c2bd7fac (merge commits of main plus fixes; author AND committer Don Hagell noreply; remote verified). 3-dot diff vs main: 3 files (engine.py, cli.py, the test file); merge-tree against current main is clean. No force push (main merged in, twice, because it moved during the work).
C1: conflict in engine.py resolved; main's `_inline` (PR 737) is now there, so `_skipped_id` is removed and the skipped-record line uses `_inline` outside the code span; tests pin `_inline` and that `_skipped_id` is gone.
C2: unreadable_timestamps is a finding: `lifecycle sweep` exits 3 and writes one `lifecycle.unreadable_timestamp` ledger escalation per record (kind, record id, field; never the value; agent subject only for agent records). CLI tests: exit 3 on a skipped record, exit 0 on a clean sweep.
U1: non-string timestamps pinned (int, None, list, dict, bytes). Reviewer's mutant U1 needed bytes: str-only inputs raise AttributeError, not TypeError.
Mutants (4, all KILLED): exit code without unreadable, no escalation, TypeError arm, raw id instead of `_inline`. test_sweep_unparseable_ts.py 31 passed.
Full suite NOT completed here: the first ~40% passed with no failure; tests/test_cli_clients_no_proxy_c575.py fails on a ConnectTimeout (needs network, not touched by this PR); run was cut at the time limit. CI is the judge. README row for the exit code not updated (docs not in the conditions).
