# Builder Lane 1: C-1021, every soak duration the repository docs expect Don's outside-repo scripts to use

Report only; no script outside the repository was read or touched (none is in this repository). Line numbers are against origin/main at the time of writing (batch CA, acaf5f2 plus later lane commits). Whether each script actually follows the doc is NOT verified: I cannot read them. STATE.md lines are history, not expectations; they are listed last for the coordinator.

## Scripts the docs name (all outside the repository)
- docs/runbooks/v1.2-deploy-rollback.md:927-928: the key-generation script, the A7 arming script, the A7 soak script, the A8 arming script, and the pre-arming gate checks (a Python file). My PR 379 (head f958cab) rewrites :927 only to say none of them is in this repository and to drop the workstation name.
- tasks/next-session-phase-g.md:7 and STATE.md:1077-1337 name more of them (A7b arm/require, gate scripts) as past steps.

## 1. The five-minute soak (Don's 2026-11-01 rule; batch BZ d0e52bc put it on main)
- docs/runbooks/v1.2-deploy-rollback.md:925 (GB10 first with a >= 5 min soak, then Fly), :949 (A7: "Soak >= 5 min, then: every event appended since arming carries `signature`..."), :1000 (A9 arming: "Soak >= 5 min, then re-run it").
- tasks/todo.md:282 (GB10 first, then a >= 5 min soak, then Fly), :426 (each step: arm, C0, >= 5 min soak), :440 (A7 row: soak >= 5 min), :477 and :624 (">= 5 min soak with C0 every 15 minutes"), :630 (restart count unchanged across a 5-minute soak).
- tasks/next-session-phase-f.md:60 (arming with a >= 5 min GB10 soak per step).
- Changes by my open PRs: PR 392 (C-911, head 36c0d55) changes :477 and :624 to "C0 every 5 minutes". PR 379 does not change :925/:949/:1000. Card C-466 remaining items (a fork is on it) would change :949 and todo.md:440 to require at least one new signed event.

## 2. The scheduler soak override (lifecycle, crosswalk, witness)
- Default today: FIELD_LIFECYCLE_EVERY and FIELD_CROSSWALK_EVERY are 86400 (compose, gb10 overlay and Fly entrypoint; cited in my PR 382). The docs call this the 25 h soak:
  - tasks/todo.md:512 (lifecycle scheduler soak ">= 25 h, running in parallel"), :601 (schedulers: evidence from the ">= 25 h soak (lifecycle, crosswalk, witness)"), :646 (A1 row: scheduled swept_at > StartedAt + 86400 s), :674 (Schedulers row: timestamp > start + interval, ">= 25 h soak").
- Don's rule (C-806): a soak that must not wait 24 h overrides FIELD_LIFECYCLE_EVERY and FIELD_CROSSWALK_EVERY by environment for that run only; the evidence check uses the same interval; the override is removed afterwards. PR 382 (head 0dde283) states this in services/lifecycle-manager/README.md, services/compliance-crosswalk/README.md and services/sealed-ledger/README.md and rewrites todo.md:646 and :674. The witness has its own variable, FIELD_WITNESS_EVERY (default 3600), no separate override variable (PR 382's sealed-ledger text).
- What the outside scripts must do (from those sentences): set the two variables to a soak-length value for the run (whole seconds, digits only; 0 is off), remove them after the run, and judge the evidence against the same interval, not 86400. NOT verified: whether any script does this.

## 3. Rotation soak (30 minutes per Don's ruling)
- No sentence on main states it. PR 57's code (refs/pull/57/head, packages/field-core/src/field_core/rotation.py:129-130, :251) has MIN_SOAK_S = 15 * 60 and SOAK_TICKS = 3; the 30 minute value is card C-1019 (a production change on PR 57, not done by me). No doc to cite yet.

## 4. The 24 hour final soak
- Only the ">= 25 h" lines in section 2 (todo.md:512, :601, :674) and the plan's final soak; no doc sentence says "24 hours only for the final soak" in those words. PR 382's text keeps ">= 25 h at the 86400 s defaults".

## Stale expectations for the coordinator (STATE.md is not mine to edit)
- STATE.md:1101 ("A9 go after a clean >= 1 h A7 soak"), :1189 (">= 1 h GB10 A9 soak"), :1268 and :1322 ("after a >= 1 h soak") read as a one hour gate; the 2026-11-01 rule replaces it with five minutes. Card C-466's F-C447-4 (a decision for Don) asks for one line saying so.
- tasks/next-session-phase-g.md and docs/runbooks/v1.2-deploy-rollback.md at PR 57's base still say ">= 1 h" in a few places on that branch; not on main.

Not run: any script, GX10, CI. This report cites lines, not behaviour.
