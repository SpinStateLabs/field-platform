VERDICT PASS on b0a280290644bfe0d84e1153562ce3550ac4508c (PR 356, Q-28, Lane 15 reviewer; delta 3713e14..b0a2802 on the C-1047 conditions; UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. A host predicate that trusts names by shape and never resolves them is a policy, not a proof: with allow_names, a single-label name or *.internal / *.local that the estate's resolver sends elsewhere passes (hosts.py docstring says so); the tools and field-agent client use allow_names=False for that reason.
2. "One predicate replaces four copies" is not literally true: three standard-library copies remain by design (packages/field-agent/src/field_agent/field_client.py:233 `_private_host`, tools/renew_token.py:221 and tools/estate_probe.py:162 `_internal_host`), held equal to the canonical one only by a test (tools/tests/test_internal_host_c489.py); a fifth, looser check remains in force-gateway (below).
3. The delta is tests only (one file, +10 lines); it cannot change behaviour, and cannot make a wrong predicate right.
4. A percent-sign pin proves ten spellings, not the class.
ASSUMPTIONS: head current (git ls-remote = full sha above); delta = test_hosts_c489.py +10 (git diff 3713e14..head --stat); made-up hosts only.

REASONING
1. Baselines: test_hosts_c489.py 201 passed; whole field-core suite 1331 passed, 1 skipped (HIGH, run).
2. Differential probe (own code): 491 candidate hosts (twelve IPv4 addresses internal, public, metadata, CGNAT, broadcast, each in about 35 spellings: decimal, hex, octal, short, dotted hex, padded, trailing dot, leading dot, whitespace, NUL, newline, full-width digits, ideographic dots, bracketed, IPv6-mapped and compatible forms, 6to4 and NAT64, scope ids, trailing percent; plus IPv6 and name candidates) x both allow_names values = 982 calls. Soundness test: whenever the predicate says internal and the string resolves numerically by getaddrinfo (AI_NUMERICHOST), every resolved address is in the internal set. Result: 0 violations, no exceptions (HIGH for the corpus, MEDIUM beyond it).
3. The three standard-library copies agree with `is_internal_host(h, allow_names=False)` on all 491 hosts (0 differences each) (HIGH).
4. PR test against 14 mutants of hosts.py: 12 killed, 2 survived. Killed include the three scope-id strippers (always, only with %25, trailing percent: the delta's target), name characters allowing %, inet_aton check dropped, 172.16/12 widened to /8, 169.254/16 added, mapped addresses not unwrapped, metadata allowed by name, allow_names ignored, name fullmatch weakened, lowercase removed. Survivors: (a) the numeric regex allowing "%": equivalent (the host then fails inet_aton and the name rule refuses it); (b) the numeric-host `fullmatch` weakened to `match`: SURVIVES BOTH test files that cover the predicate (372 tests), and my probe shows 24 failures under it: every host with a trailing NUL (for example an address followed by \x00) makes the predicate raise ValueError (embedded null byte) instead of returning False. The real code returns False for all of them (HIGH, run).
5. C-1047 conditions: both code conditions closed on 3713e14 per C-1057; the delta adds the F-C1057-356-1 pin (percent behind anything but an IPv6 address is refused); the three scope-id mutants named by the builder are killed (HIGH, run). Non-code items (the equality test as the only link between the copies) stay as stated in C-1057.
6. merge-tree: PR 356 against main clean; with PRs 325, 348, 369, 375, 381, 394, 402, 410 clean; with PR 352 CONFLICT in docs/ENVIRONMENT.md only (line-number column, mechanical).

FINDINGS
- F-Q28-1 LOW (SSRF-class, unpinned): a host with a trailing NUL is not tested; weakening `_NUMERIC_HOST.fullmatch` to `match` would make the predicate raise rather than answer False, and no test notices. Add `127.0.0.1\x00` (and `10.0.0.1\x00.evil`) to the refused table.
- F-Q28-2 INFO: three stdlib copies remain; equal on my corpus; the equality test is the only guard.
- F-Q28-3 INFO: force-gateway/src/force_gateway/api.py:184 (`_base_url_warning`) still uses `ipaddress.is_private`, which treats 169.254.169.254 as private; it only chooses whether to print a warning, so no gate depends on it. Pre-existing, outside C-489's list.
- F-Q28-4 INFO: docs/ENVIRONMENT.md conflicts with PR 352.

NOT VERIFIED: CI, GX10, behaviour against a real resolver for names (never resolved by design), the full-width digit and ideographic dot cases under a non-glibc resolver.

CONCLUSION: PASS. The delta closes F-C1057-356-1; the predicate survives a 982-call differential probe with no false internal verdict; one LOW unpinned control (F-Q28-1) and three INFO.
