B-S2-14 -> draft PR (see title "force-gateway: hygiene heuristics count curly apostrophes (S2-14)").
HIGH: failing-first (3 failed), normalise U+2018/2019 on a copy; 19 new tests pass; gateway suite 427 pass (2 local-path module errors, test_f1_enforce uncollectable locally).
Decision: [E] comment fixed, regex not widened. METHOD_LABEL not bumped.
OVERLAP: PR 492 rewrites _CORRECTION (curly-aware); disjoint files, no conflict expected.
