# Design note: "is this URL's host estate-internal?" (Lane 10, class A)

Scope: main; reports C-187, C-197, C-213 (comms/inbox/coordinator/20261029-3130, -3400, -3700, -3800, -3910 and later). Probe: 20261101-0700-design-private-host-probe-test.py (`FIELD_REPO=<checkout> python -m pytest -q`), matrix script not pushed (output summarised in section 4). Python in the probe container: 3.13 (see objection 4).

## 0. Correction of the framing
The class is not "numeric spellings". It is that the same question is answered by FIVE independent implementations, and only one was ever hardened. Confidence HIGH (grep, file:line below).
- field-core llm.py:140-170 `cleartext_ok` (hardened by C-117/C-197/C-213; the differential probe of C-213 ran 100,432 URLs).
- field-agent field_client.py:229-236 `_private_host` (used at :138 for the shared secret).
- force-gateway api.py:184 (`ipaddress...is_private or host == "localhost"`; a warning, not a refusal).
- tools/renew_token.py:1562, tools/estate_probe.py:979, tools/phase_g_check.py:798 (one identical expression, three copies; each refuses to send a secret or operator key in clear).
- field-core alerts.py:287-291 `_is_loopback` (loopback only; strict, fine).

## 1. Objections first (failure conditions)
1. Fixes land in one copy: C-197 and C-213 hardened `cleartext_ok` only. The other copies were never differential-tested; they happen to fail closed on every odd spelling (they parse with `ipaddress` only, so `134744072`, `0x08080808`, hex, octal and short forms are refused: probe green). That safety is an accident of being simpler, not a rule.
2. Python's `is_private` is a policy somebody else wrote: it accepts 0.0.0.0/8, 255.255.255.255, 198.18.0.0/15, 192.0.0.0/24, link-local (including 169.254.169.254) and `::`, and, found here, 6to4 `2002::/16` (below). The coordinator ruled some of these "by design" (C-197 F-C197-2, C-213 residual); the ruling covers the IPv4 items, not the IPv6 one.
3. Names cannot be proven internal statically. `cleartext_ok` accepts any single-label name, `.internal` and `.local`: resolved at connect time through whatever resolver and search domain the host has (mDNS for `.local` is spoofable by any LAN host: ruled by design, C-197). An https URL has no such weakness.
4. The answer depends on the interpreter: `ipaddress` range tables changed between Python releases (general knowledge, MEDIUM; I ran 3.13 only; CI runs a 3.11 to 3.14 matrix per the C-450 report), so a spelling can pass on one version and fail on another. NOT verified.
5. Validated host vs connected host: all callers use `urlparse().hostname` and then httpx or urllib. Probe: the two agree for every userinfo, backslash, fragment and `%`-escape shape I tried (`@`, `#@`, `\@`, `%2f@`, trailing dot); httpx and urllib parse the same host. (A browser would not: not relevant here, no browser connects.) HIGH for the shapes tried.
Steelman for leaving it: the four non-llm copies fail closed, the hardened one has a 100k differential result, rulings exist for the rest, and https is the recommended path.

## 2. The invariant
A cleartext request carrying a platform secret may go only to a host that is (a) a literal IP, parsed once by one function, that is loopback or in an explicit allowed set (RFC 1918, `fc00::/7`, `::1`), or (b) an exact name from an explicit allow list (`localhost`, compose service names the estate defines). Everything else is https-only. "Private" is defined by this repository's own set, not by `ipaddress.is_private`.

## 3. Recommendation (one structure)
1. One predicate in field-core, `is_internal_host(hostname) -> bool`, built from `llm.cleartext_ok`'s parse (inet_aton normalisation first) and an explicit network set instead of `is_private`; delete the other four copies (tools may import field-core or carry a tested copy, but a test must assert the copy equals it).
2. The explicit set excludes: 0.0.0.0/8, 255.255.255.255/32, 169.254.0.0/16 (cloud-metadata address inside it), 198.18.0.0/15, 192.0.0.0/24, `::`, `2002::/16`, `fe80::/10` unless the owner names it. Cost: any estate that relies on link-local or the benchmark range breaks loudly; I believe none does (not verified: "I do not know"). This reverses part of the by-design ruling for the IPv4 items: Don's call (decision card), not mine.
3. Names: keep the single-label and `.internal` rules only if the owner wants them; drop `.local`.
4. Tests: the probe in this note as the pin for the one predicate, parametrised over the single implementation, plus a lint that fails on a new `ipaddress.ip_address(...).is_private` outside field-core (same AST style as the C-57 lint).

## 4. Probe results (matrix, this container)
Accepted by ALL four implementations (llm, field_client, the tools expression, force-gateway):
- by design (ruled): 169.254.169.254, 0.0.0.0, 0.1.2.3, 255.255.255.255, 198.18.0.1, 192.0.0.1, fe80::1, `::`.
- NOT covered by a ruling (new): `[2002:808:808::]` (6to4 of a public IPv4). Probe red for all four. MEDIUM-LOW: 6to4 relays route such an address to the embedded IPv4 (general knowledge, MEDIUM).
- Accepted and correct: loopback, 10/8 spellings, IPv4-mapped private and loopback, `fc00::/7`, scoped loopback (`::1%25eth0`), upper-case `LOCALHOST`.
Accepted ONLY by llm.cleartext_ok: `local`, `10.1`, `0x0a.1`. The first is a single-label name by rule; the other two are correct inet_aton spellings of a private address. The other three refuse them (fail closed, inconsistent behaviour: the same URL works for the gateway caller and is refused for FieldClient).
Refused by all: the public spellings (decimal, hex, octal, short, `::ffff:` public, NAT64, `100.64/10`), every userinfo/fragment/escape trick, trailing dot.
Divergence the probe exposes but is not a vulnerability: one URL, four answers.

## 5. What a builder card should pin
- One predicate, one test table (accept list, refuse list, both from this note's probe).
- 6to4 and the explicit set (section 3.2) after Don's ruling.
- A lint against a second `is_private` use.
- Mutants: swap the network set for `is_private`; drop the inet_aton normalisation.

## What I did NOT do
Did not run other Python versions (objection 4). Did not resolve any name or touch DNS. Did not read the defence-shield clauses.py ip handling (different purpose). Did not test IPv6 zone-id edge cases beyond `%25eth0`. Did not edit any source, merge or open a PR. The ruling on link-local and `0.0.0.0/8` is the coordinator's; I list it as an option, not a finding.
