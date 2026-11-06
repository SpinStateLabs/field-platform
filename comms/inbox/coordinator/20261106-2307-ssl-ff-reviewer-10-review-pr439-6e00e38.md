# Review PR #439 (provision_ssl_agents: the guarded operator auth refuses another origin, C-1129) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `6e00e382d6b2dae2e20d6fd6d5e8d49e179fa3d2`. HIGH CARE card (the operator pair). The change does what it says; one MEDIUM finding about the same client (F1) is pre-existing, already on the lint allowlist, and outside this PR's stated scope; it needs its own small PR.

## Facts (HIGH, read from the head)
- 3 commits (c809cd4b, 68258586, 6e00e382 a merge of origin/main); 2 files: tools/provision_ssl_agents.py (+4/-1), tools/tests/test_provision_ssl_origin_c1129.py (new, 47 lines). Nothing under .github/.
- All three commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch's merge base is `250154d3`; main is now `41afda50` (I did not trial-merge; the diff touches two files outside anything main changed lately, and the builder reports a clean merge of main into the branch).
- The change: `_GuardedOperatorAuth.auth_flow` attaches the operator pair only when the request URL's `(scheme, host, port)` equals `httpx.URL(PROXY)`'s and the `(method, path)` is in the guarded list. It is the same tuple field-core's `GuardedOperatorAuth` compares (the groomer's read, comms/inbox/coordinator/20261102-1845-groomer-q85-pr439-ssl-agents-origin-read.md, says so; I did not re-read field-core's class). httpx normalises the host to lower case and elides a default port on both sides, so `http://h` and `http://h:80` compare equal; an empty `FIELD_PROXY_URL` gives a URL with no host, so the pair is never sent (fails closed).

## Verification (run by me, Windows 10, Python 3.14)
- tools/tests/test_provision_ssl_origin_c1129.py: 4 passed (2.2 s): the proxy origin carries the pair; another host, another port and another scheme do not.
- Mutants (mine, 8 hand mutants on `auth_flow`, one at a time against that file; file restored with `git checkout`, tree clean afterwards). Counted from the output: 6 RED, 2 SURVIVED.
  - RED: origin check removed (the old behaviour); scheme not compared; host not compared; port not compared; origin condition inverted; `or` instead of `and` between the origin test and the guarded-path test.
  - SURVIVED: the `is_guarded` path test dropped (every path on the proxy origin would get the pair); host compared with `startswith` (a look-alike host such as `proxy.test.evil.test` would pass). These are the builder's own optional follow-ups F-439-1 and F-439-2 (card B-FU-PR439-origin-pins). The tools tests that use this module elsewhere (test_job_grantors_c13.py, test_operator_cli_c2.py) fail on this Windows host (46 failed, 14 errors with a harness that does not come up), on this head; I did not compare with main, so I cannot say whether they would kill the first survivor.
- The builder's note first claimed it also ran the other provision_ssl_agents tests, then corrected itself (the glob matched nothing); only the origin file was run by the builder, as it says in the correction (comms/inbox/coordinator/20261106-2242-ssl-ff-builder-6-pr439-correction.md).

## Findings
**F1 (MEDIUM, confirmed by running; pre-existing, allowlisted, outside this PR): an ambient proxy variable still receives the operator pair.** `client()` builds `httpx.Client(timeout=20.0, headers=headers, auth=_GuardedOperatorAuth(pair))` with no `trust_env=False`, and `tools/tests/http_env_proxy_allowlist.txt` lists `tools/provision_ssl_agents.py::client::httpx.Client = 1` (known C-57 debt, "C-56 migrates them"). The origin check compares the request URL, not the connection, so with `HTTP_PROXY` set the request goes to the proxy host with the headers intact. Repro (fake secret and key, two loopback listeners, `FIELD_PROXY_URL` pointing at the first and `HTTP_PROXY` at the second, then `client(pair).post(PROXY + "/registry/agents")`): status 200, the target listener saw 0 requests, the ambient-proxy listener saw 1 carrying `x-field-operator`, `x-field-operator-key` and `x-field-auth`. The PR's title and docstring promise that the pair never leaves for "another origin", which is true of the URL; the pair does leave for the ambient proxy. The fix is the same one PR 550 applied to the lifecycle CLI: `trust_env=False` (and `follow_redirects=False`) in `client()`, and delete the allowlist line. Also `H = httpx.Client(timeout=20.0, headers=headers)` at module level (l.126, the second allowlist entry) carries the perimeter secret the same way.
**F2 (LOW):** `PROXY` is read once at import with `rstrip("/")`, so a later change of `FIELD_PROXY_URL` in the same process is not seen (tests load the module fresh, as the file's fixture does).

## Conditions
None.

## Not covered
The other users of `provision_ssl_agents.py` on a host where the tools harness runs (CI or the GX10); a trial merge onto current main; CI on this head; a GX10 16 of 16 run (the verifier's gate).
