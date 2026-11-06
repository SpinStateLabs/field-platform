# B-COND-PR751-c8d1d00: condition pushed on PR 751, new head 9f0816b0ae28

Closed the falsy-ref hole: only None and "" count as no manifest; 0, 0.0, False, [], {} are listed unresolvable/invalid (before, they were counted as without-manifest and the check said ok). Replaced the vacuous "str" assertion with the exact detail "registry returned a list holding int, str, not agent records". New tests: five falsy refs invalid, absent/null/empty-string still without-manifest, False never ok.
Mutants (6, by hand, against the shapes test file): falsy back to missing, only-None, non-str guard off, only first type named, types unsorted, odd check off: 6 of 6 killed.
Local, PYTHONUTF8=1: sealed-ledger retention tests pass (exit 0); the full sealed-ledger suite not run. Identity Don Hagell both fields. Open: CI, re-review. LOW left: agent_id passthrough of a non-JSON-scalar (reviewer objection 4), Z12 near-equivalent.
