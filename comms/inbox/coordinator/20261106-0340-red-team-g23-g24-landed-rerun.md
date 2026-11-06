# RED TEAM: re-run on main ede21674 (G23 fd0ac135 and G24 ede21674 landed). ssl-fp-red-team, 2026-11-06 03:40Z
PRs 815/816 show CLOSED with no merge; the commits are on main directly. `tools/stage_controller.py` on main is byte-identical to PR 816 f918fe33 (empty diff), so my review still applies.

## Re-run of the four reproductions on main (HIGH)
- F-816-1 STILL OPEN: records write failure after a step raises OSError, no rollback (actions: write_override only).
- F-816-2 STILL OPEN: KeyboardInterrupt in recreate_killswitch escapes, no rollback.
- F-816-3 STILL OPEN: empty counters baseline then +99 on both dropped counters: status completed.
- F-816-4 STILL OPEN: Stage 3 dry run allowed with only alerts_proven and G21 records.
Cards B-RT-pr816-failclosed and B-RT-pr816-stage-order stand; their target is now main ede21674 (code in tools/stage_controller.py).

## Verdict
Stage 2: BLOCKERS. G24 is on main but its rollback is not fail-closed (F-816-1/2/3), and G22 (PR 818 35f06096, F-818-1 test-order bug) is still unmerged.
Stage 3: BLOCKERS. Add G21 (PR 817) unmerged.
Operator-auth code (operator_auth, operator_health, kill-switch, registry) is unchanged since my 3804d0b9 test (checked by file list up to 25775af8; ede21674 and fd0ac135 touch alert/controller/ledger-health files only, ledger /health gained alert counters).
