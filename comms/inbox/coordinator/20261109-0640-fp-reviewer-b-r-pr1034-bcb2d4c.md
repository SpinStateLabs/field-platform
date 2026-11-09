# Review R-PR1034-bcb2d4c
**VERDICT: PASS** for head bcb2d4c2a6a7db46d655169c2c2899f08c8378f4 (S12-22, claude-approver: no cleartext http estate URL with a secret_file)

Reviewer: fp-reviewer-b. Independent (did not build this PR).

## Checks
| Check | Result | Confidence |
|---|---|---|
| Head equals PR head | yes | HIGH |
| Author and committer | Don Hagell 13129187+dhagell noreply, 1 commit | HIGH |
| Files | config.py (+16), README.md (+4/-1), docs/ENVIRONMENT.md (7 cite rows), tests/test_approver_estate_url_cleartext.py (+82); 0 under .github/ | HIGH |
| Secrets / estate addresses | none in added lines (test hosts are documentation ranges and `.test` names) | HIGH |
| Behind main | 15 commits, `merge-tree` clean | HIGH |
| Moved ENVIRONMENT.md cites into claude_approver/config.py | covered by the environment-anchor lint | HIGH |
| Lints (boundary-echo, blindspots, http-env-proxy, no-line-cites, environment-doc, environment-anchors) | 299 passed | HIGH |
| New tests | 28 passed | HIGH |
| Full claude-approver suite | 393 passed | HIGH |

## Coverage of the secret path (code read)
`Estate.headers()` (core.py:217) returns the perimeter secret only for a routed entry, and an entry is routed only when it names an `estate_base_url` (core.py:228). The new check runs whenever both `secret_file` and a base URL are present, so every path that can send the secret passes it. An entry without `estate_base_url` ignores `secret_file` and uses the env URLs with `auth_headers()` (not changed here). HIGH.

## Hostile-URL probe on the head (`parse_agent_map` with a secret_file; httpx host shown for comparison)
| URL | Approver | Note |
|---|---|---|
| `http://evil.example\@localhost`, `http://localhost\.evil.example`, `http://127.0.0.1\.evil.example`, `http://evil.example:80\.localhost` | refused | credentials rule, or the suffix does not match |
| `http://2130706433`, `http://0x7f.1`, `http://127.1`, `http://0.0.0.0`, `http://[::]` | refused | numeric spellings are not parsed as loopback |
| `http://[::ffff:8.8.8.8]` | refused | IPv4-mapped non-loopback |
| `http://[::ffff:127.0.0.1]`, `http://127.0.0.1.` | usable | mapped loopback is fine; the trailing-dot IP is a name in DNS, but an all-numeric top-level domain cannot exist (MEDIUM, general knowledge) |
| `http://evil.example\u3002localhost` (ideographic full stop), `\uff0e` | refused | httpx would read these as `evil.example.localhost`; refusing is the safe side |
| `http://evil.example\.localhost`, `http://evil.example\.test`, `http://evil.example%2f.localhost`, `%2e`, `%00` | usable | the host is not a valid hostname, but it ends in `.localhost` / `.test`, and httpx keeps the same string (no parser difference). Such a name cannot resolve to a public host (RFC 6761 reserved suffixes; MEDIUM, general knowledge) |
| `http://[::1]\.evil.example` | `parse_agent_map` raises `ValueError: Invalid IPv6 URL` | raised by the first `urlsplit` at config.py:204, which this diff does not touch (pre-existing) |
No bypass of the stated rule found. The rule itself ("or a `.test` / `.localhost` name") trusts the reserved suffixes: on a network whose resolver defines `.test` names, an `http://x.test` estate would carry the secret in cleartext to wherever that resolver points. That is the PR's documented choice, not a defect.

## Mutants (scratch copies, tests/test_approver_estate_url_cleartext.py)
| # | Mutant | Result |
|---|---|---|
| N1 | `lower()` dropped | SURVIVED (equivalent: `urlsplit().hostname` already lowercases) |
| N2 | trailing-dot strip dropped | KILLED |
| N3 | loopback becomes private | KILLED |
| N4 | `localhost` literal dropped | KILLED |
| N5 | `.localhost` suffix dropped | KILLED |
| N6 | `.test` suffix dropped | KILLED |
| N7 | suffix as substring | KILLED |
| N8 | suffix without the dot | KILLED |
| N9 | `localhost` as prefix | KILLED |
| N10 | every IP counts as loopback | KILLED |
| N11 | gate `scheme != "https"` | SURVIVED (equivalent: only http and https reach it) |
| N12 | gate ignores secret_file | KILLED |
| N13 | refusal echoes the URL | KILLED |
| N14 | gate removed | KILLED |
| N15 | secret_file not stripped | KILLED |
| N16 | README sentence changed | KILLED |
| N17 | refusal text changed | KILLED |
| N18 | missing hostname treated as localhost | SURVIVED (equivalent: an empty hostname is refused earlier) |

Totals: applied 18, killed 15, survived 3 (all equivalent), not applied 0. Baseline 28 passed.

## Optional LOWs (new PR, not conditions)
1. Validate the host against a hostname grammar (letters, digits, hyphen, dot) before the suffix match, so `evil.example\.test` and `%00` forms are refused instead of accepted (defence in depth; no exploit found).
2. Catch the `ValueError` from `urlsplit` at config.py:204 so one malformed bracketed URL does not abort the whole map load (pre-existing; I did not check what the caller does with the exception).
3. Add a test for a hostile-spelling set (backslash, percent forms) so the current behaviour is pinned either way.
