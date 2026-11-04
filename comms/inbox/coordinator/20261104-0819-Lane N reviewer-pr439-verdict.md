# Reviewer: PR 439 (C-1129) provision_ssl_agents: the guarded operator auth refuses another origin

**Verdict: PASS WITH CONDITIONS on head `6825858604b59c2ed64d8fb2b4a414f406557c23`.** HIGH CARE (operator pair handling), made-up values only. Head unchanged at start and end (git ls-remote); 2 commits, Don Hagell noreply on author and committer (0 nonconforming); base 05942b98, main is cd3b7690 (not contained). Not built by this lane. Earlier record: only a groomer read (Q-85); this is the first review with mutants.

Diff (HIGH, read): `tools/provision_ssl_agents.py` `_GuardedOperatorAuth.auth_flow` (+4/-1): the pair is added only if `(scheme, host, port)` of the request equals that of `httpx.URL(PROXY)` AND the (method, path) is guarded; new `tools/tests/test_provision_ssl_origin_c1129.py` (4 tests). The comparison is the same expression as field-core's `GuardedOperatorAuth._same_origin` (guarded_operator.py:99-101, read), so the two tools agree. `PROXY` is read at import (`provision_ssl_agents.py:99`) and the tool already refuses an unset proxy (test c285).

## Objections first
1. httpx applies the auth to each redirected request, so a redirect to another origin is covered by the same compare (httpx behaviour, not run here; MEDIUM).
2. Userinfo trick: `http://x@proxy.test:9000/` has host proxy.test and gets the pair; same as field-core, not a regression (not run; MEDIUM).
3. A trailing-dot host (`proxy.test.`) differs from the base and is refused: fail-closed, provisioning to such a URL would break (LOW, not run).
4. Only a host that differs from the base entirely is tested (`other.test`): a look-alike host sharing a prefix is not (survivor below).

## Measured (GX10 ~/ff-work/wt-ln439, python -B, own venv)
New file 4 passed. tools set (new file, test_proxy_url_required_c285, http_env_proxy lint c57, environment_doc, environment_anchors): PR head 188 passed, 1 skipped, 1 failed; main cd3b7690 205 passed, 1 skipped, the SAME 1 failed (`test_provision_refuses_when_the_proxy_url_is_unset_and_sends_nothing`: environment baseline on both). The count differs only because the PR base is older than main. `tools/environment_anchors.py --check`: 0 wrong rows on the PR head and on main. The file diff vs main is the PR's own +4/-1 (no overlap). CI: see Conditions. 16-suite not run by me.

## Mutants (20 rows; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| B1 a guarded route on the proxy origin carries the pair | 5 | 0 |
| B2 another host never gets the pair | 4 | 1 (compare only the first 2 characters of the host: a look-alike host passes) |
| B3 another port never gets the pair | 4 | 0 |
| B4 another scheme never gets the pair | 4 | 0 |
| B5 the guarded-path test and a pair are still required (pre-existing, not a PR claim) | 0 | 2 (no test of a non-guarded path or of a missing pair) |
Totals counted from the table: killed 5+4+4+4+0 = 17; survived 0+1+0+0+2 = 3; 20 rows. B1 to B4 each have at least 4 kills.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (value read with the verdict command).
- C2: GX10 16-suite 16/16 on a head containing main (base 05942b98; the file diff applies cleanly).

## Findings (non-blocking; new PR only)
- F-439-1 LOW: add a look-alike host (`proxy.test.evil.test`, `prox.test`) and an IPv6/userinfo case to the origin test.
- F-439-2 LOW: no test that a non-guarded path on the proxy origin gets no pair, nor that `pair=None` sends none (pre-existing behaviour; the PR rewrote the condition around them).
