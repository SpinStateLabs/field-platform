# Review R-PR857-eb08bb6: PR 857 (ssl-fp role agents: five manifests, agent and skill files, provisioning `--only`, key_intake.ps1, ENV_ID; rebuild of PR 541)
Head reviewed: eb08bb6b5ed339e0fb881794cbdcfdec122b033a (2 commits: 8260a425, eb08bb6b). `git merge-tree` against main is clean (tree 58e470ae).

## VERDICT: PASS WITH CONDITIONS (the code and tests are sound; one docs contradiction, one time-bomb, one ordering flaw in the key script; Don's decisions listed)

## Checks (HIGH, run by me)
1. Identity: both commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/` (the workflow is left out, as the PR says).
2. Public-repo scan of all changed files: the only IPs are 192.0.2.10 (documentation range, the five manifests' `endpoint:`) and 127.0.0.1 (the test); no private-range address, key shape, private-key block, password or email found. B1 and B2 of the PR 541 BLOCK are closed.
3. Tests on head: test_provision_wrapper 16 passed (3m45s); tools/tests/test_start_role_session.py 5 passed.
4. Code read: `ROLE_AGENTS` (five entries, domain engineering, never "merge pull request"), `ALL_AGENTS`, `selected_agents(only)`: no `--only` gives exactly the two original agents (a bare run is unchanged); `--only` gives the named ids once each in table order; an unknown id is a ValueError and `main` refuses with exit 2 "nothing sent" before the proxy check. The five manifests are identical apart from the role comment, description and one scope line (diffed). Scopes carry no merge, deploy or push-to-main action; spend cap 25 USD/day marked PROVISIONAL.
5. Ids cross-checked: the agent ids and env id in start_role_session.py and the docs table match; the old env id appears nowhere on the head.
6. key_intake.ps1: parses with no errors (PowerShell parser; NOT executed: it reads the clipboard and writes to the user profile). Read: key shape per kind; baseline fingerprint so a key already on the clipboard is not taken; empty file then owner-only ACL then the key; `.prev` copy gets the ACL before truncation and is restored if icacls fails; clipboard cleared after the write; nothing prints the key (status, 8-hex fingerprint, path only).
7. Mutants on tools/provision_ssl_agents.py, 9 run, 9 killed (counted from table; selected with `-k`). Source restored after each.
| # | Mutant | Result |
|---|---|---|
| M1 | default selection returns ALL_AGENTS | killed |
| M2 | an unknown `--only` id silently ignored | killed |
| M3 | `--only` order follows the command line | killed |
| M4 | `main` ignores the selection | killed |
| M5 | a role agent gets domain finance | killed |
| M6 | a role agent's `never` action changed | killed |
| M7 | `ALL_AGENTS` drops the role agents | killed |
| M8 | red-team always added to the selection (weak mutant) | killed |
| M9 | unknown-id check made case-insensitive | killed |

## Conditions
### C1 (MEDIUM): the docs contradict the manifests this PR adds
docs/ROLE-AGENTS-TEAM-ACCESS.md:3 says the "FIELD half" is "provisioned on the GB10 estate" and that tokens expire 30 days from mint; the five manifests are headed "DRAFT 2026-11-04, not provisioned, not applied", the `ROLE_AGENTS` comment says the same, and the default provisioning run excludes them. Both cannot be true. The line was already on main but this PR edits it and adds the manifests that contradict it. State which: either say "not yet provisioned; run `provision_ssl_agents.py --only <id>`" or remove the claim. (Estate-status wording in a public file is also the repo's own rule.)

### C2 (MEDIUM): delegation expiry is 2026-12-06 in all five manifests, 30 days from today (2026-11-06)
The tool's own check (test_provision_refuses_a_ttl_that_outlives_the_manifest_expiry) refuses a mint whose TTL outlives `delegation.expiry`, and the engine refuses a lapsed expiry. So `--only` with the default 30-day TTL is at the edge today, and after 2026-12-06 every role agent's provisioning fails until the manifests are edited. Either bump the date (Don decides the lifetime) or document that the run needs `FIELD_TOKEN_TTL_DAYS` below the remaining days. Not run: an actual provisioning against the estate (no estate here).

### C3 (LOW): key_intake.ps1 checks `-EnvironmentId` only after the key is stored
The identifier check (`^[A-Za-z0-9_-]{1,64}$`) sits in the verify block, after the key is written and the clipboard cleared; a bad id throws "refused" while the key is already on disk. Move it to a `ValidatePattern` on the parameter so nothing is read or written. No PowerShell test covers the script (not verified).

## Decisions that are Don's (carried from the PR 541 review; not defects of this PR)
Organisation, workspace (`wrkspc_...`), environment and agent ids in a public repo (docs and start_role_session.py; the PR says the agent ids were already public on main; whether the repo is public is not in my sources); the missing WIF workflow; who may dispatch a billing workflow; PR size.

## Observations (LOW)
- `.prev` is overwritten on every `-Replace`: the second rotation destroys the first previous key.
- Kill-switch endpoint in the manifests is `http://approver:8014/...` marked PROVISIONAL; not checked against a real service.

## Not verified
Provisioning against a real estate; running key_intake.ps1; manifest validator output (the PR reports VALID_WITH_WARNINGS; I did not re-run it); CI and GX10 16/16.

## Conditions to reach PASS
C1 and C2 (and C3 if cheap) in a new commit; identity re-check of the new head.
