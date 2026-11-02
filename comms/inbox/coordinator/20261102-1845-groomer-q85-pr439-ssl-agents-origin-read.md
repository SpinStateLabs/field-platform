# Q-85 read of PR 439, head 6825858604b59c2ed64d8fb2b4a414f406557c23 (git ls-remote refs/pull/439/head agrees)

Reader: grooming assistant, not the author (Lane 16 per the coordinator's C-1129 owner ruling). READ, NOT MEASURED: nothing was run. I read both patches in full (tools/provision_ssl_agents.py +4 -1; tools/tests/test_provision_ssl_origin_c1129.py +47) and the module's `client()` and `PROXY` lines at the same sha. HIGH CARE card (operator pair): this is a read, not a verdict.

Findings
1. HIGH (read): `_GuardedOperatorAuth.auth_flow` now attaches the operator pair only when the request's (scheme, host, port) equals the proxy base URL's, and the existing `is_guarded(method, path)` check still applies. That is the same tuple field-core's `guarded_operator.GuardedOperatorAuth` compares (I read that file on main earlier).
2. HIGH (read): one class and one call site: `client()` builds `httpx.Client(timeout=20.0, headers=..., auth=_GuardedOperatorAuth(pair))`. No other use of the class in the file.
3. HIGH (read): the client does not pass `follow_redirects`, so a redirect is not followed by default in current httpx (MEDIUM on that default, from general knowledge, not checked in this repo's pinned version). If a redirect were followed, custom headers can travel with it regardless of `auth_flow`; I do not know the pinned httpx version.
4. MEDIUM (read): `PROXY` is read from `FIELD_PROXY_URL` at import with a trailing slash removed. With an empty value, `httpx.URL("")` has no scheme or host, so the equality is false and the pair is never sent: it fails closed. No test covers the empty value.
5. The new tests: the proxy origin carries the pair; another host, another port and another scheme do not. The module is loaded fresh per test so `PROXY` follows the monkeypatched env. Not covered (LOW): an explicit default port against an implicit one, and the empty base. The values in the test file are made-up test strings.
6. CI when I looked: tests (3.11 to 3.14) in_progress; compose-smoke, fly-image-smoke and compose-upgrade-smoke success. I do not know the test result.

Not checked (I do not know): whether the new tests fail without the change (no mutant run by me), the httpx version and redirect default, and the full suite. Result: no defect found in what I read; not a PASS.
