# Reviewer report: PRIORITY 1 MAIN-RED, PRs 543, 546, 589 (the C-57 proxy-lint failure from tools/start_role_session.py, added by #532)
Reviewer: ssl-ff-reviewer-4. Claimed target PR543@caee3897; I also read and ran PR 546 and PR 589 because the claim asks which of the three should land. All runs UNVERIFIED (cloud, no GX10). All three heads are one commit on origin/main 97dcfec1 (the current tip), so each merges cleanly (`merge-tree` returns a tree for all three) and each is exactly "main plus its change".

RECOMMENDATION: land PR 546 (head b963407aec71). Do not land 543. Do not land 589 as submitted.

## What is red on main (run by me)
`tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist` fails on origin/main (1 failed, 101 passed): `tools/start_role_session.py::call::urllib.request.urlopen` is a new secret-carrying call (it sends the workspace API key in `x-api-key`) that reads the process proxy environment and is not on the allowlist. The lint's intent (PRs 295, 330, 431 and the C-496 / C-605 notes): a call that carries a secret must not read the proxy environment, and the allowlist is for sites not yet migrated, not for new secret-carrying ones.

## Objections first
1. The smallest diff is not the smallest correct change: a fix that only turns the lint green can still leave the leak the lint exists to prevent. I therefore measured the leak per option, not only the lint result.
2. A tool that sends a workspace API key from a developer machine is hard to test against the real host; the three heads differ in whether they test at all (546 does with local listeners; 543 and 589 add no test).
3. Priority-1 pressure favours the 1-line allowlist (543); steelman: it is the fastest green, it is reversible, and the real fix can follow. Against it: it records the unsafe behaviour as accepted, in a file whose own header says it is for unmigrated sites.

## Verified (run by me)
Lint file on each head: 543 102 passed; 546 107 passed (its 5 new tests included); 589 102 passed. So all three turn main green.

Behaviour probe (a throwaway script with loopback servers and a made-up key; each opener built exactly as the head builds it; the urllib global opener reset between probes):
| Head | request went through the proxy named in HTTP_PROXY | key reached the target after a 302 redirect |
|---|---|---|
| 543 (allowlist, `urlopen` kept) | YES | YES |
| 589 (`build_opener(ProxyHandler({}))`) | no | YES |
| 546 (`_NoRedirect` + `ProxyHandler({})`) | no | no |
So 543 leaves both leaks, 589 closes the proxy leak and leaves the redirect leak (urllib turns a 302 on a POST into a GET and forwards the other headers, including `x-api-key`), 546 closes both (HIGH, run).

## Mutants on PR 546 (mutations of tools/start_role_session.py; scratch worktree on its head; baseline 107 passed in test_start_role_session.py + the lint; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| R1 | redirects followed (default handler) | 1 failed | yes |
| R2 | `_NoRedirect` returns a follow-up request | 1 failed | yes |
| R3 | proxy environment read (no `ProxyHandler({})`) | 2 failed | yes |
| R4 | `call()` back to `urlopen` | 3 failed | yes |
| R5 | `ProxyHandler` with a real proxy mapping | 1 failed | yes |
| R6 | key header renamed | 1 failed | yes |
| R7 | request timeout removed | 107 passed | NO |
| R8 | `API_BASE` changed | 107 passed | NO |
| R9 | key echoed in the error exit | 1 failed | yes |
| R10 | missing key no longer exits | 1 failed | yes |
Totals counted from the table: 10 mutants, 8 killed, 2 survived (R7, R8). R7 and R8 are not behaviours PR 546 claims (the timeout and the base URL); I ran them against the two files only. No test exists in 543 or 589 to mutate against.

## Findings
- F-MAINRED-1 (543, HIGH for the choice): allowlisting records an unsafe site as accepted and leaves both leaks (table). BLOCK on caee3897 as the fix.
- F-MAINRED-2 (589, MEDIUM): leaves the redirect leak (table); adds no test; and its commit d08e70c0 has author and committer `noreply@anthropic.com`, not the Don Hagell identity (13129187+dhagell@users.noreply.github.com) the repository requires (543 and 546 carry the Don Hagell identity and a Sonnet 5.5 trailer). Not recommended as submitted.
- F-MAINRED-3 LOW (546): R7, R8 unpinned (timeout and base URL).
- F-MAINRED-4 note for the coordinator, not part of any of the three: tools/start_role_session.py on main holds a Managed Agents agent id and an environment id as literals (6 hits for `agent_01`/`env_01`); they are identifiers, not credentials, and are not in the rule's list (estate address, flag value, build id, deploy status, credential), so I do not call it a violation; the owner should decide whether they belong in a public file.

## Verdicts, each naming its head
- PR 546 @ b963407aec71: PASS WITH CONDITIONS. Conditions: CI green and the full GX10 run on this exact head rebased on current main (it changes a tool and adds tests, so the docs-only light run does not apply); after landing, close 543 and 589 (the coordinator closes PRs).
- PR 543 @ caee3897e026: BLOCK (as the fix; see F-MAINRED-1).
- PR 589 @ d08e70c0363c: BLOCK as submitted (identity F-MAINRED-2; redirect gap). If a smaller change than 546 is wanted, the minimum that keeps the C-57 intent is 589's opener plus a no-redirect handler, which is what 546 already is.
Not run by me: CI, GX10.
