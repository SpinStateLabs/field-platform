# ssl-ff-builder-9: B-RT1 PR 846 update

PR 846 head is now d551353f660290c93290b75f31412c1e711ac998, CI green on all 7 checks. Two follow-up commits after the first filing: docs/ENVIRONMENT.md first-read anchor sealed_ledger/api.py:475 -> 481 (tools anchor tests, 104 passed), and two ops-console tests (test_console_features.py) that posted formula-lead event types over HTTP now write them to the ledger store (the charset refuses them over HTTP; console neutralising kept as defence in depth; 34 passed).
