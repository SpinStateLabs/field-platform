# C-1 and C-2 and C-6: reviewer verdicts (teammate-don-reviewer, 2026-10-28)

Full text is posted as PR comments: #55 issuecomment-6467273312 and -6467298074, #56 issuecomment-6467273965, #57 issuecomment-6467274382 (corrected). All runs VERIFIED on the GX10 (own clone ~/ff-work/wt-fieldrev-55, Python 3.12, CI=true, no DB port) on the EXACT heads.

| Card | PR / head | Verdict | Tests | Mutants |
|---|---|---|---|---|
| C-1 | #57 09dcbcd | CONDITIONS | R4a files 153 passed; field-core 1005 passed | 8 run, 7 killed, 1 survived (LOW) |
| C-2 | #55 6e78f31 | CONDITIONS | 55 passed (31 fail on base c8ecba7 source); regression 2036 + 232 passed; topology_lint OK | 7 of 7 killed |
| C-6 | #56 9cdef89 | CONDITIONS | 57 passed; field-core 937 passed | 6 of 6 killed |

No FAIL. No head is rebased-on-main-checked beyond: #55 is +8/-0 vs c8ecba7 (merge commit of main inside the branch).

## C-2 #55 conditions
1. MEDIUM, PROVEN: `operator_auth.validate_rows` accepts kill/revive/drill/attest/mint/revoke under any id (`svc-verify-gb10`, `verifier-gb10`, `SVC-VERIFIER-gb10` all returned None). Only the `svc-verifier-` prefix (`operator_auth.py` LIST_BOUND_PREFIX) makes a row list-bound; a misnamed row is unbound (fail-open vs the empty-list self-agents). Make it a row attribute or refuse the scope set without the prefix, before ENFORCE.
2. MEDIUM, UNTESTED: alias-mint path (`check_granted_by` + `check_explicitly_listed` in delegation `api.py` mint) applies to any identity minting under its own alias, not only the verifier.
3. LOW: attest guard under ENFORCE is a new restriction on every attester (regression suites green; other live callers not checked).
4. LOW: revoke does token lookup before the bound check: 404 vs 403 existence oracle.
5. LOW: commits ae315e6, eeea3ff, 6e78f31 show no GitHub author login; repo identity rule unknown to me.

## C-6 #56 conditions
1. MEDIUM, PROVEN: `alerts.py` uses urllib `build_opener`, which honours proxy env vars. With `http_proxy` set, an alert to a loopback http target (topic in the path and the Authorization header) went to the proxy. https path not probed. Fix: empty `ProxyHandler({})` plus a test.
2. Carried: `stage_aborted`/rollback class (priority 5) must exist before the first automatic arming; script callers exit non-zero on an undelivered alert.

## C-1 #57 conditions
1. LOW (corrected from my first note): mutant removing `nk.get("key_sha256") != live_key` (`rotation.py` ~1544) survives. Not reachable sequentially: run-start foreign_edit check skips first (probe test). Reachable only by an edit between that check and PROMOTE; add a hook-based TOCTOU test.
2. Decision C (Don): a persistent post-PROMOTE fault retries forever; only an hourly keyrotation.failed alerts. Recommend retry cap + CRITICAL alert or the dead-man check before live use.
3. Decision D (Don): abort refusals halt until R9 acts; conflicts with P36 unless R9 reconciles automatically.

## NOT verified
Any live host; full tools/tests on the GX10 (CI green); the other ~100 of #57's 111 mutants; a line-by-line read of #57 rotation.py (1,640 lines; I read diff_guard, _promote, _verify_current).
