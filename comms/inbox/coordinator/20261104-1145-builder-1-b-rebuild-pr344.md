builder-1: B-REBUILD-PR344 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/550 "rebuild of #344", branch rebuild/pr344-lifecycle-cli-no-proxy, head 6c87a5c72fd7e05d5ab4670c9fb6b1d2d723571b on origin/main 97dcfec1. Old head 22d04601 untouched.
COORDINATOR RULING NEEDED: open PR 460 (head 3040d198, non-draft) already carries 344's 4 commits + PR 425, rebuilt on b39287c1 (25 commits behind main). I released this item once for that reason; dispatch.sh re-queued and re-issued it to me, so I built it. Merge one of 460 / 550, not both; if 460 is the path, it needs REBUILD:PR460.
One real conflict: lifecycle_manager/cli.py::_service_client (main added follow_redirects=False in C-1041; kept PR's trust_env=False plus main's follow_redirects=False, comments merged). Other differences are range-diff context only.
Ran: lifecycle-manager tests 304 passed (+ test_provision_wrapper 6 passed); tools allowlist-reading tests 101 passed, 1 failed: test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist (flags tools/start_role_session.py::call::urllib.request.urlopen from #532). It fails identically on unmodified origin/main: MAIN IS RED on that test, needs an allowlist line or a fix. environment_anchors --check 0 wrong.
Full range-diff:
1:  005ba2be ! 1:  56441ccc lifecycle-manager: the CLI's estate clients never read the proxy environment or follow a redirect; the lint allowlist shrinks by one (C-575, reviewer C-524 F-C524-2)
    @@ services/lifecycle-manager/src/lifecycle_manager/cli.py: _SERVICE_URLS = {
      def _service_client(service: str, pair: tuple[str, str] | None, timeout: float = 20.0):
          var, default = _SERVICE_URLS[service]
          base = os.environ.get(var, default).rstrip("/")
    +-    # a redirect is never followed: httpx keeps custom headers and the auth object's pair on a followed redirect
    +-    # (C-1041 F-C1041-1)
     -    return base, httpx.Client(base_url=base, timeout=timeout, headers=_perimeter(),
    +-                              auth=GuardedOperatorAuth(base, pair, GUARDED_ROUTES.get(service, ())),
    +-                              follow_redirects=False)
     +    # trust_env=False: never read the process's proxy variables, and follow_redirects=False: the perimeter secret
    -+    # (and, on guarded routes, the operator pair) must not follow a redirect or an ambient proxy (C-575)
    ++    # (and, on guarded routes, the operator pair) must not follow a redirect or an ambient proxy (C-575); httpx keeps
    ++    # custom headers and the auth object's pair on a followed redirect (C-1041 F-C1041-1)
     +    return base, httpx.Client(base_url=base, timeout=timeout, headers=_perimeter(), trust_env=False,
     +                              follow_redirects=False,
    -                               auth=GuardedOperatorAuth(base, pair, GUARDED_ROUTES.get(service, ())))
    ++                              auth=GuardedOperatorAuth(base, pair, GUARDED_ROUTES.get(service, ())))
      
      
    + def estate_clients(pair: tuple[str, str] | None, timeout: float = 20.0) -> dict:
     
      ## services/lifecycle-manager/tests/test_cli_clients_no_proxy_c575.py (new) ##
     @@
    @@ services/lifecycle-manager/tests/test_cli_clients_no_proxy_c575.py (new)
     +        other.shutdown()
     
      ## tools/tests/http_env_proxy_allowlist.txt ##
    -@@ tools/tests/http_env_proxy_allowlist.txt: services/incident-replay/src/incident_replay/engine.py::LedgerQueryClient.__init
    +@@ tools/tests/http_env_proxy_allowlist.txt: services/incident-replay/src/incident_replay/cli.py::run::httpx.post = 2
    + services/incident-replay/src/incident_replay/engine.py::LedgerQueryClient.__init__::httpx.Client = 1
      services/incident-replay/src/incident_replay/engine.py::TokenQueryClient.__init__::httpx.Client = 1
    - services/kill-switch/src/kill_switch/api.py::new_endpoint_client::httpx.Client = 1
      services/kill-switch/src/kill_switch/cli.py::_client::httpx.Client = 1
     -services/lifecycle-manager/src/lifecycle_manager/cli.py::_service_client::httpx.Client = 1
      services/ops-console/src/ops_console/api.py::ServiceClient.__init__::httpx.Client = 1
2:  fd377edb ! 2:  7d16eeea lifecycle-manager: pin that every client the CLI verbs build comes from the CLI builder; state the scope (C-575, reviewer C-639)
    @@ tools/tests/http_env_proxy_allowlist.txt
     +# headers (the field-core clients add none then), so it would change what `serve` sends. Closing them needs the shared
     +# client of C-487.
      integration/demo/fixtures/c6-observer/check_rows.py::_events::urllib.request.urlopen = 1
    - integration/demo/fixtures/kr-edge/check_edge_block.py::_ask::urllib.request.urlopen = 1
      integration/demo/fixtures/upgrade-smoke/signing_fault.py::Estate.call::urllib.request.urlopen = 1
    + integration/demo/fixtures/upgrade-smoke/upgrade_flow.py::Estate.call::urllib.request.urlopen = 1
3:  627532e8 ! 3:  c0c44a07 lifecycle-manager: pin the verbs' wiring and the builders' behaviour; correct the kill-switch client docstring (C-575, reviewer C-732)
    @@ tools/tests/http_env_proxy_allowlist.txt
     +# so it would change what `serve` sends. Whether a per-request-auth client (api.PerRequestAuthClient, PRs 318/330) can
     +# take that role is C-487's question; the shared client of C-487 closes these two entries.
      integration/demo/fixtures/c6-observer/check_rows.py::_events::urllib.request.urlopen = 1
    - integration/demo/fixtures/kr-edge/check_edge_block.py::_ask::urllib.request.urlopen = 1
      integration/demo/fixtures/upgrade-smoke/signing_fault.py::Estate.call::urllib.request.urlopen = 1
    + integration/demo/fixtures/upgrade-smoke/upgrade_flow.py::Estate.call::urllib.request.urlopen = 1
4:  22d04601 ! 4:  6c87a5c7 docs: the allowlist note says four serve clients read the proxy environment (C-861 C2)
    @@ tools/tests/http_env_proxy_allowlist.txt
     +# subclasses of httpx.Client; PRs 318 and 330 pin them, and until one lands they are open. This PR closes the CLI's
     +# clients only.
      integration/demo/fixtures/c6-observer/check_rows.py::_events::urllib.request.urlopen = 1
    - integration/demo/fixtures/kr-edge/check_edge_block.py::_ask::urllib.request.urlopen = 1
      integration/demo/fixtures/upgrade-smoke/signing_fault.py::Estate.call::urllib.request.urlopen = 1
    + integration/demo/fixtures/upgrade-smoke/upgrade_flow.py::Estate.call::urllib.request.urlopen = 1
