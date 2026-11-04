# builder-5: S6-2 built, draft PR 709

PR: https://github.com/SpinStateLabs/field-platform/pull/709 (draft, one commit, identity checked).
Fix: sweep kill call goes through _try; failure sets auto_killed False and additive Orphan.kill_error (class or HTTP status). 4 tests; mutant fails 4/4.
Verified: lifecycle-manager 273 passed; env-doc lints 98 passed. Not covered: CLI exit-3 path end to end (follows from orphans non-empty).
