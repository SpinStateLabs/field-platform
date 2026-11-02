# Lane R: claims C-1174 and posts the R4b slice list instead of code (the card's own stop rule)

C-1174 says: implement R4b as my C-1161 note scopes it, one small card per slice, and "stop and post the slice list if the note leaves any scope open". It does, so this is the slice list; nothing is built. Source: my design note 20261102-0530-rebase-builder-design-C-1161-r4b-r9.md; reviewer C-843 (Lane 5). Read, not measured.

## Why code cannot start yet (HIGH, read)
1. The rotator is not on main: rebase/57-c1156 (648a933e) has Lane 7's PASS WITH CONDITIONS (C-1157) but still needs CI (no PR is open for it) and a GX10 run, and it is not landed. R4b runs the real `tools/operator_rotate.py`; building the e2e on the branch before it lands means a second rebase of the e2e when it does.
2. Don's open decisions in the note (soak length, whether R4b's CI job is wanted in the 7-job pipeline, park semantics) change slice 5 and the soak value used by slices 2 and 3.
3. The note's own order puts the F-C843-3 to -6 fixes before or with R4b.

## The slices (one small card each, fail-first, made-up keys only)
- R4b-P (prerequisites, separate cards, builder): F-C843-3 (lost status.json freezes the rotation as foreign_edit), F-C843-4 to -6 as C-843 lists them (I name them by id because I have not re-read each; C-843 puts -5 and -6 at LOW confidence, uid and int64 dependent), C-18 F-C18-5 and F-C18-9, C-16 #6.
- R4b-1 (builder): a compose profile with the eight operator-block services, one shared made-up operators file (format 2) and a key volume at mode 0600; fixtures generated at test time, nothing committed that looks like a key. Done when the profile starts and each service answers /operator/rotation-state.
- R4b-2 (builder): the happy path: one identity rotated end to end with a short `soak_s`; asserts every service says `current` for the new key and `none` for the old hash, ledger events in order with only 16-hex fingerprints, no key bytes in any log or event, the old key file removed only after both checks.
- R4b-3 (builder): kill the rotator mid-SOAK and resume from the journal; asserts convergence and no lockout.
- R4b-4 (builder): the refusal cases on all eight services (a retired hash refused, a late-reloading service tolerated up to the VERIFY-NEXT limit, a generation skew above the file's).
- R4b-5 (Don's call first, then builder): the CI job for the e2e (a workflow change; adds run time to the 7-job pipeline).

## What I would start on first, if you want it now
R4b-1 on a branch from main that carries rebase/57-c1156 (a stack, as for rb-stack2), clearly marked as such, so the rotator is there to run. Say "start R4b-1 on the stack" and I do it; otherwise I wait for the rebuild to land. I hold C-1174 until you say which.
