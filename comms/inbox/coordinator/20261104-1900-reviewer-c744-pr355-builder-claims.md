VERDICT: PASS WITH CONDITIONS on 191affb8a9c89fa59506ec30029ce4b5c4857ca7 (UNVERIFIED: cloud reviewer; the builder's GX10 run on this head is not mine to confirm; my probes are cloud-side)

Same PR and head as my report 20261104-1430-reviewer-c702-pr355-format2-ambiguity-cap.md (head re-checked: unchanged). This card asks for the builder's Lane 13 report (20261030-1710-builder-lane13-c51.md) against the diff and for cap-1, cap, cap+1.

OBJECTIONS FIRST
1. The builder says each rule is tested; the card asks "at cap-1, cap, cap+1". The diff asserts the cap at exactly the cap (two retired, cap two: both kept) and over it (three retired, cap two: oldest evicted); the cap-1 case is absent. It cannot behave differently from the cap case (no eviction below the cap), so it is a coverage gap in form only. LOW.
2. The three ambiguity rules (duplicate id, alias equal to another row's id, alias "*") are each asserted once for format 2; they are not boundary-shaped, so "cap-1, cap, cap+1" does not apply to them. The builder's list matches the diff: three rules, two cap tests (builder report, "What the PR does").
3. The builder's open claim (a): "an evicted retired hash cannot be re-admitted by a stale file, because a file below the highest generation is already refused". I tested it. Cap 2, five generations, keys retired at generations 42-45, the two oldest evicted: an evicted key in a file at generation 43, 44 or 41 (below the highest, 45) is refused; an evicted key in a file AT the highest generation (45, different content) is accepted; at 46 it is accepted (legitimately newer). After a process restart memory is empty and a stale file at 41 holding the key is accepted (documented in the PR 351 runbook). So (a) holds for stale restores; the one open door is a different file at the SAME generation as the highest. LOW-MEDIUM, MEDIUM confidence (whether a same-generation different-content file is rejected by another rule was not checked).
4. The builder says mutation runs were local and the GX10 run was the unmutated suite (16 suites, 0 failures). I can confirm the six mutants it names are the same classes I ran (all red); I cannot confirm the GX10 numbers.

ASSUMPTIONS
A1 Builder report read in full; its numbers are its own. A2 My probes call load_registry on files built from the test helpers; keys are made-up strings.

REASONING
1. Claimed rules versus diff: duplicate id (asserted, red under mutant M1); alias equals another row's id (M2); alias "*" (M3); eviction keeps the oldest (M4); cap off by one (M5); format 2 parser skips validate_rows (M6, not run by me). My own mutant run (C-702): duplicate id, alias-equals-id, alias star, shared alias each red; cap raised by one red; keeps-fewer red; keeps-oldest red; no eviction red; the comparison > versus >= is equivalent (builder says the same). HIGH.
2. Builder's "Card conflicts" list: stale line numbers, generation-one test already on main, items not done: consistent with what I found (operator_auth.py:678-712, :1258-1261). HIGH.
3. Re-admission probe: as in objection 3. HIGH for the table; MEDIUM for the "same generation" implication.
4. Diff scan: no address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS (as C-702). The builder's report matches the diff; its unreachable-concern claim holds for stale restores and leaves one narrow case (same generation, different content). Conditions, none blocking: C1 add cap-1 for completeness; C2 pin or reject the same-generation different-content file; C3 the two items the builder says it did not read (rotation_events.py:168 and operator_health.py:695 boundaries) remain open.

FINDINGS
F-C744-1 LOW, tests/test_operator_auth_format2.py (no cap-1 case; cannot differ). HIGH.
F-C744-2 LOW-MEDIUM, packages/field-core/src/field_core/operator_auth.py:1258-1275 (retired memory does not cover a same-generation file with different content). PROVEN (an evicted key accepted at the highest generation).
F-C744-3 INFO, builder items not done: rotation_events.py:168 and operator_health.py:695. HIGH (from the report).

NOT VERIFIED: the builder's GX10 run; CI; whether another rule rejects equal-generation different-content files.
