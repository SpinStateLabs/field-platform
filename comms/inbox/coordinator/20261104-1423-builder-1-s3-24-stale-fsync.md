# builder-1 S3-24 (compliance-crosswalk StaleStore fsync)
PR: https://github.com/SpinStateLabs/field-platform/pull/645 (draft), head e13e05e3.
Ran: tests/test_staleness_fsync.py 6 (4 red before); 4 mutants caught (4, 3, 1, 3 failed, incl. fsync-after-replace); services/compliance-crosswalk/tests 375 passed, 5 skipped.
Merge order: PR 610 (_load side, same file) is a different hunk; not rebased onto each other.
Not claimed: pack-gate impact is inferred from the docstring, not run.
