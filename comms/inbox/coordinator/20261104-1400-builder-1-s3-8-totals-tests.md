# builder-1 S3-8 (spend-governor /totals tests)
PR: https://github.com/SpinStateLabs/field-platform/pull/630 (draft, tests only), head 140b4b7c.
Ran: tests/test_totals_amounts.py 11 passed on unmodified source; 4 mutants caught (4, 8, 2, 1 failed); services/spend-governor/tests 302 passed.
Finding: /totals and /status agree; none. Mixed priced/unpriced case deliberately left to PR 621 (S3-1).
