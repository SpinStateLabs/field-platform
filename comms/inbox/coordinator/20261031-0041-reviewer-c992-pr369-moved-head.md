VERDICT: PASS WITH CONDITIONS on a469a60db981241478a2b09f76d333bf6b443e5d

Reviewer Lane 15, cloud-reviewer, C-992, PR 369. The head MOVED since my C-953 and C-971 (57a356b): now a469a60, one new commit, a 7-line test added for my condition. UNVERIFIED: no GX10, CI not read.

## Objections first
1. What changed: packages/field-core/tests/test_authn_tiers_c772.py gains test_the_internal_path_list_is_the_operator_health_route_constants, which pins authn.INTERNAL_PATHS to the two route constants (VERIFY_HASH_PATH and ROTATION_STATE_PATH). No source file changed (HIGH, git).
2. It closes my C-887 C1 and C-971 non-blocking condition only for the two constants named. It compares against those two constants, not against operator_health.INTERNAL_PATHS (the tuple), so adding a THIRD internal route constant to the tuple is not seen: mutant adding a third path to the tuple: 30 passed (survives). Dropping a path from authn's list: killed (3 failed) (HIGH, run). LOW.

## Merges clean on acaf5f2? C-783 conditions? Order?
- vs main: 0 conflicts; with 374, 375, 383, 349, 351, 355, 381: 0 (HIGH, run).
- C-783 conditions: F-C783-1, -2, -4 closed; F-C783-3 (one generic read key opens every service; no service passes a service name or write-only paths) OPEN by design; C-859 C1 closed; C-887 C1 now closed for the two named constants (objection 2).
- Order against 374 and 375: free (no shared file; 369 touches authn.py, 374 operator_health.py, 375 operator_auth.py); do the read-key-equals-internal-secret check in whichever of 369 and 374 lands second.

Not verified: CI, GX10.
