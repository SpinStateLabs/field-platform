# builder-5: S6-16 built, draft PR 725

PR: https://github.com/SpinStateLabs/field-platform/pull/725 (draft, one commit, identity checked).
Fix: UsageCursor.set fsyncs before replace, cleans its tmp file on failure, best-effort dir fsync (not Windows); bundle._write_text flush+fsync. 5 new tests; mutant fails 4 of 5.
Verified: claude-approver 319 passed; sealed-ledger 804 passed (1 relative-PYTHONPATH artifact passes with absolute path); env-doc lints 98 passed. Dir fsync untested (Windows).
