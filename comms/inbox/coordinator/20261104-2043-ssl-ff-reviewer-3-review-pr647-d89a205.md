# Review PR 647 @ d89a2054c8892e16f1bb8094e7681961697c3372 (spend-governor tests: evaluate_rogue and window_action_rows pinned directly) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head d89a2054. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required. Tests only (no source edit; a three-dot diff shows one new file).

## Objections first
1. Two pure helpers decide a rogue-usage finding and which rows count toward a rate window (sentinel-metered rows win). A test that pins only the happy path would let a boundary (`>=`), the precedence, or the allow-list match drift. I attacked each.
2. The tests call the helpers directly with hand-built `UsagePolicy` objects; they cannot show the API wiring (covered elsewhere through the API, which the PR text says).
3. The detail strings are partly free text; pinning them freezes wording.

## Facts (HIGH)
- Head fetched via refs/pull/647/head = d89a2054; 1 commit; contains current main; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 1 file, +110: `services/spend-governor/tests/test_pure_policy_helpers.py` (17 tests).
- Baseline unmutated: 17 passed (relative `PYTHONPATH`).

## Mutants (the new file first; a survivor then the whole spend-governor suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| UNPRICED: fires when and only when unpriced, with or without a policy, detail names the model (U1-U5; U4 the wording of the instruction) | 5 | 4 | 1 (U4) |
| ROGUE_MODEL: enforced, empty list never flags, exact match (not case, prefix or stripped), detail names the model and the list (M1-M7) | 7 | 7 | 0 |
| ROGUE_BURST: `>=` boundary, fires only with a limit, detail holds the count (B1, B2, B3, B6); limit 0 as falsy (B4); window seconds in the detail (B5) | 6 | 4 | 2 (B4, B5) |
| the order of findings (O1) | 1 | 0 | 1 (EQUIVALENT: my edit inserted a no-op `if policy is not None: pass`) |
| `window_action_rows`: metered rows win, else self-reported, any non-sentinel source is self-reported, input order kept, generator accepted (W1-W8) | 8 | 8 | 0 |
Totals counted from the table: 5+7+6+1+8 = 27 rows; killed 4+7+4+0+8 = 23; survived 4 (U4, B4, B5, O1); anchor failures 0.

## Survivors (each also survives the whole suite)
- U4 LOW (cosmetic): the wording "price it or block the model" is unpinned; the "no price" part is.
- B4 EQUIVALENT: `token_rate_limit` is a validated field of `UsagePolicy`; I did not read its bound (`gt=0` or not) beyond the one-line signature; the falsy-zero case is only reachable if 0 is accepted. I do not know whether 0 is valid.
- F-R647-1 LOW (B5): the window seconds in the burst detail is pinned only at 60; my replacement with the literal "60" is invisible to a test whose window is 60. A second window value would pin it.
- O1 is a no-op of mine; the real ordering is pinned by `test_every_finding_at_once_comes_back_in_a_fixed_order` (a reordering mutant was not written).

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head.
