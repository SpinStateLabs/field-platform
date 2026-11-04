# Reviewer (lane A, tools): PR 507 (scout S-A5) fly_identity_check: a non-object /health body is reported, not raised

**Verdict: PASS WITH CONDITIONS on head `9f593b59a86541b3702f0b3aa78d70702bbc0343`.** Head unchanged at start and end; base current main (the diff is the PR's own 2 files); 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): `tools/fly_identity_check.py` (+7/-1): `_health` stores the decoded body only if it is a dict, else `{"_error": "NotAnObject"}`; `check_health` reports `<svc>: /health unreadable (NotAnObject)` for a non-dict entry instead of calling `.get`. New `test_fly_identity_health_shape_sa5.py` (15 tests).

## Objections first
1. The checker is a deploy-gate verifier: it must report, never crash, and a body it cannot read must not read as healthy. A non-dict entry becoming a PROBLEM line keeps that (the problem count is the signal).
2. An empty object `{}` is a valid dict and still passes the dict guard; whether an empty `/health` should count as healthy is the existing `check_health` logic, not touched here (not run).
3. The 65536-byte cap truncates a larger body so it fails to parse: the cap is a safety limit, pinned only at far distances (survivors below).

## Measured (GX10 ~/ff-work/wt-ln507, own venv, python -B)
New file 15 passed (0.02 s). The existing `test_fly_identity_c5.py` run together with it did not finish within my tool window on a busy GX10 (other lanes had ~15 pytest processes), so I do NOT report a baseline for it; the mutants below ran against the PR's own file only. CI at read: see Conditions. 16-suite not run by me.

## Mutants (21 rows on `fly_identity_check.py`, PR file only; source restored, worktree clean; an interrupted first run left a mutant in the source, which I reverted before this run)
| Behaviour | Killed | Survived |
|---|---|---|
| H1 a decoded non-object becomes an error entry | 5 | 1 (gap: the error name `"Other"` instead of `NotAnObject` passes) |
| H2 an object body is kept unchanged | 1 | 3 (1 equivalent: `dict(body)` copy; 2 gaps: dropping a key such as `image` and treating `{}` as an error both pass) |
| C1 `check_health` tolerates a non-dict entry | 5 | 1 (gap: the message without the service name passes) |
| R1 the read cap is 65536 bytes | 2 | 3 (gaps: caps of 32768, 65535 and 65537 all pass; only 131072 and unbounded are caught) |
Totals counted from the table: killed 5+1+5+2 = 13; survived 1+3+1+3 = 8; 21 rows. Of the 8 survivors, 1 is equivalent and 7 are unpinned detail. H2 and R1 are below the 4-kill bar.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: GX10 16-suite 16/16 on a head containing main, which also settles the existing `test_fly_identity_c5.py` that I could not run to completion.

## Findings (non-blocking; new PR only)
- F-507-1 LOW-MEDIUM: pin that an object body keeps its content (a `{"image": ...}` body must reach `check_health` intact): the checker compares the image, so dropping a key would be a silent miss (H2).
- F-507-2 LOW: assert the exact `NotAnObject` text and the service name in the problem line (H1, C1); put a body of 65535 and 65537 bytes either side of the cap (R1).
