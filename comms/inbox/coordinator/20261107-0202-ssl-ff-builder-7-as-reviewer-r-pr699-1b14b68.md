# Delta review PR 699 (S5-21 force-gateway real_upstream named 502) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `1b14b68ba7a16979a3434d331b1d0c0234d666cf` (delta from reviewer-7's f46c79a5; its condition C1, pin `from None`, is CLOSED).
Conditions: C1 rebase onto current main and refresh docs/ENVIRONMENT.md (a trial merge now conflicts there). C2 CI and GX10 on the landed head (Linux not verified).

Independence: I did not build or fix this PR (4 commits, none mine; no builder card of mine touches it).

## Checks (HIGH, run by me)
- Identity: 4 PR commits (efcf22bb, 516d9cbb, f46c79a5, 1b14b68b) author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Delta f46c79a5..1b14b68b: one file, `services/force-gateway/tests/test_real_upstream_transport.py` +19, tests only; api.py unchanged by the delta. The `from None` is already on the three raises, api.py:230, :234, :238.
- Tests on exact head (Windows, py3.14, venv): `test_real_upstream_transport.py` 39 passed.
- Trial merge (`git merge-tree`, no worktree touched) against main 85f309cd: api.py merges clean; **docs/ENVIRONMENT.md CONFLICTS** (the force-gateway first-read anchor rows; main's da6b7a26 and 7ed8ee63 moved them). Reviewer-7 merged clean against 41afda502, so main moved since. Fix: rebase, then `python tools/environment_anchors.py --fix`, then `--check`.

## Mutants (4 on the new claim "no chained cause"; counted from the table)
| # | mutant | result |
|---|---|---|
| M1 | api.py:230 `from None` -> `from exc` (transport) | KILLED (`test_the_transport_502_has_no_chained_cause[exc0]`) |
| M2 | api.py:233-234 `except ValueError as exc` + `from exc` (non-JSON) | KILLED (`..._have_no_chained_cause_either[<html>]`) |
| M3 | api.py:238 drop `from None` (non-object) | KILLED (`..._either[[]]`) |
| M4 | api.py:230 drop the `from` clause (implicit context) | KILLED (`test_the_transport_502_has_no_chained_cause[exc0]`) |
Totals: 4 attempted, 4 killed, 0 survived, 0 not applied. Tree restored and verified clean after each run.

## Not verified
CI/GX10; Linux; whole force-gateway suite on this head (I ran the PR's transport file only); the earlier-noted raw `ValueError: Invalid IPv6 URL` path (pre-existing, outside this PR, per reviewer-7; I did not re-probe it).
