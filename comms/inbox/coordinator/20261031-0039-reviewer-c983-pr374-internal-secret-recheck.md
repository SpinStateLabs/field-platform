VERDICT: PASS WITH CONDITIONS on b97d35fc70479b6089f579eceea8973967f52274

Reviewer Lane 15, cloud-reviewer, C-983, PR 374 at b97d35f, the head of my C-896 (re-fetched: unchanged). UNVERIFIED: no GX10, CI not read; made-up secrets only, none printed.

## Objections first
1. Premise: no head newer than C-896's exists; this re-checks C-896 against the card's three questions (HIGH).
2. The internal secret is dormant: no client sends it today; the routes need it only once FIELD_INTERNAL_SECRET or its hash is set (C-849 F-C849-2, carried). Until a wiring card exists and Don rules, the PR changes nothing on any estate (HIGH, read).

## C-849 conditions at this head
- F-C849-1 (the hash of the empty string let an absent or empty header pass): CLOSED two ways: `internal_request_allowed` returns false for an absent or empty header before hashing (operator_health.py, "if not presented"), and `internal_secret_problem` refuses that hash at install; mutants removing either are killed (C-896).
- F-C849-4 (pins): closed for the three survivors; one condition from C-896 C2 (pin the header name by value; refuse a secret too long for a header line; a runbook line that a bad value stops the service at start) remains open, non-blocking.
- F-C849-5 (an internal secret equal to FIELD_READ_KEY): OPEN. `internal_secret_problem` checks only equality with the perimeter secret (operator_health.py, :476-495); PR 369's read key is not in this tree and not checked. Whichever of 369 and 374 merges second should add the check (C-896 C1) (HIGH, read).

## Can the internal secret authorise any other route?
No by construction: `INTERNAL_HEADER` is read in exactly two handlers, `verify_hash` and `rotation_state_route` (operator_health.py:750 and :761), and both also require `internal_routes_enabled()`, which needs an armed operator layer and the perimeter secret; the perimeter middleware still demands x-field-auth for those paths. Nothing else in packages/ or services/ references the header or the helper. The secret equal to the perimeter secret is refused at install. A presented internal secret therefore opens only the two routes' extra check and cannot stand in for the perimeter key (HIGH, read).

## Merge order against 369 and 375
No conflict between any two of 374, 369 and 375 (merge-tree, each pair, and each with main: 0). 374 changes operator_health.py; 369 authn.py; 375 operator_auth.py. 369's INTERNAL_PATHS list repeats the two route constants (authn.py:41 against operator_health.py:431-433); 374 adds no route, so no drift (C-971). Order is free; do the equality-with-read-key check in whichever lands second.

Not verified: CI, GX10, any client that sends the secret (none exists).
