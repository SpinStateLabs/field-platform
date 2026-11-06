# Review PR #846 (B-RT1: refuse look-alike ledger event types, F-H1-3) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `a43cc13ccf6eaa1bbf35b84a74b4ba438274b02c`.

## Facts (HIGH, read from the head)
- 2 commits (5bfadbfd, a43cc13c); 6 files: field-core operator_auth.py (+17/-3), sealed-ledger api.py (+7/-1), new test_event_type_charset_rt1.py (+116), test_operator_health_g_sealed_ledger.py (+9/-1), docs/runbooks/ntfy-alerts.md (+2), docs/ENVIRONMENT.md (anchor line). Nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>` on both.
- The change: (1) `AppendRequest.event_type` takes `pattern=^[a-z0-9_.-]+$` (fixed 422, input not echoed); (2) a new `_sealed_prefix_form` (NFKC, zero-width and BOM characters removed, strip, lower) is used by `admit_ledger_event`, `reject_reserved_event_type` and `OperatorAuth.may_attribute` instead of `strip().lower()` when testing the sealed `operator.` prefix; acceptance still needs the exact type in SELF_REPORTABLE_EVENT_TYPES.

## Verification (run on the head, Windows 10, Python 3.14)
- field-core: 1,638 passed, 3 skipped.
- sealed-ledger: first run stopped at one ERROR in test_operator_observer_c6_serve.py, caused by my harness (a relative PYTHONPATH, which the test's `serve` subprocess inherits while running in a temp cwd; not the PR). Rerun of that file and every file after it with absolute paths: 200 passed. Files before it: 700 passed, 4 skipped. So the whole sealed-ledger suite is green on the head, including the two new and changed test files.
- `tools/environment_anchors.py --check`: 0 wrong anchors (FIELD_EXPORT_ROOT is at sealed_ledger/api.py:481 as the table now says).
- No legitimate emitter is broken by the charset: an AST scan of all non-test Python for event types passed to append, make_event and similar calls found 18 positional literals and every keyword literal conforming; the only dynamic types are `conformance.{decision}` and `federation.{decision}` with Decision in ALLOW, BLOCK, ESCALATE lower-cased (conform, and the PR tests the conformance one).
- Pydantic's pattern is Rust-regex: a trailing newline is refused (the test pins it); the test file's own `re.compile(EVENT_TYPE_PATTERN)` is Python `re`, where `$` accepts a trailing newline, so the test's local regex is weaker than the server's (harmless here).

## Mutants (mine, 19 hand mutants, one at a time, in a separate worktree, targets restored from backup, tree clean). Counted from the output:
- RED 14: pattern removed; underscore dropped; dot dropped; upper case allowed; end anchor removed; start anchor removed; NFKC removed; invisible-character table not applied; lower() removed; BOM or U+200B removed from the table; may_attribute reverted; admit_ledger_event reverted; the exact self-reportable check dropped.
- SURVIVED 5: hyphen dropped from the charset (no event type uses a hyphen, so the hyphen is an unneeded allowance, harmless); `strip()` removed (admit and may_attribute tests have no leading-whitespace case); U+2060 and U+00AD removed from the invisible table (untested entries); `reject_reserved_event_type` reverted to the old test (a deprecated function with no new test).

## Finding status
- Reviewer-8's F-H1-3: the look-alike half is closed at two layers (the 422 at the edge, the normalised prefix test in the policy). The `keyrotation.*` half is deliberately NOT done and the runbook says so (accepted from any shared-secret caller until the PR 57 rework, C-496); `test_keyrotation_prefix_is_accepted_today_and_documented` pins today's behaviour. That is honest, and it remains open.
- Confusables are not mapped: a Cyrillic "o" in `operator.` passes `_sealed_prefix_form`, so the policy alone would not refuse it; only the charset (outside a-z0-9) does. Defence in depth holds today because every ledger write path I found goes through `AppendRequest`; an in-process append that bypasses the model is not covered (the observer's own appends use exact names).

## Conditions
None.

## Optional LOWs (new PR only; head is frozen after this PASS)
1. Add test cases for a leading space or NBSP, U+2060 and U+00AD in `admit_ledger_event`, and one for `reject_reserved_event_type` (survivors above), or remove the deprecated function's change.
2. Scan positional `append(...)` event types too: `_literal_event_types` only reads `event_type=` keywords, so the "every literal passes" guard misses the 18 positional emitters (they conform today).
3. The charset change is a client-visible 422 for any previously accepted type with upper case, space or non-ASCII; the note sits in the ntfy runbook; the sealed-ledger README is the natural home.

## Not covered
Did not run the other services' suites against the new charset (the scan above stands in); Linux behaviour; any estate; did not rebase on current main.
