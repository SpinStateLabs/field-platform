# builder-5: S8-20 built, draft PR 780

PR: https://github.com/SpinStateLabs/field-platform/pull/780 (draft, one commit, identity checked).
Fix: build() keeps a per-build ContextVar memory of upstream clients that failed with no answer; later fetches to them return the same unavailable tuple (same query text and note) without calling. HTTP statuses never trip it. 9 tests; mutant fails 6/9 (the 3 status cases pass either way by design).
DECISION FOR DON (from the card): a degraded pack issues fewer upstream queries; one early transient error makes that upstream's remaining figures unavailable for that pack. No overall deadline added.
Verified: attestation-reporter 264 passed; env-doc lints pass. Not measured against a real timeout.
