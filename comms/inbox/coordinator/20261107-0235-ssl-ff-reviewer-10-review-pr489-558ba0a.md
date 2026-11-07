# Review PR #489 (lifecycle-manager: an unreadable timestamp no longer aborts the sweep; conditions applied) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on the head named in the card, `558ba0ac50bd33fe1674deef37a2532839a12087`: it still conflicts with main (C1 of ssl-ff-reviewer-8 unmet at that SHA).
**VERDICT: PASS** on the PR's current head `a447c4450a38ad140b1e1148b23e2720c2bd7fac` (558ba0ac plus a merge of main that applies C1). Reviewer 8's C1, C2 and U1 are all met there. Use the second line; the first is for the record.

## Facts (HIGH, read from the heads)
- 5 commits on merge base `41afda50`; all authored and committed by `Don Hagell <13129187+dhagell@users.noreply.github.com>`. a447c445 is a merge commit. Nothing under `.github/`.
- 3-dot diff vs main at a447c445: 3 files (engine.py +52/-4, cli.py +1/-1, test_sweep_unparseable_ts.py +214 new). At 558ba0ac: same 3 files, engine.py has the extra `_skipped_id` helper.
- `git merge-tree --write-tree origin/main <head>`: 558ba0ac gives a content conflict in engine.py; a447c445 gives none.
- Code at a447c445: `_parse_ts_or_none` (TypeError, ValueError, AttributeError); a token with unreadable `expires_at` and an agent with unreadable `attested_at`/`created_at` are skipped and listed in `SweepReport.unreadable_timestamps` (kind, record id, field name, never the value); each is a finding: exit 3 (cli.py) and one `lifecycle.unreadable_timestamp` ledger event per record (agent subject only for agent records); markdown section uses main's `_inline`, `_skipped_id` removed. A revoked token is skipped before its timestamp is read.

## Prior conditions (ssl-ff-reviewer-8, R-PR489-1e8f7fe)
- C1 (rebase, one helper): met at a447c445 only.
- C2 (a skip is a finding: exit 3 plus escalation): met at both heads; pinned by tests, mutants below.
- U1 (non-string timestamps): met; int, None, list, dict and bytes are pinned.

## Verification (run by me, Windows 10, Python 3.14, at each head)
- test_sweep_unparseable_ts.py: 30 passed at 558ba0ac; 31 at a447c445 (the merge adds one).
- Whole lifecycle-manager suite at a447c445: 453 passed, 5 failed. All 5 are `test_cli_clients_no_proxy_c575.py::test_an_ambient_proxy_gets_no_connection_from_the_cli_client[...]` (a closed loopback port gives ConnectTimeout, not ConnectError, on this Windows host); the file and the client code are untouched by the PR. Baseline class, not PR defects (I did not re-run main for them: MEDIUM).
- Hand mutants (mine, 15, at a447c445, one at a time against the new file; restored, tree clean). Counted from the output: 13 RED, 2 survived.
  - RED: TypeError arm; ValueError arm; AttributeError arm; exit code ignoring the list; no escalation; unreadable token not skipped; token not named; agent not named; list not put in the report; markdown section always shown; raw id instead of `_inline`; the value echoed in `field`; `created_at` fallback lost.
  - Survived: (a) the escalation's agent subject also set for a token record; (b) the `revoked` check moved after the timestamp read.

## Reading the survivors
- (b) LOW-MEDIUM: nothing pins that a REVOKED token with garbage `expires_at` is ignored; moving the check would add a false "unreadable" finding (exit 3, escalation) for dead tokens. Optional test.
- (a) LOW: the subject passed for a token record is only metadata on the ledger event.

## Conditions
None on a447c445. On 558ba0ac: the rebase (done in a447c445).

## Optional (LOW)
1. Pin the revoked-token case (survivor b).
2. README row for exit code 3 was not updated (builder says so; docs not in the conditions).

## Not covered
CI and GX10 on a447c445 (the verifier's 16 of 16 was on the older head `53c30a02`); Linux; the full-suite failures on main.
