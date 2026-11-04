# builder-1 S3-1 (spend-governor mixed priced/unpriced)
PR: https://github.com/SpinStateLabs/field-platform/pull/621 (draft), head 3645f6b6.
Ran: new test file red 9/12 before fix, green after; mutant (revert sum) 9 failed; services/spend-governor/tests 303 passed.
Decision for Don: by_model shape for mixed models (priced portion, priced=False).
