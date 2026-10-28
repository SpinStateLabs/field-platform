# DECISIONS-FOR-DON

Don's standing words: "use your recommendations". Entries are PROVISIONAL until Don rules.

## D-1 Integration branch = `main` (2026-10-28, HIGH)
Choice: `main` (the brief left it as a placeholder; HEAD equals origin/main c8ecba7). Alternative: another branch. Reversal: none needed unless Don names another.

## D-2 Coordinator ruling (2026-10-28)
Don: "I coordinate". This session (c6f632) is the field-platform coordinator. Sessions "Force-Field coordinator takeover" and "handoff" run in the Agentic AI and LLMOps at Scale worktrees (another repo, MEDIUM) and verify only.

## D-3 Teammates (2026-10-28, PROVISIONAL, MEDIUM)
Choice (Don, 2026-10-28): reviewers = "FIELD platform adversarial review" (86dc6f) and "Teammate reviewer onboarding" (not in ListAgents, unreachable by me). Builder = "Work queue review" (f77070) until Don names another. Reversal: re-message.

## D-4 Draft PRs #55 #56 #57 stay draft until verified (2026-10-28, HIGH)
Choice: no merge without reviewer PASS plus GX10 run on exact head. Alternative: merge on CI green. Reversal: n/a.

## D-5 #57 persistent post-PROMOTE fault (reviewer Decision C) (2026-10-28, PROVISIONAL, MEDIUM)
Choice: retry cap plus CRITICAL alert before any live use. Alternative: retry forever with hourly keyrotation.failed. Reversal: drop the cap commit (C-15 separate commit).

## D-6 #57 abort refusals halt until R9 acts (reviewer Decision D) (2026-10-28, OPEN, LOW confidence)
Conflicts with P36 unless R9 reconciles automatically. I do not know P36's text. Default: keep halting (fail closed) until Don rules.

## D-7 Cloud reviewer (2026-10-28, PROVISIONAL, HIGH)
Don: "Teammate reviewer onboarding" is a cloud session. Choice: it takes read-only card C-18 from origin/comms (I cannot message cloud sessions); its output is UNVERIFIED until re-run on the GX10. Alternative: bind a local reviewer. Reversal: reassign C-18.

## D-8 Don: "go with recommendations" (2026-10-28)
D-5 (retry cap plus CRITICAL alert) confirmed. D-6 (keep halting, fail closed) confirmed pending a P36 reading.

## D-6 update (2026-10-28, from reviewer C-22, MEDIUM)
P36 (controller project, tasks/DECISIONS-FOR-DON.md:317-321) covers stage gates and alerts, not the rotator: no literal conflict. Your 2026-10-27 ruling "key rotation is continuous machine work" does conflict with "halts until a human acts". Provisional: R9 reconciles automatically where state is provable, halts plus CRITICAL alert only where not (C-29). Until then no live use of the rotator.

## D-9 Unpushed t1 commit recommitted (2026-10-28, HIGH)
Local teammate-don/t1-renew-token-signed (D:/claude-tmp/td-t1) had author donhagell@gmail.com and an empty committer email. Worktree untouched; same tree recommitted as fix/renew-token-signed @8269445 with the repo identity, pushed. Reversal: delete the remote branch.
