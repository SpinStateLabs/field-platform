# builder-5: S6-12 built, draft PR 714

PR: https://github.com/SpinStateLabs/field-platform/pull/714 (draft, one commit, identity checked).
Fix: _sweep_rows counts a non-str token_id/agent_id as missing instead of hashing it; non-dict payload tolerated. 7 tests incl. GET /pack 200; mutant fails 7/7.
Verified: attestation-reporter 262 passed; env-doc lints 98 passed. Non-dict payload itself only covered by the guard.
