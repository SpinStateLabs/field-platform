VERDICT: PASS on b2f3b161e54b0e6659c1149acb45b43a475e0a60 (UNVERIFIED: cloud reviewer; Linux only; CI not read)

Same PR and head as my report 20261104-1130-reviewer-c697-pr357-alerts-default-opener-test.md (head re-checked: unchanged). Test-only PR (+30 lines in packages/field-core/tests/test_alerts_ntfy.py).

OBJECTIONS FIRST
1. Does the test go red if the opener reads the proxy environment? Yes, by four mutants on alerts.py (opener built without the empty proxy handler: 4 failed; send() calling urlopen instead of the opener: 6 failed; the no-opener path building a fresh default opener: 3 failed; the proxy handler built from the environment instead of empty: 4 failed). The new test is among the failures for three of them; its own contribution per mutant was not isolated. MEDIUM.
2. Other default openers still reading the environment: five bare urlopen calls remain in non-test code, all on the C-57 allowlist (tools/tests/http_env_proxy_allowlist.txt lines 3-6 and 58): c6-observer/check_rows.py:44, kr-edge/check_edge_block.py:55, upgrade-smoke/signing_fault.py:59 and upgrade_flow.py:77, tools/fly_identity_check.py:188. Six other openers use an empty ProxyHandler (alerts, canary, field_client, estate_kill_watcher, estate_probe, renew_token). HIGH.
3. The loopback-through-proxy assumption is Linux-specific (macOS and Windows consult a system bypass list); on those the "never the proxy" half proves less. LOW.

CONCLUSION
PASS, as C-697. Non-blocking: run the new test alone against each mutant; note the Linux assumption; migrate the five allowlisted sites when their cards land.

FINDINGS
F-C753-1 LOW, packages/field-core/tests/test_alerts_ntfy.py (new test; Linux-only proof). MEDIUM.
F-C753-2 INFO, five allowlisted bare urlopen sites (listed above). HIGH.

NOT VERIFIED: non-Linux behaviour; CI; per-mutant isolation of the new test.
