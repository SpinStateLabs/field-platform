# Review PR 643 @ 138c28c2a2d1eda6f17da78b8ff8b044f5f120dd (force-gateway: GET /telemetry limit bounded 0..500; drop the unused _SECTION_RE, S3-21) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 138c28c2. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. This is an API behaviour change, not only a hardening: a negative `limit` used to be clamped to 0 (200 with no records) and a limit above 500 used to be accepted. Both now give 422. A script that sent either breaks. I searched the repository for callers that pass `limit` to `/telemetry` (grep over `.py`, `.html`, `.js`, `.sh`, `.yml`, tests excluded): none; the README documents `GET /telemetry[?limit=20]` only.
2. The 422 body must not repeat the value. The test checks the value's text is absent after removing the word `loc`; a limit like `-1` could appear inside other text (`"-1"` is weak); I measured nothing stronger.
3. Dropping `_SECTION_RE` is a deletion of unused code; a dangling use would be an import-time `NameError`.

## Facts (HIGH)
- Head fetched via refs/pull/643/head = 138c28c2; 1 commit; contains current main; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 3 files, +32 -9: `api.py` (`Query(default=20, ge=0, le=500)`, and `recent = store.records(limit=limit)` replacing `max(0, limit)`), `presets.py` (the unused regex removed), `tests/test_telemetry_limit_bound.py` (+29, 2 tests with 4 cases).
- `grep -rn _SECTION_RE` over services, packages and tools: no remaining use; `import re` in `presets.py` is still used (`re.search` at line 45), so no unused import is left.
- Baselines unmutated: new file 4 passed; whole force-gateway suite 452 passed.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| upper bound exactly 500: 501, 499, none, 5000, `lt` instead of `le` (B1-B4, B12) | 5 | 5 | 0 |
| lower bound exactly 0: -1 allowed, 1 minimum, none, `gt` instead of `ge` (B5-B7, B11) | 4 | 4 | 0 |
| default exactly 20 (B8, B9) and the old unbounded signature (B10) | 3 | 3 | 0 |
| `recent` uses the limit: ignores it, off by one, wrong window (R1-R3) | 3 | 3 | 0 |
Totals counted from the table: 5+4+3+3 = 15 rows; killed 15; survived 0; anchor failures 0.

## Findings
- F-R643-1 LOW: no changelog or README note of the behaviour change (422 for out-of-range values); the README line still reads `[?limit=20]` with no bounds. One docs line would tell scripts.
- F-R643-2 LOW: the no-echo assertion is weak for single-digit-like values; fine for 501 and 1000000.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head.
