# Review PR 656 @ dc312fda23feb9e1051180e953f14bd68dcb3b7f (field-agent FieldClient: base_url must be http(s) with a host; _call refuses any other scheme, S4-8) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head dc312fda. UNVERIFIED (cloud, no GX10). Condition 1 is a ruling on a measured host-redirect through `prefixes`, which the PR's own last test pins as accepted.

## Objections first
1. The stated harm is a `file:`/`ftp:`/`data:` base URL read as the sentinel's answer. The fix checks the scheme at construction and again per request. The per-request check looks at the scheme only, so a `prefixes` entry that changes the HOST is not stopped (measured below).
2. `shared_secret` is only allowed over https or a private host, judged on `base_url`; a host-changing prefix defeats that judgement after construction.
3. `prefixes` and `base_url` are set by the code that builds the client (a constructor argument and an attribute), not by a remote party; the risk is a misconfigured or compromised caller, not an external attacker.

## Facts (HIGH)
- Head fetched via refs/pull/656/head = dc312fda; 1 commit; contains current main; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +96 -2: `field_agent/field_client.py` (a scheme and host check in `__init__`, a scheme check on the full request URL in `_call`), `tests/test_field_client_scheme.py` (+88, 31 cases).
- Baselines unmutated: new file 31 passed; whole field-agent suite 237 passed, 1 deselected (the environment-baseline test that fails on main too).
- MEASURED on the head: `c = FieldClient("http://127.0.0.1:8080", ..., opener=recorder); c.prefixes["sentinel"] = "@evil.example"; c.check("act")` makes the opener receive `http://127.0.0.1:8080@evil.example/check`, whose host is `evil.example`. The `x-field-auth` header, when a secret is set, goes there over http. The PR's test `test_a_prefixes_override_cannot_turn_the_request_into_another_scheme` asserts only that the scheme stays http(s) and that the call went through; a host pin (my mutant H1) makes that test fail, so the suite currently ENCODES the permissive behaviour.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| construction refuses a non-http(s) or host-less base URL: check removed, http only, https only, no host check, case, ftp allowed, placed after the secret check (C1-C5, C7, C8) | 7 | 7 | 0 |
| file allowed at construction (C6) | 1 | 0 | 1 (near-equivalent: a host-less `file:///x` is still refused by the host rule; `file://host/x` is caught per request) |
| per-request scheme check: removed, allows file (U1, U3) | 2 | 2 | 0 |
| per-request check ordering (U4) and on the base URL only (U5) | 2 | 0 | 2 (EQUIVALENT: order is immaterial and a prefix cannot change the scheme) |
| per-request check is case-sensitive (U6, uppercase `HTTP://` refused at use) | 1 | 0 | 1 |
| the host pin I propose (H1) | 1 | 1 (it breaks the PR's own test) | 0 |
Totals counted from the table: 7+1+2+2+1+1 = 14 valid rows; killed 7+0+2+0+0+1 = 10; survived 4 (C6, U4, U5, U6); 1 further edit (U2) did not anchor and is not counted.

## Findings
- F-R656-1 MEDIUM (measured): `prefixes["sentinel"] = "@evil.example"` redirects a request, and the shared secret with it, to another host; the per-request check is scheme-only. Pin the host to the base URL's host (refuse otherwise as unreachable) and change the PR's last test to assert the refusal. If the coordinator rules the prefixes argument trusted, say so in the module docstring and rename the test.
- F-R656-2 LOW (U6): an uppercase `HTTPS://Estate.Example` base builds (tested) but is never used in a call by any test; the per-request check lowercases correctly today, unpinned.
- C6, U4, U5: equivalent or near-equivalent, listed for completeness.

## Conditions
1. A ruling on F-R656-1: pin the host (recommended), or document `prefixes` as trusted and re-title the test.
2. GX10 16/16 and CI on this head.
