# DECISIONS-FOR-DON

Don's standing words: "use your recommendations". Entries are PROVISIONAL until Don rules.

## D-1 Integration branch = `main` (2026-10-28, HIGH)
Choice: `main` (the brief left it as a placeholder; HEAD equals origin/main c8ecba7). Alternative: another branch. Reversal: none needed unless Don names another.

## D-2 Coordinator ruling (2026-10-28)
Don: "I coordinate". This session (c6f632) is the field-platform coordinator. Sessions "Force-Field coordinator takeover" and "handoff" run in the Agentic AI and LLMOps at Scale worktrees (another repo, MEDIUM) and verify only.

## D-3 Teammates (2026-10-28, PROVISIONAL, MEDIUM)
Choice (updated 2026-10-28): builder = session "Work queue review" f77070; reviewer = session "FIELD platform adversarial review" 86dc6f; both messaged. Alternative: other sessions. Reversal: rename inbox dirs and re-message.

## D-4 Draft PRs #55 #56 #57 stay draft until verified (2026-10-28, HIGH)
Choice: no merge without reviewer PASS plus GX10 run on exact head. Alternative: merge on CI green. Reversal: n/a.

## D-5 #57 persistent post-PROMOTE fault (reviewer Decision C) (2026-10-28, PROVISIONAL, MEDIUM)
Choice: retry cap plus CRITICAL alert before any live use. Alternative: retry forever with hourly keyrotation.failed. Reversal: drop the cap commit (C-15 separate commit).

## D-6 #57 abort refusals halt until R9 acts (reviewer Decision D) (2026-10-28, OPEN, LOW confidence)
Conflicts with P36 unless R9 reconciles automatically. I do not know P36's text. Default: keep halting (fail closed) until Don rules.
