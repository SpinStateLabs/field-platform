VERDICT: PASS WITH CONDITIONS on 1f7f61f51e264566b708e49600bbe6f8b8b80966  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-781, PR 368 (field-mcp PR 1, Tier 1 read-only server). Applies to this head only.

OBJECTIONS FIRST
1. Mutant harness can pass for the wrong reason. scripts/mutants.py sets PYTHONPATH to the copy's src only, so on a checkout where the service packages are not installed the four test_route_coverage tests ERROR at baseline (86 passed, 4 errors in my run) and every mutant is "killed" by -x on collection error. R1/R2/R3 are the ones that matter. I re-ran R1, R2, R3, D5 with the service sources on the path: KILLED, baseline 90 passed. So the controls hold; the harness gives no signal when the services are not installed. Confidence HIGH.
2. SEGMENT is matched with `$`, so a value with one trailing newline passes the check (tests: "a\n" accepted). build_path quotes it to %0A, so no injection; the check is looser than its stated pattern. Confidence HIGH. Not blocking.
3. hosts.py fallback accepts "localhost" and IPv4-mapped IPv6 spellings of RFC 1918 addresses. When C-489 lands and field_core.hosts is used with allow_names=False, "localhost" may be refused (cannot verify: field_core.hosts is not on main; present only on PR 356 history). The test_hosts_predicate corpus is the guard. Confidence MEDIUM.
4. client.py builds its own httpx.Client, not field_core.http (PR 365). Pins match (trust_env=False, follow_redirects=False, explicit timeouts); drift risk only. Confidence HIGH.
5. Redaction is substring replace of configured secrets in strings/keys; a secret split across fields or encoded is not caught. Bounded by Tier 1 never sending the key in a response path. Confidence MEDIUM.

ASSUMPTIONS
A1 Design note 20261030-1700 (D1-D8, tiers 49/8/20) is the spec. A2 No GX10 and no CI read. A3 Packages importable from the repo checkout equal CI's editable installs.

REASONING / CHECKS
- Tests: PYTHONPATH with all service and package sources: 90 passed. Mutants: 29 of 29 KILLED (K1-K13, C1-C5, D1-D5, R1-R3, S1, P1), none NOT APPLIED.
- Tool count: len(catalog.TOOLS) = 49 (matches the note). EXCLUDED holds 63 keys: Tier 2, the 20 Tier 3 routes, the "Other" group (force-gateway POST /v1/messages and claude-approver POST /halt, which answers my C-780 F-C780-1), ops-console, and the hidden operator routes. test_route_coverage builds all 14 apps and requires every live route to be a tool or an exclusion with a reason.
- FFMCP_ENABLE_DESTRUCTIVE appears only in scripts/mutants.py (the D5 mutant) and in tests/test_dispatch.py:78 as an absence assertion. Not in src. HIGH.
- os.environ/getenv: only src/field_mcp/config.py (grep); K13 pins it.
- Base URL comes from config only; tool schemas set additionalProperties false (D3) and the path pattern is in the schema (K7b).
- Path probe: "..", "a/b", "a%2fb", "a b", "%2e%2e", "a?b", "a#b", non-ASCII, 201 chars all refused; ":" "@" "~" "." allowed and percent-encoded (":"→%3A, "@"→%40). Trailing newline: see objection 2.
- Hosts fallback probe: 10.0.0.1 and ::1 accepted; 0x7f.1, 127.1, 2130706433, "10.0.0.1.", [::ffff:10.0.0.1] with brackets, fe80::1, 169.254.1.1, 100.64.0.1, "host" refused. HIGH on observed behaviour.
- Commit author and committer on all four commits: Don Hagell no-reply. No estate address, flag value, build SHA, deploy status or credential seen in the diff scan (test P1 also checks the tree).
- ci.yml change is a comment wording line only (+5 -1 across ci.yml and the install lines for hash-checked field-mcp requirements); hashes file and constraints not re-derived.

CONDITIONS
C1 (non-blocking) Make the mutant harness fail closed when the baseline suite is not green, so a collection error cannot read as a kill. 
C2 (non-blocking) Anchor SEGMENT with \Z or fullmatch.
C3 (non-blocking, follow-up when C-489 lands) delete the fallback and re-run test_hosts_predicate; decide on "localhost".
C4 (still open from C-780) PATCH /agents/{agent_id} remains in the Tier 2 list; confirm it stays there.

NOT VERIFIED
GX10 full suite, CI by run id, the hash file contents against the index, the MCP SDK behaviour beyond the stdio test, snapshot.json against a live GX10 build. A pycache was written in the scratch worktree (config.cpython-313); the worktree is deleted and nothing was committed.

CONCLUSION
At 1f7f61f the code matches the design note on the points I probed; no blocking finding. PASS WITH CONDITIONS C1-C4, all non-blocking, UNVERIFIED.
