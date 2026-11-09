# fp-estate-deployer: Stage 3 prep steps, follow-up after Don's answers (2026-11-09 ~12:20Z)

Follows 20261109-0526 report. Estate writes: none. Local writes: one records file, one local script edit, monitor files.

## A. G21 RECORDED (HIGH, direct)
`stage_controller.py record gate G21 --build-sha <41afda50 full>` run from a clean worktree at 41afda50 (PYTHONPATH set to it), file `stage-controller-records.jsonl` in the rog-command tasks dir `gb10-require-scripts` (next to pg-run.py). Row: gate G21, ok, sha8 41afda50, ts 2026-11-09T12:13:41Z. Evidence: 9a2417c04 and 36fa4aeb2 ancestors of 41afda50; manifest test 6 passed/4 skipped; lifecycle G21/c73/p29 tests 55 passed.
- alerts-proven: NOT recorded (needs Don's phone receipt). The GB10 has no ntfy topic configured; the coordinator arranges the topic file (machine-to-machine); then alert-test, then Don confirms in chat, then `record alerts-proven --build-sha 41afda50...` into the same file.
- Note: this file is on rog-command, not the GB10; the controller driver must be pointed at it with --records.

## B. Stage 2 MONITOR RUNNING (started 2026-11-09 12:14Z)
- State read before start (direct, HIGH): kill-switch enforce, other seven log-only, dropped_unauthenticated and dropped_refused 0/0 on all eight, canary halted=False. Kill-switch refused_count still 45. On-shape, so started.
- Glue is NEW and read-only: `probe.sh` (reads the eight /health blocks and the canary status; no secrets) plus `monitor.py` (a session-run loop, 48 polls x 5 min). No new rollback logic: on a trigger it calls the reviewed `s2-6-rollback.sh` through `pg-run.py --live --allow-not-tip`, once, then stops. Triggers: any dropped_* above 0, any mode other than kill-switch enforce / seven log-only, canary halted not False; an unreadable probe gets one 30 s retry. Files: D:/claude-tmp/s2mon (monitor.log holds counts only).
- It lives and dies with this session (a harness background task); it ends after about 4 h. Poll 0 OK at 12:14:59Z.
- A live rollback from it could be denied by the permission classifier; if so it stops and logs, it does not work around.

## C. s3-6 edit and dry run
- Edited LOCALLY (not deployed): after the seven are recreated, s3-6 now runs `pg_printenv_loop killswitch` and `pg_check_health stage2 killswitch` (kill-switch enforce, seven log-only), non-blocking (a mismatch is a warning, the kill-switch step still follows). `bash -n` OK.
- The stub harness `_stubs/dryrun.py` could NOT run it: the harness is pinned to 14fed1e, which is not in its scratch clone (s2-0 aborts "SHA not in the checkout", exit 1 vs expected 0), so every later step cascades. Stopped it; nothing reached the GB10. So the edit is syntax-checked only, NOT exercised (UNVERIFIED behaviour). Repinning the harness to 41afda50 needs a decision.
- The dry run changed nothing on any host.

## Open
1. ntfy topic file on the GB10 (coordinator) then alert-test, Don's receipt, `alerts-proven` record.
2. Repin dryrun.py to 41afda50 (or main) to exercise the s3-6 edit, then put the edit through review (it is in the private tasks tree, not a PR).
3. Monitor ownership beyond this session's life.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
