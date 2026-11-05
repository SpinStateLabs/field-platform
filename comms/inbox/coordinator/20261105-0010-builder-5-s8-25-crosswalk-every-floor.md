# builder-5: S8-25 built, draft PR 783

PR: https://github.com/SpinStateLabs/field-platform/pull/783 (draft, one commit, identity checked).
Fix: MIN_EVERY_SECONDS floor on crosswalk regwatch interval; create_app ValueError, `serve --every` exit 2 one-line; 0 and negative still off; ENVIRONMENT.md and README updated.
DEVIATIONS for Don: floor is 5 not the suggested 60 (README documents short soak intervals; sealed-ledger observer min is 5; one constant to change). Existing test test_regwatch every=2 changed to 5 (card's grep missed it).
Verified: compliance-crosswalk 384 passed; env-doc lints 98 passed. Mutant is coarse (import error without the source change).
