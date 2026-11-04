# Reviewer ssl-ff-reviewer-6: MERGE 15 (PR 431, main 1d11c5e7 -> 05942b98, the no-echo 422 handler in eight services) — read-only mutant review, UNVERIFIED (cloud, no GX10)

**VERDICT (retrospective, read-only): PASS; nothing here calls for a revert.** Every one of 18 mutants that removes or disables the handler install in a service is killed by that service's own test. Seven mutants of the handler's text survive; none lets caller text back out (below). Reviewed at 05942b98, which is an ancestor of current main 97dcfec1 (HIGH, `merge-base --is-ancestor`). Fallback claim note: inbox/coordinator 20261104-1303-ssl-ff-reviewer-6-claim-merge15.md.

## Objections first
1. The central guard is a text scan (stated in its own docstring): `tools/tests/test_422_handler_installed_c1114.py` passes when the call text sits in a comment. Measured: commenting the call out in all 9 services is NOT caught by the guard (9 of 9 survive the guard alone); only the per-service request tests catch it. The protection therefore rests on those 9 per-service files plus the crosswalk one, not on the guard.
2. Three services are in the guard's NOT_YET list with "not measured" (attestation-reporter, claude-approver, kill-switch) and two keep their own handlers (agent-registry, federation-broker). On current main, kill-switch now installs the helper; I found no install in attestation-reporter or claude-approver (grep of services/*/src on origin/main). Their 422 replies were never sent a probe by this merge; I did not probe them either. Unknown.
3. Lane A's C-1141 audit checked counts only (per the task text); this review is the behavioural one.

## Identity (HIGH)
All 29 commits in 1d11c5e7..05942b98 (13 on the PR plus merges of main and the commits those bring): author and committer Don Hagell 13129187+dhagell@users.noreply.github.com.

## Method
Scratch worktree at 05942b98; PYTHONPATH from the worktree (field-core, field-agent, every service src); PYTHONDONTWRITEBYTECODE=1. Unmutated baselines: field-core test_http_errors_c1018.py plus the `-k` 19 tests pass; each service's no-echo test file passes (conformance-sentinel 3, delegation-authority 5, force-gateway 1, incident-replay 6, lifecycle-manager 3, ops-console 9, sealed-ledger 6, spend-governor 6, crosswalk 9); guard file 16 passed. Kill = the named test file fails (`-x`); each handler survivor was run against the whole field-core suite.

## Table
Service installs (9 services x 2: the call replaced by `pass`, and the call commented out): 18 mutants; 18 killed by the per-service test; guard alone killed 9 (the `pass` variants) and missed 9 (the comment variants).
Handler text (H1-H18): H3, H4, H5, H6, H8, H9, H10, H12, H13, H16, H17 killed by test_http_errors_c1018.py (11). Survivors against the whole field-core suite (7): 
- H1 (the `extra_forbidden` last-loc redaction removed): redundant, an unknown field name is already redacted by the `known` filter; leaks only a name that equals a declared field name, which the docstring says stays.
- H2 (the `value_error` branch dropped): the message becomes "Invalid value" instead of "Value error"; no leak.
- H7 (`body` dropped from the loc roots): "body" is replaced by "(field)" in every body error; usefulness loss, no leak.
- H11 (validation_alias ignored): a field reachable only through its validation alias would show as "(field)"; no leak.
- H14, H15, H18 (the texts of UNLISTED_KIND_MESSAGE, VALUE_ERROR_MESSAGE, REDACTED_NAME changed): the constants are imported by the tests, so their values are unpinned; no leak.
Totals: 36 mutants; 29 killed (18 service + 11 handler); 7 survived (all handler text), none of which echoes input.

## Findings
- F1 LOW: module docstring of field_core/http_errors.py line 11 still says "Only the crosswalk service installs this so far; the other services still use FastAPI's default reply" on current main (grep): false since this merge. Fix in a docs follow-up.
- F2 LOW: pin `body` kept in loc (H7) and the three message constants' values; optional.
- F3 MEDIUM-LOW: make the guard parse the call (ast) instead of substring so a commented call fails it; today only the per-service files stop that regression.
- F4: probe the three NOT_YET "not measured" services (attestation-reporter, claude-approver, and kill-switch after PR 476) with a request that gives a 422.

No state of main, STATUS, TASK-QUEUE or any PR was changed by this review.
