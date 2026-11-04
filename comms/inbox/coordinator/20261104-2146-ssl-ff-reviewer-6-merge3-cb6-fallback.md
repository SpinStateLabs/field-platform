# Reviewer report (fallback, read-only): MERGE 3 (batch cb6: PRs 317, 331, 332, 333, 337, 338; 18 commits) on current main ebb027a2

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Fallback of the role loop: `dispatch.sh next reviewer` is still EMPTY (restock-needed-3 filed; re-checked after the MERGE 2 report). Nothing was pushed; I changed no repository file. Author and committer of the 18 commits: Don Hagell noreply (HIGH for the 18 as listed by `git log --format='%h %an|%cn' 7de2a064..6a37ae76`: every line is "Don Hagell|Don Hagell"; I did not check the email field of each).

Scope (code only; the docs and README commits were not mutated, see "Not reviewed"):
1. sealed-ledger `anchors.py`: strict `AnchorRecord`, `parse_anchors` (BOM, "\n" only), ordering, `min_anchors` floor, position-0 rule (C-573, C-647, C-721).
2. attestation-reporter `engine.conformance_percent`: exact half-up rounding and the input contract (C-138, C-555).
3. claude-approver `core.py`: the events cursor is bounded above by the clock and stored normalised (C-570, C-720).

## Verdict: PASS (merged code and tests on ebb027a2). Retrospective: no merge condition.

## Objections first (FORCE-O)
1. The `min_anchors` floor is the guard against deleting the newest anchors, and it can only count what it can verify: it needs the public key (V3 killed) and counts signature-verified positions only; position 0 counts only with the genesis hash (V10, V11 killed). Its stated limit is the one in the docstring: "the guarantee depends on this file being the complete, off-box copy". If the attacker also controls the file and the caller passes a small floor, nothing detects the removal. Design limit, not a defect (HIGH, from the docstring).
2. Two mutants in `verify_anchors` are equivalent and I say so: V12 (position 0 counted even without a key) and V18 (every position counted without a key) change `counted`, but `counted` is only read when `min_anchors` is set, and `min_anchors` without a key is refused earlier (V3). They cannot change a result.
3. Three branches of `verify_anchors` survive the merge's own anchors tests (test_anchors_c573.py, test_load_anchors_c468.py, test_verify_anchors_fail_closed_c192.py: 70 tests): "chain shrank" (V14), "position is in an archived segment" (V15) and "position missing from the live chain" (V16). Each is killed by the whole sealed-ledger suite (the rotation and segment tests), so they are pinned, but not by the anchors files that name them (LOW).
4. `cursor_future_ignored` counts every future-dated event, but the warning is logged once per streak of exactly 10 (`==`); A7 (`>=`, so every value after the tenth logs) is killed, so the "once per streak" claim is tested. A host clock more than one minute BEHIND the API's re-reads (fails safe, reported), per the comment (HIGH, stated in the code).
5. The conformance rate is now a float rounded half up from `Decimal`; the value stays a float in the pack, so a consumer that formats it with Python's own `round` or `%.1f` can still print 6.2 for 6.25 (not checked; the pack note says "rounded half up to one decimal"; LOW).
Steelman: three real defects were closed with tests first: a 6.25 rate printed as 6.2 (half-to-even on a float), anchors accepted as strings, floats or bools and read by two different parsers, and a single far-future `processed_at` that became the cursor and hid every later event.

## Runs on main ebb027a2 (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- anchors: test_anchors_c573.py 46 passed; with the two sibling anchors files 70 passed. test_conformance_rate_c138.py: 42 passed. test_approver_cursor_bound_c570.py: 33 passed. For V14 to V16 I ran the whole sealed-ledger suite with `-x` (each stopped at the first failure: V14 after 681 passed in 120 s, V15 after 290, V16 after 349).

## Mutants (kill = the merge's own test file; anchors baseline 46 in c573 and 70 in the three)
| group | ids | result |
|---|---|---|
| anchors parser and record | P1 BOM kept, P2 `splitlines`, P3 blank lines not skipped, P4 lax int, P5 negative allowed | all 5 KILLED by test_anchors_c573.py |
| anchors verify | V1 empty file, V2 floor of 0, V3 floor without key, V4 repeat as out of order, V5 order check removed, V6 same position other hash, V7 `previous` not updated, V8 unsigned with key, V9 signature not verified, V10 genesis at 0, V11 position 0 never counted, V13 shrink `<=`, V19 floor `<=`, V20 distinct count, V21 floor not enforced, V22 signature count, V23 floor counts anchors | 17 KILLED by test_anchors_c573.py |
| | V17 hash mismatch not refused | KILLED by the sibling files (c468/c192), not by c573 |
| | V14 shrink check removed, V15 archived branch removed, V16 missing branch removed | SURVIVED the three anchors files; each KILLED by the whole sealed-ledger suite |
| | V12 position 0 counted without key, V18 floor counts without key | SURVIVED: equivalent (objection 2) |
| conformance_percent | C1 half-even, C2 precision 4, C3 two decimals, C4 float `round`, C5 bool accepted, C6 non-int accepted, C7 negative allowed, C8 allows>total allowed, C9 zero total, C10 allows==total refused, C11 note dropped, C12 call site back to `round` | all 12 KILLED |
| cursor bound | A1 bound removed, A2 slack 5 min, A3 slack 0, A4 not counted, A5 streak not incremented, A6 warn after 11, A7 warn `>=`, A8 streak not reset, A9 raw spelling stored, A10 string stored as datetime, A11 unusable not counted, A12 unusable raises, A13 `later` check removed, A14 unusable not skipped | all 14 KILLED |
Totals counted from the table: 54 mutants; 48 killed by the merge's own test file for that group (5 + 17 + 12 + 14), 1 by sibling files (V17), 3 by the whole suite (V14, V15, V16), 2 equivalent (V12, V18); no real survivor.

## Not reviewed
The docs and README commits of the batch (ARCHITECTURE.md, IMPLEMENTATION.md, the crosswalk and attestation-reporter READMEs, the crosswalk wording in mapping.py with test_declaration_only_wording_c558.py, topology_lint's cite by name): I did not cite-check them in this fallback.
