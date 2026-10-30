VERDICT: PASS WITH CONDITIONS on a9be06983be4d92e8eff00cb0657b2a631c2224b (the PR head now; the card names e6df20d, which is its parent)  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-794, PR 356 (field-core: one is_internal_host predicate; C-489). The head moved one commit past the carded e6df20d: a9be069 is a tests-only commit ("C-794 survivors"). I reviewed a9be069; source files are identical between e6df20d and a9be069 per the commit message and my read (hosts.py not touched by the last commit). This SHA only.

OBJECTIONS FIRST
1. The open d7f1058 condition (non-ASCII dot) is closed. hosts.py (the `_NAME_CHARS` ASCII-only check, `_name_internal`) refuses names outside [a-z0-9._-]. Probe: the ideographic full stop, full-width full stop and half-width ideographic stop as dots between link-local and private octets, full-width digits, a local name with an ideographic stop: all False with and without allow_names. HIGH (observed).
2. Forms still accepted that a reader may not expect (all by design or documented, none an address bypass): a scope-id spelling of the loopback address ("::1%eth0") is True; "10.1", "10.0.1", "127.1" short forms are True (inet_aton semantics, resolved to the same address); with allow_names the shapes "internal", ".internal", "a..internal", "-.internal", "_x.internal", "a_b" and any "*.local" are True (shape-trusted names, documented in the docstring; the tools and the MCP client call with allow_names=False). The scope-id and short-form acceptance is not stated in the docstring. LOW.
3. Names are never resolved: a `*.local` or single-label name that the estate's resolver sends outside the estate passes with allow_names=True. llm.py:148 calls `is_internal_host(u.hostname)` with the default (allow_names True). That is a design choice stated in the docstring; it is the caller that decides. MEDIUM-LOW (design).
4. Three stdlib-only copies exist by design (tools/estate_probe.py:163, tools/renew_token.py:222, packages/field-agent/src/field_agent/field_client.py:235) because those programs run without field_core. They can drift; tools/tests/test_internal_host_c489.py holds them equal. Independent check: on 33 hosts (non-ASCII dots, decimal/hex/octal/short forms, trailing dot, brackets, mapped IPv6, scope id, link-local, CGNAT, public, trailing newline and text, names) all three copies equal field_core with allow_names=False: 0 differences. HIGH for those 33.
5. "Every old call site migrated": I found no remaining inline use of ipaddress.is_private/is_loopback or a private-range check in packages/*/src or services/*/src outside the three declared copies. The MCP client (PR 368) has its own local fallback until this PR lands (see my C-781 report); that is stated there and pinned by a corpus test, and it accepts "localhost" and IPv4-mapped forms like this one. Grep-based, MEDIUM for completeness.

ASSUMPTIONS
A1 Card scope: the d7f1058 non-ASCII condition, address forms missed, call-site migration. A2 allow_names=False is the setting for secret-carrying callers.

REASONING / CHECKS
- Tests at this head: field-core test_hosts_c489 132 passed; tools test_internal_host_c489 171 passed; field-core test_llm_c117 54 passed; field-agent suite 151 passed.
- Address probe (about 50 forms, both modes): refused: link-local incl. the cloud-metadata address, fe80::/10, 100.64/10, 0.0.0.0, broadcast, "::", public addresses, mapped public IPv6, bracketed host, trailing dot on an address and on "localhost", embedded space/newline/NUL text, "10", "0", out-of-range octets. Accepted: loopback, RFC 1918, ::1, fc00::/7, mapped RFC 1918, hex/octal/decimal/short spellings that resolve to those, "LOCALHOST", "0xa000001" (as the PR pins).
- Mutants on hosts.py (each restored, worktree removed, nothing committed): name-character rule loosened KILLED (field-core test only; the tools test did not catch it: 171 passed); numeric-shape rule loosened KILLED; mapped-IPv6 unwrapping removed KILLED; name shape any-name True KILLED; localhost removed KILLED; lower-casing removed KILLED; link-local added to the internal set KILLED; inet_aton branch removed KILLED; empty-host check removed SURVIVED (equivalent: an empty string fails the name-character rule anyway). Eight real kills, one equivalent survivor.
- Commits: author and committer Don Hagell no-reply on every commit; diff scan of the last two commits: no estate address, flag value, credential or deploy status.

CONDITIONS
C1 (non-blocking) Say in the docstring that scope-id and short numeric spellings are accepted, or refuse the scope id.
C2 (non-blocking) Let the tools-side test also cover the name-character rule (mutant H1 survives there), so a copy cannot loosen it unseen.
C3 (non-blocking, process) Land this before PR 368 so the MCP fallback can be deleted; add the corpus to both.

NOT VERIFIED
GX10 full set, CI by run id, behaviour under the real resolver, any caller not in packages/*/src, services/*/src, tools/*.py.

CONCLUSION
The non-ASCII hole is closed, the predicate matches its three copies on every form I tried, and its tests bite. PASS WITH CONDITIONS C1-C3, all non-blocking. UNVERIFIED.
