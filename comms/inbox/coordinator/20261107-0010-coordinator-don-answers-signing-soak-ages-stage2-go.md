# Don's answers, Don-only questions (chat, 2026-11-06 evening; recorded by the coordinator)

Asked via the question tool; Don chose the recommended option on each.

1. Signed go sentence: NOT NOW. The architect's plain token `GO STAGE <n> <sha8>` bound to the run's build sha stands. Signing is a future feature, not built.
2. Soak minimum: KEEP 1 h per stage on both estates (auto-rollback on any dropped_unauthenticated or dropped_refused rise).
3. Record ages: ACCEPT the architect's values (alerts 24 h, G18 and Stage 2 window 72 h, stage_done 7 d; sha-bound G21/G22 rows never expire). Confidence LOW: measured defaults, not from a source.
4. Stage 2 arming on the GB10: PRE-AUTHORISED by Don in chat, scope below. This is Don's per-action chat OK for the arming step; it is not authority for Stage 3 or Fly.

## Scope of the Stage 2 pre-authorisation (coordinator's reading of Don's answer; tell me if it is wrong)
- GB10 only. REQUIRE on the kill-switch ALONE (Stage 2). Registry and the other seven stay LOG-ONLY.
- Build: the one the checklist was run on (41afda50 or the current deployed main), operators file sha16 b885ebdab2948f13 (11 rows).
- Arm only if ALL hold at arming time: the 1 h Stage 1 window on that build is judged CLEAN with drops 0/0 on all eight; every Stage 2 checklist item passes (runbook :1471) including 3(e) = 2 of 2; red-team NO-BLOCKER still stands; the Stage 2 rollback (incl. R-1) is rehearsed; no rise in dropped_unauthenticated_records or dropped_refused_records.
- After arming: 1 h Stage 2 window with auto-rollback on any rise; report; the Stage 3 go is a separate decision (not authorised).
- If any condition fails: do not arm; report which one. If the classifier blocks the arm, stop and tell the coordinator (never work around it).
