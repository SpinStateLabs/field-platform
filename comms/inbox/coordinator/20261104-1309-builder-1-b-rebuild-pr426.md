builder-1: B-REBUILD-PR426 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/617 "rebuild of #426", branch rebuild/pr426, head fe4bbb3f6a8f7d4e949b1ad00e26075a30de8ccc on origin/main 97dcfec1. Old head 43294fc0 untouched, not already on main.
DECISION NEEDED (human): CHANGELOG.md only (+21, docs). Two conflicts, both in Unreleased: main now has #520's topic summary 'main from 2026-10-30 to 2026-11-02'. I kept it and added this PR's two per-merge sections (Merges 9-15, Merges 1-8) after it; same intent as the reviewed change, but the result overlaps #520's summary. Merge it only if the per-merge sections are still wanted next to it; otherwise drop PR 426.
No test reads CHANGELOG.md; added text has no address/mailbox/key. Range-diff '!' = moved context only.
Range-diff:
1:  f7d8b71e ! 1:  21907198 docs: CHANGELOG delta for the eight main fast-forwards of 2026-11-01, acaf5f24 to 9addf44f (C-1107, BACKLOG B-06)
    @@ Commit message
         Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
     
      ## CHANGELOG.md ##
    -@@
    - 
    - ## Unreleased
    +@@ CHANGELOG.md: Source: `git log --since=2026-10-29` (110 commits). Ids are main commits; card i
    + - Docs: ADR pack 10 notes cite gateway code by symbol, with a test pinning the symbols, and state the bypass and telemetry-retention rules as the code has them (efebfc2, 2b94469, fb277a9, 85958f1); the ntfy runbook states that main sends the library and the test alert only, the six production senders being planned (300abeb, b5e98d8); capstone hardening evidence is dated as history (83ff023, cd68fe7); per-stage pre-flight checklists for Stages 1 to 3 in the runbook (2940dcc, d866b0d, cddca52); `per_caller` counts signed events only (f980f5c).
    + - Public safety (C-1130/C-1134): non-noreply mailboxes in plugin metadata, agent skills and the timekeeping manifest become placeholders (1ad562b); key fingerprints in `STATE.md` become a placeholder (9010866); manifest endpoint hosts become a documentation-range address (cc98514); deploy-status and build-id lines carry no status or sha (968cc2c). Don's ruling 2026-11-03 (Q-86 F1, in 793481f): the company's own contact stays in the plugin and marketplace metadata and the invoicing skill; client mailboxes stay scrubbed.
      
     +### Changed - eight fast-forwards of main, 2026-11-01 (main acaf5f24 to 9addf44f, 90 commits)
     +One line per fast-forward (MERGE to MERGE 8 in `comms/STATUS.md`). The commit ids are the ones on main (`git log acaf5f24..9addf44f`); the source PR numbers are the ones STATUS names for each batch, and each commit message carries its card and reviewer finding ids. Backfilled from `git log` of main; merge evidence (reviewer verdicts, test runs) is in `comms/STATUS.md` on the `comms` branch.
2:  43294fc0 ! 2:  fe4bbb3f docs: CHANGELOG delta for MERGE 9 to 15, main 9addf44f to 05942b98 (C-1127)
    @@ Commit message
         Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
     
      ## CHANGELOG.md ##
    -@@
    - 
    - ## Unreleased
    +@@ CHANGELOG.md: Source: `git log --since=2026-10-29` (110 commits). Ids are main commits; card i
    + - Docs: ADR pack 10 notes cite gateway code by symbol, with a test pinning the symbols, and state the bypass and telemetry-retention rules as the code has them (efebfc2, 2b94469, fb277a9, 85958f1); the ntfy runbook states that main sends the library and the test alert only, the six production senders being planned (300abeb, b5e98d8); capstone hardening evidence is dated as history (83ff023, cd68fe7); per-stage pre-flight checklists for Stages 1 to 3 in the runbook (2940dcc, d866b0d, cddca52); `per_caller` counts signed events only (f980f5c).
    + - Public safety (C-1130/C-1134): non-noreply mailboxes in plugin metadata, agent skills and the timekeeping manifest become placeholders (1ad562b); key fingerprints in `STATE.md` become a placeholder (9010866); manifest endpoint hosts become a documentation-range address (cc98514); deploy-status and build-id lines carry no status or sha (968cc2c). Don's ruling 2026-11-03 (Q-86 F1, in 793481f): the company's own contact stays in the plugin and marketplace metadata and the invoicing skill; client mailboxes stay scrubbed.
      
     +### Changed - seven more fast-forwards of main, 2026-11-01 and 2026-11-02 (main 9addf44f to 05942b98, 97 non-merge commits)
     +MERGE 9 to MERGE 15 in `comms/STATUS.md`, same conventions as the section below: commit ids are the ones on main (`git log 9addf44f..05942b98`), PR numbers are the ones STATUS names for each batch, the area groupings are read from the commit subjects, and merge evidence is in STATUS on the `comms` branch.
