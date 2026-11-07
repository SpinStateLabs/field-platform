# Don's authorization: Fly Stage 4b and a Fly redeploy (chat, 2026-11-07 ~15:23Z; recorded by the coordinator)

Source: Don's chat message "authorize Fly Stage 4b and a Fly redeploy". Answers the "not authorised" lines in 20261107-0430-estate-deployer-stage3-prep.md section 4 and 20261107-0500-coordinator-don-answers-stage3-prep.md.

## What is authorised
1. A Fly redeploy (new image from main). It must carry PR 867 (entrypoint exports FIELD_INTERNAL_SECRET_SHA256) only after PR 867 is merged on main with CI green and a reviewer PASS plus GX10 16/16 naming its head. Do not deploy an unmerged head.
2. Fly Stage 4b (REQUIRE on Fly), run by the estate-deployer through scripts f4b-0..4 and the Stage 4b checklist.

## What this does NOT change (every gate still applies; nothing here waives one)
- E1: f4b-0 --stage3-record needs a clean GB10 Stage 3 record, so Fly REQUIRE cannot precede GB10 Stage 3. GB10 Stage 3 is still held on: PR 837 merged, the GB10 renewal job fix, Don's go sentence `GO STAGE 3 <sha8>` and the live R-1 rehearsal with Don present. Those are Don's and are NOT given by this authorization.
- E2 renewal record, the 4a soak floor (f4lib), every internal caller carrying an identity, the red-team no-blocker read on the build being armed, rollback rehearsed.
- Setting the Fly internal-secret hash (a secret set) is not covered: Don has to say so in chat. No key or secret goes through chat or a report.
- If Stage 4b needs its own go sentence in f4lib, the exact token is Don's to type. The coordinator does not issue one for him.
- Roll back on any dropped_* rise or canary failure, as in Stage 2.
