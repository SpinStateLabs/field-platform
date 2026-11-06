# B-COND-PR649-c0f5512: follow-ups pushed on PR 649, new head 7460666b8194

Tests only (no source change): an over-long domain and a lone surrogate refused first, middle or last (422, nothing halted); a legitimate non-ASCII list (Cyrillic, CJK) accepted and halted; the 128 cap counts characters (é*128 accepted, é*129 refused). 8 new tests, 16 in the file pass (PYTHONUTF8=1).
Mutants (6, by hand): length check first-only, last-only, in UTF-8 bytes; encode ASCII-only, first-only, last-only: 6 of 6 killed (reviewer's U2, U3, U5, U6, E2). The redundant try/except (U4, equivalent) left as is; dropping it is optional and I did not touch source. Identity Don Hagell both fields. Open: CI, re-review.
