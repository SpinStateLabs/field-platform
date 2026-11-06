VERDICT: PASS on a628fbbefc1e4e25908e60e348d6a9a936018611  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for the Lane O PASS WITH CONDITIONS on f0c3d170. The Lane O condition C2 (the positive/negative asymmetry) is met by recording it as design and pinning it; C1 (CI and GX10) is the standing gate. Financial display code: every figure below was run.

R-PR506-a628fbb, PR 506 (scout P-5: field-core units_to_usd_str shows every unit below one cent). Applies to this head only. The fetched pull/506/head is a628fbbe; the condition-fix commit changes a comment and adds tests only (git diff f0c3d170..head: pricing.py comment lines, the test file +16).

OBJECTIONS FIRST
1. Zero-error tolerance on money: I did not rely on the PR's tests. I compared units_to_usd_str on the head with an independent Decimal reference over 2,950,150 amounts (every integer from -250,000 to 2,499,999, 200,000 random integers within +/-10^15, and the values 10^k-1, 10^k, 10^k+1 and their negatives for k up to 24): 0 mismatches. The reference is the PR's stated rule: one cent or more is floored to whole cents ("$0.19" for 1,999,999 units); below one cent, every unit, trailing zeros trimmed; a negative amount of any size keeps every unit. HIGH (measured).
2. Mutant U2 (the one-cent boundary moved to two cents, so 100,000 to 199,999 units, one to two cents, would print every unit, e.g. "$0.0199999" instead of "$0.01") SURVIVES the PR's file (23 passed) and the existing test_pricing files (55 passed): no test sends an amount strictly between one and two cents. That is the display boundary the whole change is about. MEDIUM-LOW (a test gap; the code is correct, checked above). Related: U12 (the sub-cent fraction computed through a float) also survives; it matters only above float precision, far beyond any real spend. LOW.
3. The asymmetry (Lane O objection 1) is recorded, not removed: -1,999,999 units prints "$-0.1999999" (every unit) while +1,999,999 prints "$0.19"; -10,000,001 prints "$-1.0000001" while +10,000,001 prints "$1.00". The builder says a negative amount is a difference or credit that is only displayed, and asks Don whether to floor it with a "-$0.20" shape. Still a decision for Don; the comment now says so and six cases pin both signs. Note for him: a display of a credit and a charge of the same size can differ in precision on the same page. LOW. HIGH on the behaviour.
4. docs/agent-estate.md (line 47) says "Costs are shown in whole cents, floored (the governor's `units_to_usd_str`)". After this change that is true only from one cent up; below one cent every unit is shown (e.g. 99,999 units prints "$0.0099999"). The PR does not touch the doc. LOW.
5. `units_to_usd_str(True)` prints "$0.0000001" (a bool is an int); a float raises ValueError and None or a string raises TypeError (measured). The callers (spend-governor api.py lines 262 and 584) pass integers. LOW.
6. The base is cd3b7690, 67 commits behind main; `git merge-tree --write-tree origin/main <head>` is clean (tree id only). HIGH.

ASSUMPTIONS
A1 "One unit = 1e-7 USD, one cent = 100,000 units" are the module's constants (USD_UNITS 10,000,000, CENT_UNITS 100,000), read and printed on the head. A2 The only consumer is spend-governor's two display fields (grep over the head: api.py lines 262 and 584; no other caller, no parser of the string).

REASONING / CHECKS
1. Diff read in full: units_to_usd_str, >= one cent: `f"${whole}.{frac // (USD_UNITS // 100):02d}"` (floored cents); otherwise integer `divmod(abs(units), USD_UNITS)`, seven zero-padded digits, `rstrip("0").rstrip(".")`, sign from units < 0. Nothing under .github/. HIGH.
2. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Cross-check with the sibling helper: for every positive amount of one cent or more the display's cents equal units_to_cents (0 disagreements over every seventh integer from 0 to 3,000,000 units, the amounts of one cent or more among them). Examples printed: 0 -> "$0"; 1 -> "$0.0000001"; 99,999 -> "$0.0099999"; 100,000 -> "$0.01"; 199,999 -> "$0.01"; 10,000,001 -> "$1.00"; -99,999 -> "$-0.0099999"; -30,000,000 -> "$-3". HIGH.
4. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, field-core src): test_units_to_usd_str + test_pricing + test_pricing_55_generation 55 passed, 0 failed; the spend-governor test file that checks the display fields (test_usage.py) 9 passed. I did not run the whole field-core or spend-governor suites (the PR reports 1562 and 291). HIGH.
5. Mutants on a copy of the head, units_to_usd_str only, the new test file (-x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| U1 | boundary `>` instead of `>=` | SURVIVED (equivalent: exactly one cent prints "$0.01" on both branches) |
| U2 | boundary at two cents | SURVIVED (objection 2; also survives test_pricing*) |
| U3 | positives rounded, not floored | KILLED |
| U4 | positives show every unit | KILLED |
| U5 | negatives floored too | KILLED |
| U6 | sign dropped | KILLED |
| U7 | sign always shown | KILLED |
| U8 | six digits | KILLED |
| U9 | eight digits | KILLED |
| U10 | no trailing-zero strip | KILLED |
| U11 | zeros stripped, the dot kept | KILLED |
| U12 | sub-cent fraction through a float | SURVIVED (objection 2) |
| U13 | fraction not zero padded | KILLED |
| U14 | negative whole part off by one | KILLED |
| U15 | cents divisor 1000 | KILLED |
| U16 | zero prints "$0.00" | KILLED |

Counted from the table: 16 run, 13 KILLED, 3 SURVIVED (U1 equivalent, U2 and U12 real gaps), 0 NOT APPLIED. Lane O's 23-row table is not repeated; the two rows the builder added (negatives floored too, positives exact too) are U5 and U4 and are killed. HIGH on the counts.

CONDITIONS
C1 (standing gate) GX10 16/16 and CI on this exact head rebased on main, including the field-core and spend-governor suites; not run by me. After this PASS the head is frozen.
C2 (new PR, optional) add 100,001 and 150,000 and 199,999 (each "$0.01") so U2 dies; add one amount above float precision so U12 dies; update docs/agent-estate.md line 47 ("floored from one cent up; below one cent every unit"); decide whether a bool is refused.
C3 (decision for Don, already carried by the builder) the format of a negative amount of one cent or more.

NOT VERIFIED
GX10 / Linux, CI, the full field-core and spend-governor suites on this head, any other consumer outside the repository.

CONCLUSION
The arithmetic is right: 0 mismatches against an independent Decimal reference over 2.95 million amounts, positives agree with units_to_cents, identity correct, merge clean, the Lane O asymmetry condition is met by a recorded design and six pinned cases. Two test gaps remain (the one-to-two-cent boundary and float precision) and a doc line is now inexact. PASS on a628fbbe; the GX10 gate and Don's negative-format decision stay open.
