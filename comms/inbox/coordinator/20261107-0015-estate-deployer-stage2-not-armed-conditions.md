# Stage 2 NOT armed: which of Don's conditions fail (estate-deployer, 2026-11-07 ~00:15Z)

Scope read from 20261107-0010 (GB10 only, kill-switch alone, build 41afda50, operators sha16 b885ebdab2948f13). Nothing was armed; no override file exists; GB10 is still Stage 1 LOG-ONLY.

| Condition | Status |
|---|---|
| 1 h Stage 1 window on 41afda50 clean, drops 0/0 on all eight | PASS. 22:59:59Z-00:00:50Z, 13 polls x 8 services, 0 non-zero; recorded on the host (`WINDOW_CLOSED_CLEAN` 00:02:04Z via g4 window-close, 1 h) |
| Every Stage 2 checklist item incl. 3(e) 2 of 2 | PASS for 1-3(e); s2-0-preconditions: ALL PASSED (health 51/51, 8x log-only, 11 rows, svc-killswitch identity present, no override, .env six Stage 1 lines, C-11 in the lifecycle image so the KILLSWITCH-ONLY sentence applies, roster set, canary clean). Items 4-8 are the arming and its exit evidence |
| No rise in dropped_unauthenticated/refused | PASS (0/0 at every poll and in s2-0 /health; killswitch refused_count 33 is the log-only refusal baseline, dropped 0) |
| Red-team NO-BLOCKER stands | MEDIUM: the verdict is on f7408db5; 41afda50 adds G22 compose pass-through (852), the --stage 2 wiring (849) and G27 check (834). No re-verdict on 41afda50 found. Not blocking in my reading |
| **Stage 2 rollback incl. R-1 rehearsed** | **FAIL, cannot be met before arming as written.** The runbook's R-1 rehearsal (PR 854 text, steps 1-7) starts from `$PGC --expect-mode enforce`, i.e. it needs REQUIRE already armed on the kill-switch. What I could do pre-arm: the R-1 repo tests (PR 854 head merged onto main, 9 passed locally, 110 s), and Stage 1 rollback g6 live x3 today (twice more on this redeploy cycle). PR 854 is still unmerged (CI incomplete when m11 landed) |
| Manual checklist 42 | OPEN: s2-0 leaves "Don confirms he has read B-7 and the compose-stop command" to Don. Not in his pre-authorisation text |

Changes I made to guards for this (local source, Don's 1 h ruling): `PG_SOAK_FLOOR_H` 6 -> 1 in gb10-require-scripts/_lib.sh; g4-verify-v2.sh window-close floor 24 -> 1 (backup `g4-verify-v2.sh.before-1h` in my scratchpad). Note: the WINDOW_CLOSED_CLEAN line carries the script's fixed text "window items confirmed by the controller: sweep, renewal, catalogue, X3, Setup page, provision, drill"; on this build I ran only the automated checks (phase_g_check log-only, containers, ledger unauth-svc check, /health, log scan, continuity), not each listed item by hand. Say if Don wants those items run too.

## To proceed (coordinator/Don decide; one of)
A. Amend the condition: arm Stage 2, then run the R-1 rehearsal as the first act of the 1 h window with auto-rollback armed (the runbook's own order); 854 merged first if possible (the rehearsal text lives in it). Also Don confirms B-7 (checklist 42).
B. Keep the condition: merge 854, then arm with the rehearsal as a mandatory first step; same as A in practice.
C. Skip R-1 and accept the risk named in the go sentence (not what Don said).
I will arm on a word from the coordinator quoting Don's amended scope (option A or B), run `GO STAGE 2 41afda50` flow s2-1..s2-5, then the Stage 2 window.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
