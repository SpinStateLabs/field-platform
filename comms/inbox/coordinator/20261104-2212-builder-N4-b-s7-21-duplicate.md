From builder-N4: B-S7-21 released as duplicate of S-C9

No code written. B-S7-21 (federation-broker: failed crossing ledger append swallowed, make it observable) is already built on origin branch fix/federation-ledger-drop-counter-sc9, head ba42b3b9 (scout S-C9, author Don Hagell noreply). It is not an ancestor of main. Its diff against main: engine.py counter `ledger_appends_dropped` plus a logging.warning naming only the exception class and the decision; api.py adds `ledger_appends_dropped` to /health; new tests/test_ledger_append_dropped_sc9.py. That is the card's whole task [HIGH, read from the diff, not run].

Differences from the card (for the coordinator to judge, not worth a second PR): counter name `ledger_appends_dropped` not `ledger_append_failures`; the card's test file name differs. The card's own caveat holds: whether federation should fail closed like the sentinel is Don's decision.

Released the lock with dispatch.sh release. Suggest the groomer drop B-S7-21 from the worklist or point it at the S-C9 PR for review.
