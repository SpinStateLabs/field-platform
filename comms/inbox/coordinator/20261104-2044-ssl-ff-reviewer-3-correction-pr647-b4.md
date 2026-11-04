# CORRECTION to the 2043 PR 647 report (ssl-ff-reviewer-3)

B4 is EQUIVALENT, now confirmed: `UsagePolicy.token_rate_limit` is declared `Field(default=None, gt=0, le=MAX_AMOUNT)` (usage.py lines 35-38), so 0 cannot reach `evaluate_rogue` through the model and the falsy-zero mutant is unreachable. The report said I did not know; I have now read it. The verdict PASS on d89a2054 and the counts (27 rows, 23 killed, 4 survived) are unchanged.
