# B-COND-PR652-95a7b13: condition pushed on PR 652, new head 27ed14c15a69

Test only: test_the_operator_and_reason_come_back_exactly_as_sent_padding_and_case_included sends padded, mixed-case values (tab, newlines, inner double space) to /kill and asserts the response carries them unchanged. Mutants of KillRequest._not_blank returning strip(), title() and lower(): 3 of 3 killed. The whole file passes locally, 73 tests (PYTHONUTF8=1, Windows).
The Cf (zero-width, bidi) question in the review is not a condition and I did not widen scope: heartbeat ids and operator/reason still refuse Cc only. A coordinator or architect decision; if wanted, a follow-up card (B-FU-PR652-cf-chars). Identity Don Hagell both fields. Open: CI, re-review.
