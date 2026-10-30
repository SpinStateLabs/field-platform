# Builder Lane 1 status (bob): what is pushed, what is local, what I am doing, blockers

PUSHED (draft PRs, all UNVERIFIED on the GX10, no GX10 tool in this cloud session):
- PR 288 C-221 MERGED (batch BQ). PR 299 C-451 @f1184235 (redirect:error on guarded writes, route-enumeration test), ops-console 246 passed; ask: reviewer card.
- PR 295 C-57 @e39671e (three commits; C-462 findings and Lane 10 evasion review fixed; cards C-476 and the evasion part of C-486 are done in it); ask: delta review of the two commits after b47ee05.
- PR 291 C-23 @c13f2de (7/7 CI green; C-450 PASS WITH CONDITIONS), PR 297 C-44 @3bb2510 (C-473 PASS; one flaky CI job reported earlier).
LOCAL, being tested (not pushed yet):
- PR 295 branch, 4th commit 6dd592e (C-486 part 2): `PerRequestAuthClient` (lifecycle-manager) now pins `trust_env=False` in its constructor; two tests, 2 mutants red; lifecycle-manager suite 227 passed; lint allowlist back to 58 keys / 63 sites. Whole tools suite running.
- PR 291 branch, 2nd commit c3dd32f (cards C-459 and C-460): `integration/build-constraints.txt` (hatchling, editables and their closure; the probe showed `editables` was also unpinned) and `--build-constraint` in `$C`; the pin test now scans every run of every job of every workflow, 34 tests, 28 checker mutants red (one equivalent survivor: `uv pip` is caught by the `pip install` match). The CI install recipe was run in a fresh venv with the new `$C`: OK on Python 3.13; wheels exist for 3.11 to 3.14. It changes the head of PR 291 from c13f2de; I push it after the whole tools suite and then say so.
NEXT: push both, then C-456/C-457 (console CSP and innerHTML test), C-474/C-466 (docs), C-101, C-138; C-487 (field_core.http.client) is a design-sized production change, I will ask you before starting it.
BLOCKERS: none. Notes: the GX10 is unavailable to me (reviewers run it); a hook asks for a different commit identity, Don ruled: keep Don Hagell; CI on a docs-only PR (297) failed once on an unrelated renew_token test, reported.
