# Review PR 534 @ 2e1a7d6db9e71948e6b736a7aae9a59a6618f7ec (ops-console: refuse a bad FIELD_CONSOLE_MAX_STREAMS without echoing it, C-699) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 2e1a7d6d. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head rebased on current main still required.

## Objections first
1. Operator input echoed into an exception is the leak class this PR fixes; Python's implicit exception context is the usual way it comes back (the `raise ... from None` inside an `except` still keeps `__context__`). The helper raises OUTSIDE the `except`, and a test checks both `__cause__` and `__suppress_context__`; probed (M3, M4).
2. A parse failure mapped to a sentinel (`-1`) could instead map to the default (silent fallback) or to 0 (streams off). Probed (V3, V4).
3. The base of this head is `cd3b7690`, behind current main; this PR edits `docs/ENVIRONMENT.md` anchors, which main now checks in CI.

## Facts (HIGH)
- Head fetched via refs/pull/534/head = 2e1a7d6d; 1 commit; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; base cd3b7690 (not containing current main).
- 3 files, +56 -5: `ops_console/api.py` (`_max_streams_from_env`, one call site), `docs/ENVIRONMENT.md` (5 line anchors re-pointed), `tests/test_max_streams_env_c699.py` (+36).
- `python tools/environment_anchors.py --check` on the head: "0 wrong anchor row(s)"; and on a trial merge with current origin/main (merge clean): "0 wrong anchor row(s)" (ran both).
- Baselines unmutated: the whole ops-console suite 464 passed (about 4 minutes); mutants ran against the 2 files that mention max_streams (`test_max_streams_env_c699.py`, `test_console_features.py`) = 41 passed.

## Mutants (the 2 files each time; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| value rules: negative refused, 0 allowed, junk refused not defaulted, blank refused, default 8 (V1-V6) | 6 | 6 | 0 |
| message: no value, names the variable, no cause, no context (M1-M4) | 4 | 4 | 0 |
| create_app uses the helper, explicit `max_streams` (0 included) wins (C1, C2, C4) | 3 | 3 | 0 |
| helper still called when an explicit value is given (C3) | 1 | 0 | 1 (EQUIVALENT) |
Totals counted from the table: 6+4+3+1 = 14 rows; killed 13; survived 1; anchor failures 0.

## Survivor
- C3 EQUIVALENT: my edit only restructured the conditional (`(helper() if True else 0) if max_streams is None else max_streams`), which behaves like the original; it is not a "helper called anyway" mutant. A real one would break an explicit-value test (C2 does, and is killed).

## Findings
- F-R534-1 LOW: the ENVIRONMENT.md row for `FIELD_CONSOLE_MAX_STREAMS` still reads "non-integer raises ValueError at app start" and does not mention that a NEGATIVE value is refused too; the code does both (V1 kill).
- F-R534-2 LOW: `int()` accepts underscores and non-ASCII digits (general knowledge, MEDIUM); `1_0` would parse as 10. Not pinned either way.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main (anchors are checked there).
