# builder-1 S3-2 (lifecycle-manager empty/BOM roster)
PR: https://github.com/SpinStateLabs/field-platform/pull/622 (draft), head afd5ca95.
Ran: new tests 7 red before fix; both mutants caught (6 and 1 failed); services/lifecycle-manager/tests 277 passed (sibling src dirs on PYTHONPATH; spend_governor is imported by engine.py).
Other: #561 and #576 CI red is main's (tools/start_role_session.py from #532 trips test_http_env_proxy_lint_c57); commented once on each. No fix on main known; needs a small PR (ProxyHandler({}) or allowlist line).
