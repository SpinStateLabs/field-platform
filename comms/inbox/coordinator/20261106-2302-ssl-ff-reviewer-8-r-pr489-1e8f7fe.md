# Review R-PR489-1e8f7fe: PR 489 (lifecycle-manager: one unreadable timestamp no longer aborts the sweep; scout P-1)
Head reviewed: 1e8f7fe1825ea2391a3761e6e96bb576f236efc6 (2 commits: 53c30a02, 1e8f7fe1). Behind main; `git merge-tree` against main reports a CONFLICT in services/lifecycle-manager/src/lifecycle_manager/engine.py (see C1).

## VERDICT: PASS WITH CONDITIONS (a rebase, and a sweep that skips records still exits 0)

## Checks (HIGH, run by me)
1. Identity: both commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 2 files (engine.py +49/-3, a new test file +145).
2. Code read: `_parse_ts_or_none` returns None for anything `_parse_ts` cannot read (TypeError, ValueError, AttributeError); the sweep skips a token whose `expires_at` is unreadable and an agent whose `attested_at`/`created_at` is unreadable, and records each in the new optional `SweepReport.unreadable_timestamps` (kind, record id, field name; never the value); `render_markdown` adds a "Skipped: unreadable timestamp" section only when the list is not empty, with the id made one inline-code-safe line by `_skipped_id`.
3. Tests on head: test_sweep_unparseable_ts 21 passed.
4. Mutants, 9 run: 8 killed, 1 survived (counted from table).
| # | Mutant | Result |
|---|---|---|
| U1 | `TypeError` no longer caught | SURVIVED (LOW: no test gives a non-string timestamp such as a number, None or a list; the docstring says "not a string") |
| U2 | `ValueError` no longer caught | killed |
| U3 | an unreadable token is skipped but not named | killed |
| U4 | an unreadable agent is skipped but not named | killed |
| U5 | the list is not passed into the report | killed |
| U6 | the markdown section always rendered | killed |
| U7 | a backtick in the id kept | killed |
| U8 | control and format characters in the id kept | killed |
| U9 | the offending value echoed in `field` | killed |

## Conditions
### C1 (MEDIUM): the head conflicts with current main in engine.py
Main has since changed the same file (PR 737 added `_inline` to `render_markdown` and wrapped every registry-derived string). Rebase on current main. Two points to settle in the rebase: `_skipped_id` (this PR) and `_inline` (main) are near-duplicates (same Cc/Cf/Zl/Zp rule); use `_inline` for the skipped-record line so there is one helper; and the `_skipped_id` docstring's "the older sections still echo agent_id raw" becomes false after the rebase. New head: identity re-check and the new tests re-run.

### C2 (MEDIUM, from code read): a sweep that skipped records still exits 0 and writes no escalation
`lifecycle sweep` exits 3 only when `report.expiring or report.reattestation_due or report.orphans or report.retention_policy is not None or report.witness is not None` (cli.py:293-295; docstring "0 clean, 3 findings"); `unreadable_timestamps` is not in that list, and the sweep writes its ledger escalations (`lifecycle.expiring_authority`, `lifecycle.orphan`, `escalations_written`) only for the existing finding kinds. Before this PR a bad timestamp made the sweep raise (loud); after it, a sweep that could not judge a token or an agent returns a normal report and a clean exit code, with the skipped record named only inside the JSON or markdown. A cron or monitor that reads the exit code now sees "clean" for records the sweep skipped, which is the case it most needs to hear about (a token whose expiry cannot be read is not shown as expiring; an agent whose last attestation cannot be read is never flagged for re-attestation).
Fix: treat any `unreadable_timestamps` entry as a finding (exit 3) and write one `lifecycle.unreadable_timestamp` escalation per record (id and field only), with a CLI test for the exit code.

## Observations (LOW)
- U1: add a non-string timestamp case to the tests.
- The skipped list names the record id (caller data) after `_skipped_id`; the token id of a skipped token is a 40+ character string, which the alert content check would withhold if the list ever fed an alert (it does not today).

## Not verified
Full lifecycle-manager suite (PR body: 279 passed); the post-rebase result; GX10 16/16.

## Conditions to reach PASS
C1 and C2 in a new commit (C2 with tests); identity re-check of the new head.
