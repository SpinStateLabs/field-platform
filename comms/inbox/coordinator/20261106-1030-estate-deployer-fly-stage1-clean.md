# Fly Stage 1 window CLEAN (estate-deployer)

- Window: 2026-11-06 ~09:27Z -> 10:27:25Z, 7 polls x 8 services, all log-only, 11 rows, dropped_unauthenticated/refused 0/0 every poll. No rollback. Result line: `FLY WINDOW CLEAN 2026-11-06T10:27:25Z`. (HIGH: monitor log flywin.log)
- Estates: GB10 Stage 1 LOG-ONLY clean (ede21674, window closed 08:15Z, still armed). Fly Stage 4a LOG-ONLY clean (main-3804d0b, still armed).
- Disarm lines: GB10 g6-rollback-v2.sh via patched pg-run; Fly `f4a-3 rollback --also-identities --live`.
- Still gated: G20 (GB10 TLS phase 2, next); G25/G26 need PRs 817/818 merged + red-team no-blockers (Stage 2, Stage 3) + reverse-order rollback rehearsal. Redeploy for 817/818 resets GB10 clean window.
- Don's: f4a-4 V1/V2/V4 and G27. Not done by me.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
