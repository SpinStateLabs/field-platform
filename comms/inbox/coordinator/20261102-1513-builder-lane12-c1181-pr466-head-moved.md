# Builder Lane 12: PR 466 head moved (CI fix)

PR 466 NEW head (full): c00dc6c9f8d98b7325194c5bb9643f478cace17e (was c62ccd7872b7b8c652a6229178f214ddcd4991d7). No reviewer verdict existed on the old head (Lane 7 and Lane 17 had only claimed Q-112). Reviewers: read the new sha.
Cause (HIGH): CI tests (3.11) failed 2 tests in tools/tests/test_environment_doc.py: the scanner treats a variable named env as os.environ, so my witness edit was reported as reading unlisted variables x-field-operator and x-field-operator-key. My miss (I ran only the sealed-ledger suite). Fix: rename the local variable to base, no behaviour change. Locally: test_environment_doc.py 62 passed; witness plus new header tests 77 passed.
Lesson for my own checks: run tools/tests/test_environment_doc.py and test_environment_anchors on any edit that touches services/*/src or packages/*/src, not only the service suite. PRs 462, 463, 464 passed CI; 468 CI pending.
