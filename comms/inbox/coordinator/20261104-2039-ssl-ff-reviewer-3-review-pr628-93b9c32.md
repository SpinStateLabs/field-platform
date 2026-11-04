# Review PR 628 @ 93b9c327040f1fb3f7ddeb7ada8b0d2db7844fdf (field-agent tests: heartbeat, checkin, report-usage and mint exit codes, S3-7) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 93b9c327. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required. Tests only.

## Objections first
1. Exit codes are the contract a script relies on (1 = killed or not metered, 3 = rogue findings). A test that checks only the code, not stream and content, would let a message move to stdout. Probed (H3, C5, M3).
2. The tests use a fake `FieldAgent`; the CLI could drift from the real client's exceptions. `mint` is the exception: it runs the real `bootstrap.mint` over a mock transport, and the PR's own docstring says so.
3. `check` and `cross` verbs are not in this PR (`check` has its own coverage elsewhere; not checked).

## Facts (HIGH)
- Head fetched via refs/pull/628/head = 93b9c327; 2 commits (the tests and a merge of current main); contains current main; author AND committer on both: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 1 file, +199: `packages/field-agent/tests/test_cli_verbs.py` (17 tests); no source change.
- Baseline unmutated: 17 passed (relative `PYTHONPATH`). The mutants were applied to `field_agent/cli.py` as it is.

## Mutants (the new file first; a survivor then the whole field-agent suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| heartbeat: killed exits 1, JSON then message on stderr, None guard, active prints JSON (H1-H5) | 5 | 5 | 0 |
| checkin: killed prints JSON then the halting line on stderr, exit 1; unreachable exit 1 (C1-C5) | 5 | 5 | 0 |
| report-usage: rogue exit 3 after the report, error exit 1 with the fixed text, defaults, option pass-through, model required (U1-U10) | 10 | 10 | 0 |
| mint: ttl default 3600, error exit 1 on stderr with a message, granted-by and scope required, every scope passed (M1-M7) | 7 | 7 | 0 |
Totals counted from the table: 5+5+10+7 = 27 rows; killed 27; survived 0; anchor failures 0.

## Findings
- F-R628-1 LOW: the verbs `check`, `cross` and `version` are outside this file; I did not look for their tests.
- F-R628-2 LOW: `test_negative_token_options_are_passed_through_not_refused` pins that negative token counts are passed on; that is a deliberate "pass-through" (the governor refuses them), but it also freezes the absence of a client-side check.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head.
