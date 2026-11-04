S6-20 gateway env resolvers. PR #720 (draft). 58 tests, 9 mutants killed, suite 506 pass, lints pass (anchors fixed 11).
Card corrected: inf timeout does NOT 500 /health (null) - real defect is an infinite httpx timeout; the huge telemetry window IS a 500.
