VERDICT: PASS WITH CONDITIONS on 4ff09c7b653aa30230cf0a965cc34c079a40d1a5 (finding C-958 objection 2 is REAL but already known to the PR's own tests as a "mutant")

Reviewer Lane 15, cloud-reviewer, C-1003. Verification on the current head (4ff09c7, unchanged). UNVERIFIED: no GX10, CI not read; synthetic registry files and a made-up key, scratch tree, nothing committed.

## Objections first
1. The behaviour is documented in the code and pinned by an existing test as the reason "the row must never hold it" (packages/field-core/tests/test_operator_auth_machine_verifier.py:241-246: a mutant test asserts that with bypass_operator_list the identity escapes the reach bound). So this is a deliberate non-enforcement, not an oversight: the shipped row is trusted not to hold the scope (operator_auth.py:609-611, comment). My finding is "nothing refuses it at load", which stays true (HIGH).
2. The smallest fix flips three existing tests, so it is a decision, not a drive-by: they encode the escape on purpose (HIGH, run).

## Does a prefixed row still reach the operator-list bypass?
Yes. Probe through the real loader and authenticate with a made-up key: a row with the exact `svc-verifier-` prefix, the verifier's scope set and `bypass_operator_list` LOADS (also with the scope alone). Authenticated: true; list_bound: true; list_bound_applies: FALSE (operator_auth.py:626-631, the exemption on :631). check_record_authorized (operator_auth.py:653) returns early on `has_scope("bypass_operator_list")` before the list-bound branch (:658), so the identity passes the per-agent authorized_operators check for ANY agent, including a manifest naming nobody; check_list_bound_reach is a no-op for it (HIGH, run).

## Impact
A machine verifier row that gains the scope (a file edit, or a template that includes it) reaches every agent's kill, revive, revoke and mint paths with no list check, which is the class P35 and D-18 exist to prevent. Preconditions: write access to the operators registry file (an attacker with that can already do more) or an honest mistake. The shipped row does not hold it (comment :609-611, not verified against the estate's real file). MEDIUM-LOW.

## Smallest fix (verified in a scratch tree, then discarded)
In `validate_rows` (operator_auth.py:695 onward), next to the C-805 verifier rule: refuse an ACTIVE row whose id starts with `svc-verifier-` and whose scopes include `bypass_operator_list` (about six lines, one message). Probe after the change: the prefixed row with the scope is refused as "ambiguous" (the registry is unavailable, fail closed); the prefixed row without it and a non-prefixed kill-switch identity with the scope both still load. Tests: field-core 1160 passed and 3 failed (the three tests that pin the escape, including the one above, and two siblings); delegation-authority 213 passed; the machine-verifier identity and job-grantor tool tests 39 passed. Those three tests would be rewritten to assert refusal.

## Builder card?
Only with Don's ruling that a verifier-prefixed row may never hold bypass_operator_list (the code comment already says "must not"). If ruled, the card is the six lines plus the three flipped tests.

Not verified: CI, GX10, the estate's real operators file.
