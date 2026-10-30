VERDICT: PASS WITH CONDITIONS on 846242e5919d796ad56564dccb44c5bc21b50b4c (UNVERIFIED: cloud reviewer, no GX10, full suite not run, CI not read; the PR's host tests plus llm tests ran: 223 and 50 passed)

Head matches the card. Two commits on main; author and committer are the no-reply identity. 10 files (field-core hosts.py new, llm.py, three tools, field_client.py, three test files). A parallel reviewer card (C-689, GX10) exists on the same head; this one is the read-only angle.

OBJECTIONS FIRST
1. PROVEN, NOT NEW BUT NOT CLOSED: the name rule accepts any host without an ASCII dot that is not an address. An ideographic or full-width dot makes a public address a "single label": cleartext_ok("http://8<U+3002>8<U+3002>8<U+3002>8/x") is True (field_core.llm.cleartext_ok through is_internal_host), and httpx builds the request for host 8.8.8.8 (same result for U+FF0E and U+FF61). So a plain-http key can be directed at a public address. Main gives the same True (same rule in the removed code), so this PR does not regress it, but the PR title promises "one predicate" for the class and the class is still open through this door. MEDIUM, HIGH confidence (run on both heads).
2. Names are accepted without resolution: metadata.google.internal, instance-data and metadata all answer True with names on (hosts.py:28-30), although Don's C-488 ruling refuses the cloud-metadata address itself. A name that resolves to a refused range passes. Main accepted these too. LOW-MEDIUM; MEDIUM confidence that it matters (depends on the estate's DNS).
3. The single-label branch also accepts strings that are not hostnames: bracketed IPv6 text ("[2001:db8::1]", "[fe80::1]"), text with a colon ("foo:bar"), an unparseable IPv6 ("2001:db8::zz"), a host with a trailing tab. All True with names on. Not reachable through urlparse().hostname (which strips brackets and the callers pass that), but reachable if anyone calls the predicate with a raw netloc. LOW.
4. "One predicate replaces four copies" is partly cosmetic: the logic still exists in four places (hosts.py, field_client.py, estate_probe.py, renew_token.py; phase_g_check reuses estate_probe's). The PR keeps three of them equal to the original with a parametrised equality test, which is sound, but a fix to the predicate needs four edits. The reason (stdlib-only tools and client) is stated.
5. One remaining use of is_private outside field-core: services/force-gateway/src/force_gateway/api.py:184 (the upstream-key warning). It is on the test's allowlist with a stated reason (open PRs touch the file). So the second policy still exists in the gateway: link-local passes there.
6. Behaviour change by ruling, not a defect: llm.cleartext_ok previously accepted link-local addresses and now refuses them; an estate relying on that breaks loudly (C-488 notes this).

ASSUMPTIONS
A1 "Internal" = Don's C-488 set: loopback, RFC 1918, ::1, fc00::/7, plus (with names on) localhost, single-label names, .internal, .local. A2 Probes ran on the real predicate and on field_core.llm.cleartext_ok in a scratch worktree; httpx as installed; one interpreter. A3 Glibc-style inet_aton semantics (the sandbox's) are what the predicate and the resolver share.

REASONING
1. Address forms (is_internal_host, names on / off): accepted: 127.1, 0x7f.1, 0177.0.0.1, 2130706433, 0x7f.0x0.0x0.0x1, 0X7F.1, 0xA.1, ::ffff:7f00:1, ::1 with a scope suffix, LOCALHOST. Refused: 0, ::127.0.0.1 (IPv4-compatible), 64:ff9b::7f00:1 (NAT64), localhost. (trailing dot), a host with a NUL, 127.0.0.1/8, 1.2.3, fe80::1 with a zone, 10.0.0.1 with a bad zone, 169.254.169.254, 0.0.0.0, 255.255.255.255, 198.18.0.1, 192.0.0.1, ::, 2002:808:808::, fe80::1, 100.64.0.1, ::ffff:169.254.169.254 (the PR's table). HIGH.
2. URL-level: cleartext_ok accepted http://[::1]/, localhost with a port, 0x7f.1, 127.1; refused 127.0.0.1@evil.com and the fragment trick (hostname evil.com), http://[2001:db8::1]/, the metadata address. HIGH.
3. Mutants (restored; worktree removed; nothing committed): each range deleted: 127/8 -> 14 failed, 10/8 -> 20, 172.16/12 -> 8, 192.168/16 -> 6, ::1 -> 12, fc00::/7 -> 8; IPv4-mapped handling removed -> 8; inet_aton normalisation removed -> 18; numeric-character guard removed -> 6; swap the set for ipaddress is_private -> 56. A test is red under every mutant I tried. HIGH. (The card asks for a mutant per refused range, e.g. link-local; the is_private swap covers those together: 56 failures.)
4. Call sites: the old inline logic is gone from llm.py (llm.py:148); the three tools and the client each carry a copy checked equal by tools/tests/test_internal_host_c489.py over 32 spellings. Search for inet_aton in non-test code finds only the four sites. HIGH. The lint test (no is_private outside field-core except the one allowlisted file, with a scan-size floor of 100) passes.
5. Diff scan: no address, SHA, flag value, deploy status or credential; the test lists documentation and well-known addresses only. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The predicate matches the ruled set for every address spelling I could build and its tests are sharp. The class "which hosts may receive a cleartext key" is still open through the name rule (ideographic dots, metadata names), exactly as on main. Conditions, none blocking this PR:
- C1 (do soon; separate card): F-C696-1 refuse names containing any non-ASCII character, or normalise with IDNA before the dot test; add the three dot variants to the test table.
- C2 (decision for Don): F-C696-2 whether names that resolve into refused ranges (metadata.google.internal, instance-data) are acceptable under the C-488 ruling.
- C3 (non-blocking): F-C696-3 restrict the single-label rule to [a-z0-9-] labels.
- C4 (non-blocking): F-C696-5 migrate force-gateway/api.py:184 when its open PRs land (already listed).

FINDINGS
F-C696-1 MEDIUM, packages/field-core/src/field_core/hosts.py:28-30 (name rule; "." not in host) with llm.py:148: a non-ASCII dot makes a public IPv4 look like one label. PROVEN, also on main. HIGH.
F-C696-2 LOW-MEDIUM, hosts.py:28-30: metadata names accepted by name. PROVEN (predicate). MEDIUM on impact.
F-C696-3 LOW, hosts.py:28-30: strings with brackets, colons or whitespace pass as single labels. PROVEN.
F-C696-4 LOW, packages/field-agent/src/field_agent/field_client.py:231-252, tools/estate_probe.py:159-182, tools/renew_token.py:218-242: three copies of the logic. HIGH.
F-C696-5 LOW, services/force-gateway/src/force_gateway/api.py:184: second policy (is_private) remains. HIGH.

NOT VERIFIED: the GX10 full suite; CI; behaviour with a resolver that differs from this sandbox's inet_aton; whether any caller passes a raw netloc into the predicate.
