# Review PR 626 @ d68bd2120cf42957b7fd9224c4761b4ebec4d114 (the head moved from 3ab9b3f0; delta review) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head d68bd212, the same conditions as my report on 3ab9b3f0 (review-pr626-3ab9b3f). UNVERIFIED (cloud, no GX10).

## What changed since 3ab9b3f0 (HIGH, measured)
- `git diff 3ab9b3f0 d68bd212 -- packages/` is EMPTY: `canary.py` and `tests/test_canary_main_args.py` are byte-identical to the head I mutated. The earlier mutant table (26 valid rows, 18 killed, 8 survived) therefore carries over; I did NOT re-run the mutants (not run again).
- New since then: a merge of current main, one allowlist line in `tools/tests/boundary_echo_allowlist.txt` (`packages/field-agent/src/field_agent/canary.py::main::cli = 1 | allow | operator terminal ... the setting NAME only`), and `docs/ENVIRONMENT.md` anchors refreshed. The diff against the old head also lists `tools/start_role_session.py` and its test: that is main's own content merged in, not this PR's.
- Head contains current main; author AND committer on all 4 commits: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- Ran on this head: `python tools/environment_anchors.py --check` = "0 wrong anchor row(s)"; boundary-echo lint 61 passed; field-agent suite 227 passed, 1 deselected (the same environment-baseline test that fails on main).

## Conditions (unchanged, still open)
1. Pin F-R626-1 (a non-numeric `FIELD_CANARY_HEARTBEAT_EVERY` turns into 0 = off instead of exit 2: mutant N3 survives) and F-R626-2 (port 65536 refused, 1 and 65535 accepted: P2, P5 survive) before this lands, or the coordinator rules them follow-ups.
2. GX10 16/16 and CI on this head.

## New LOW
- F-R626-6 LOW: the ENVIRONMENT.md rows for `FIELD_CANARY_PORT` (and the work and heartbeat rows) still say "non-integer raises ValueError at start"; the code now exits 2 with a one-line message naming the setting, and refuses out-of-range values. The anchors are right, the wording is stale.
