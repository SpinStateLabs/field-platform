builder-1: B-REBUILD-PR425 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/564 "rebuild of #425", branch rebuild/pr425-lifecycle-cacert, head 54f13c8a55e1d4992d0476f8cffe59dd3f6ba7ce. Old head 186998a7 untouched.
STACKED: PR 425 is stacked on PR 344 (its first 4 commits are 344's). Branch sits on my rebuild of 344 (PR 550); PR base is rebuild/pr344-lifecycle-cli-no-proxy so the diff is 425's 2 own commits. Merge 550 first, then retarget 564 to main. Open PR 460 carries 344+425 on an older base: merge one path, not both.
One conflict: cli.py::_service_client comment block (kept main's C-1041 lines + PR's verify lines; code identical). 2nd commit identical.
Ran: lifecycle-manager 320 passed; anchors 0 wrong; test_http_env_proxy_lint_c57 1 fail = main's start_role_session.py, same on unmodified main.
Range-diff:
1:  13f437d4 ! 1:  55b2b513 lifecycle-manager: the CLI's estate clients take --cacert, a PEM bundle for an https estate behind a private CA (C-1098, reviewer Q-09 F-Q09-1, Don's ruling)
    @@ services/lifecycle-manager/src/lifecycle_manager/cli.py: _SERVICE_URLS = {
          var, default = _SERVICE_URLS[service]
          base = os.environ.get(var, default).rstrip("/")
          # trust_env=False: never read the process's proxy variables, and follow_redirects=False: the perimeter secret
    --    # (and, on guarded routes, the operator pair) must not follow a redirect or an ambient proxy (C-575)
    -+    # (and, on guarded routes, the operator pair) must not follow a redirect or an ambient proxy (C-575).
    +     # (and, on guarded routes, the operator pair) must not follow a redirect or an ambient proxy (C-575); httpx keeps
    +     # custom headers and the auth object's pair on a followed redirect (C-1041 F-C1041-1)
     +    # verify: the system trust store, or the --cacert bundle's context (C-1098); trust_env=False also keeps
     +    # SSL_CERT_FILE / SSL_CERT_DIR unread, so the option is the one way to trust a private CA.
          return base, httpx.Client(base_url=base, timeout=timeout, headers=_perimeter(), trust_env=False,
2:  186998a7 = 2:  54f13c8a docs: the lifecycle CLI's --cacert option in the README and the deploy runbook; the httpx SSL_CERT_FILE line states what Q-09 measured (C-1098)
