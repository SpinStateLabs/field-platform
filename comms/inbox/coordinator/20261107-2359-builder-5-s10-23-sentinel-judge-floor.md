# B-S10-23 report (builder-5)
Draft PR 949: resolve_floor treats negative, -inf, nan and junk as invalid (default floor, one warning without the value); empty/whitespace is unset; >1 stays the strict clamp. ENVIRONMENT.md pins repaired (3 rows).
Evidence: 2 new tests in test_judge.py, both fail on the unfixed code. Sentinel suite 372 passed; ENVIRONMENT.md lint tests 104 passed; anchors 0 wrong.
Decision for Don (MEDIUM): +inf is the strict clamp 1.0 here (card lists only -inf and nan); one-line change if non-finite should always mean the default. The card's optional /health effective-floor item is not built (needs Don).
