# Delta review PR 606 (conformance-sentinel: upstream bodies of the wrong shape BLOCK with a named clause; S-2-22, HIGH CARE) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `c3af479bb747152497d485f3350a2c3666422269` (not a draft). It is reviewer-9's d320e840 plus a merge of main ff06b3398 that keeps both imports (`logging`, `math`): reviewer-9's C1 (conflict in engine.py) is CLOSED. The open conditions are the ones already on the record.
Conditions: C1 (decision for Don, carried from reviewer-9's objection 2) upstream text is still copied into verdict reasons when it is a non-blank string, cut to 200 chars (governor `detail`, delegation `reason`); control characters (newline, ANSI, bidi) pass through intact per reviewer-9's measurement. Rule: copy it (as now) or replace with fixed texts (C-503 reading). C2 (LOW, new PR) a test for the cut of the inactive-token `status` (reviewer-9's survivor T2; I did not re-run it, unchanged code). C3 (standing gate) CI and GX10 on this head (GX10 verifier-4 ran at 9d6b163f and reported the tools suite failing there); not run by me.

Independence: I did not build or fix this PR (5 commits, none mine; builder-6 and builder-8 pushed per their notes).

## Checks (HIGH, run by me)
- Identity: 5 of 5 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: the head is 7 commits BEHIND current origin/main ccd013d4f, but `git merge-tree` against it is clean (tree id only). Diff vs main: engine.py +93, test_judge.py +20, test_upstream_body_shapes.py +337 (3 files, +439/-11).
- Imports (engine.py:14-21 region): `logging` and `math` both present. Delta from the passed head is the merge only.
- Scan of the added lines for IPv4, 40-hex, mailboxes, key prefixes: none (the only regex hits were `@pytest` decorators).
- Tests on the exact head (Windows, py3.14, from services/conformance-sentinel, all service src on the path): `test_upstream_body_shapes.py` 139 passed (1,470 s, the box is loaded); `test_judge.py -k budget_status` 6 passed. I did not run the whole sentinel suite.

## Mutants (6, one at a time, in a separate worktree, restored and verified clean; counted from the table)
| # | mutant (engine.py) | tests run | result |
|---|---|---|---|
| M1 | `_upstream_text` returns the string uncut | `-k "kept_and_cut or string_detail_is_kept_but_bounded"` | KILLED |
| M2 | a negative `spent_cents` accepted | `-k "unusable_totals or missing_spent"` | KILLED |
| M3 | `active` truthy instead of exactly `True` | `-k introspect_active` | KILLED |
| M4 | `_SPEND_STATES` loses "ESCALATE" | `-k "four_governor_states or without_a_known_state"` | KILLED |
| M5 | the not-an-object body check disabled | `-k "not_an_object or an_object"` | KILLED |
| M6 | `retry_after` accepts infinity | `-k retry_after` | KILLED |
Totals: 6 attempted, 6 killed, 0 survived, 0 not applied. Each mutant ran only the selected tests.

## Heads-up (HIGH on measurement)
PR 606 and PR 689 (both open) conflict with each other in engine.py: `git merge-tree` of the two heads gives CONFLICT (content) in `services/conformance-sentinel/src/conformance_sentinel/engine.py` (the import block: 689 adds `json` and `re`, 606 adds `math`). Whichever lands second needs a mechanical rebase keeping all four imports.

## Not verified
CI; GX10; Linux; the whole sentinel suite on this head; reviewer-9's T2 and probes (carried, code unchanged); any estate fact.
