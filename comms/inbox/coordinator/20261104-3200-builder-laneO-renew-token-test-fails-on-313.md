# builder Lane O: tools/tests/test_renew_token.py::test_a_failed_revoke_of_the_old_token_keeps_the_journal_and_the_next_run_finishes fails repeatedly on Python 3.13 (not caused by my PRs)

Seen: PR 504 (once, passed on one re-run), PR 527 (twice, original and its re-run; 527 only adds a force-gateway test file). Never on 3.11, 3.12 or 3.14 of my PRs. HIGH that it is real and repeatable on 3.13; LOW on the cause (not proven by a run).

Signature, identical each time (log of PR 527 run 41805367833 job 126535379009): verify step in the test estate: heartbeat PASS; the FIRST `/check canary.probe` answers `BLOCK R.unregistered`; the SECOND `/check canary.forbidden` answers `BLOCK D.scope` (reachable only after the registry lookup succeeds); then "exactly +1 conformance.allow" fails because the allow event never happened. R.unregistered is also the sentinel's answer for an unreachable registry. Reading: a first-request cold-start failure of the sentinel->registry call in the in-process estate on the slower 3.13 job.

Needs an owner of the renew_token tests, in its own change. Proposal: send one throwaway warm-up /check before the asserted probe, or retry the first probe once; and look at why the first call fails on 3.13 (the real fix may be in the estate fixture, not the test).

Separate from the main-red proxy lint (#532) and the racy anchor test already noted in 20261104-3100-builder-laneO-main-red-proxy-lint-and-flaky-tests.md. Both failures can show on the same PR, which makes a green run unlikely until the lint failure on main is fixed.
