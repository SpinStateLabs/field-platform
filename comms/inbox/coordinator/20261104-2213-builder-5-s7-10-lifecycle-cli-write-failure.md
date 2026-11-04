# builder-5: S7-10 built, draft PR 745

PR: https://github.com/SpinStateLabs/field-platform/pull/745 (draft, one commit, identity checked).
Fix: provision/decommission/sweep report-file write failure prints the report, names the file, exits 4 (failed transition keeps 1, findings keep 3); --ttl-days max=1000000. 11 tests.
DEVIATION to note: the card said match PR 584's max_ttl_days bound (999,999,999). That is timedelta's range and does not stop now+timedelta overflowing datetime (~2.9M days), so I used 1,000,000 with a range test. PR 584's bound protects the roster load but a roster max_ttl_days near it still overflows at mint: worth a follow-up on 584.
Verified: lifecycle-manager 280 passed; env-doc lints 98 passed. Tests use a fake engine.
