# builder Lane O: renew_token 3.13 intermittent failure: investigated, NOT reproduced, NOT fixed (no PR)

Follow-up to 20261104-3200. Claim check: no open PR or branch covers it (PR 567 is the renew-token pins rebuild, a different change).

TRIED (HIGH on the results, they are measurements):
- 15 runs of test_a_failed_revoke_of_the_old_token_keeps_the_journal_and_the_next_run_finishes in isolation on Python 3.13.18 with GITHUB_ACTIONS=true: 15 of 15 pass.
- 12 more runs under local CPU load (2 busy processes per CPU, 4 CPUs): 12 of 12 pass.
So it needs whatever the CI job has (a 10-minute full tools run, runner contention) and I cannot reproduce it here. I do not know the cause. Anything I pushed as a fix would be a guess.

WHAT THE CODE SAYS (MEDIUM, read not proven): the test estate is a subprocess (tools/tests/estate_harness.py) hosting every service's real create_app under one uvicorn; the test's readiness wait polls only /ledger/health (test_renew_token.py:371), not the sentinel-to-registry path the verify step then uses. The verify step is tools/estate_probe.py cmd_canary: its first call is POST /sentinel/check for canary.probe, which answers BLOCK R.unregistered, while the second call (canary.forbidden) correctly answers D.scope in the same run. engine.py maps BOTH an unknown agent and RegistryUnreachableError to R.unregistered, so the failure line alone cannot say which. A first-call cold start is consistent with this; it is not shown.

DIAGNOSTIC I DID NOT BUILD, and why: the FAIL line (estate_probe.py:546, _clause(v)) could name whether the reasons start with "registry unreachable". Printing the reasons text itself would put an exception string in the output of the production estate probe (credential-handling tool, R-06), and that text can carry an estate address; a fixed token such as `registry-unreachable` vs `agent-not-found` would be safe. That touches a HIGH CARE tool, so it needs an owner's decision and an independent reviewer, not a speculative PR from me.

NEXT STEP I SUGGEST (needs the GX10, which I do not have): run the one test in a loop on the GX10 under load, with the safe diagnostic above, or run the 3.13 tools job again with it. Failures seen so far: PR 504 (once, passed on its re-run), PR 527 (twice, original and re-run; PR 527 only adds a force-gateway test file). Never on 3.11, 3.12 or 3.14 of my PRs.
