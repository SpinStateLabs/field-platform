# Reviewer Lane 6: idle, reports pushed, proposed new cards (the coordinator's session is not in my ListAgents; this is the message)

Lane 6 has no open reviewer card without a report except C-454, which waits for the C-453 PR. Reports pushed since my last status: C-446 (PR 288, PASS), C-450 second review (PR 291, PASS WITH CONDITIONS), C-452 (PR 293, PASS WITH CONDITION), C-463 = C-472 (PR 296, PASS), C-473 = C-464 (PR 297, PASS). Please mark C-472 DONE (same review as C-463); C-471 (= C-462) is Lane 7's.

## Proposed new cards (for the coordinator to number)
1. Builder, MEDIUM-LOW: PR 291 follow-up (my second C-450 review, F-C450-S1..S3): add `--build-constraint integration/build-constraints.txt` (hatchling and its dependencies, exact) to `$C` in ci.yml; widen `tools/tests/test_ci_pip_pins_c23.py` to every job and step and to `python -m pip install`, `pip3`, `uv pip`, `&&` chains, `--index-url`, `git+` (9 spellings and a new step or job pass the test today).
2. Builder, LOW: flaky `tools/tests/test_renew_token.py::test_a_failed_revoke_of_the_old_token_keeps_the_journal_and_the_next_run_finishes` (red once on `tests (3.12)` of the docs-only PR 297; 25 of 25 green in isolation on main): make `assert code == 1, out` check the revoke-failure reason so another exit 1 is named; find what exited 1 in that CI run.
3. Builder, LOW to MEDIUM: C-453 residue (my C-452 report): pin the `docker-rootless` socket with a path outside /run (a survivor); normalise the tail in the unresolved-head rule (`${A}//.ssh`, `${A}/../.ssh` pass today); and add a RESOLVED-value gate: apply the C-453 allowlist to the output of `docker compose config` at the deploy gate (`estate_probe` or `phase_g_check`), because the seven estate-driven bind variables cannot be seen by a static test.
4. Builder, LOW (optional): claude-approver cursor bound (my C-463 F-C463-1): ignore a `processed_at` far beyond now so one absurd but valid time cannot freeze a session's reads.
5. Don decision, trivial: 19 of 398 commits on main carry a `Claude-Session: https://claude.ai/code/session_...` trailer in a PUBLIC repository; keep or strip going forward (C-473 note N2).
6. Reviewer: C-454 as soon as the C-453 PR exists; Lane 6 will take it.

I poll the queue every 5 minutes (user instruction) and take the next reviewer card.
