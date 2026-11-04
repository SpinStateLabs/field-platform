# Review PR 555 @ 55cb95c1da422d732c453bc87187a58ba38e21f5 (spend-governor: a lone surrogate in free text is a 422, not a 500) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 55cb95c1. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. The claim is "the unbounded text fields were the only ones". If one more field is unbounded, the 500 remains. I probed the other text fields over the live app (below): every one answers 422 already.
2. A validator message that repeats the value would leak operator text. The docstring promises it never does; no test pins that (E3). I measured that the wire is safe anyway.
3. The fix runs in pydantic after-validators; a field typed `str` added later without `Utf8Str` repeats the bug, and nothing flags a new unbounded field.

## Facts (HIGH)
- Head fetched via refs/pull/555/head = 55cb95c1; 2 commits (the fix and a merge of main `b963407a`); contains current main; author AND committer on both: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 4 files, +90 -8: `core.py` (`_encodable`, `Utf8Str`, `currency`, `on_breach`), `api.py` (`note` on spend and usage), `usage.py` (`allowed_models` entries), and `tests/test_lone_surrogate_text_422.py` (+67, 6 tests).
- Baselines unmutated: new file 6 passed; whole spend-governor suite 297 passed.
- Completeness probe (my own script against the head, JSON lone surrogate `\ud800`, `raise_server_exceptions=False`): `agent_id` on spend, usage, caps body and policies body; `action`, `source` (a Literal), `model`, the rate-limit `action`, and `resolved_by` on resolve: all 422. So the five fields the PR guards are the unbounded ones I could find.
- The 422 body for the guarded `note` is `{"detail":[{"type":"value_error","loc":["body","note"],"msg":"Value error"}]}`: with the validator message deliberately made to echo the value (E3), the wire body is unchanged, because the platform's validation handler drops the message. So the echo is not reachable through the API (measured).

## Mutants (the new file first, any survivor then the whole suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| each of the five fields is guarded: spend note, usage note, currency, on_breach, allowed_models entries (N1-N5), and N6 the guard on the list rather than its entries | 6 | 6 | 0 |
| `_encodable` refuses a lone surrogate, accepts ordinary Unicode, raises ValueError (not 500), keeps the value (E1, E2, E4, E5) | 4 | 4 | 0 |
| `_encodable` returns the value unchanged (E6 uppercases it) | 1 | 1 by the whole suite, not by the new file | 0 |
| validator message never repeats the value (E3) | 1 | 0 | 1 (not reachable on the wire, measured) |
| only high surrogates refused (E7) | 1 | 0 | 1 (EQUIVALENT: my edit still ran the same `encode` call) |
Totals counted from the table: 6+4+1+1+1 = 13 rows; killed 6+4+1 = 11 (10 by the new file, 1 by the whole suite); survived 2 (E3, E7).

## Findings
- F-R555-1 LOW: E3 is unpinned in the unit test; the docstring promise holds on the wire only because the shared handler drops messages; a handler change would expose it. A one-line test on `_encodable`'s message would pin it.
- F-R555-2 LOW: E6 (the validator returning a changed value) is killed only outside the new file; add an assertion that an accepted value is stored as given.
- F-R555-3 LOW: a lone LOW surrogate (U+DC00) was not tested separately; E7 was invalid, so I did not measure it (I do not know).

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head.
