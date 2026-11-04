# Reviewer report: PR 445 @307b1cf0 (lint: auth_headers() outside field-core is a finding, C-1149, B-19)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. Tests-only PR: tools/tests/test_auth_headers_outside_core_c1149.py (+229, AST scanner plus 27 tests) and tools/tests/auth_headers_allowlist.txt (+35).

## Verdict: PASS WITH CONDITIONS (head 307b1cf0ab81e0e65d805908f4c077cd38e697bf)
Conditions: C1 rebase on current main (PR base is 05942b98). I did the substantive part already: I checked out main 97dcfec1, overlaid this PR's two files, and the lint passed there (27 passed), so the allowlist still equals the scan on current main. In-flight PRs that migrate sites (467 and 468 in this lane's queue, others) will each need to delete their allowlist lines, in the same commit, or the lint turns red: the coordinator must sequence them (the lint is designed that way). C2 GX10 16/16 on the exact rebased head; C3 CI green. No blocking finding.

## Objections first
1. The allowlist is exact, not a ceiling: a PR that migrates a site and forgets to delete its line fails (stale entry); a PR that adds a site fails (new site). Merge order therefore matters: PR 467 (sentinel, 8 sites, in the allowlist as conformance-sentinel cli/engine/governed lines) and PR 468 (approver `Estate.headers`, one site, in the allowlist) each change allowlisted sites. Whichever lands second must be rebased and its allowlist lines removed (HIGH, read of the allowlist against those two diffs).
2. The scanner declares its own blind spots (docstring): `getattr(authn, "auth_headers")`, `importlib`, `self.authn.auth_headers()`, a wrapper function, inner-scope shadowing. A site written that way passes (HIGH, read).
3. It scans only non-test Python under packages, services, tools, plugins, integration, defence-shield; a top-level script outside those roots is invisible (HIGH, read of SCAN_ROOTS).
4. The count in the commit ("33 sites, 40 uses") matches the file: 33 non-comment lines, counts sum to 40 (HIGH, computed). My own `git grep auth_headers` on the head lists the same files, including the examples, the plugin template, field-agent `_transport.py` and all spend-governor CLI commands (HIGH, read; I did not recount every line independently).
5. `test_the_scan_is_not_blind` asserts at least 100 scanned files; if the repo is trimmed below 100 the control fails for the wrong reason (LOW, read).

## Scope and identity
2 files, 2 commits; author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH). No production code touched.

## Runs
Baseline: the PR test file 27 passed on the PR head; 27 passed on main 97dcfec1 with the two files overlaid. Mutants edit the scanner and selection code inside the test file one at a time; kill = the file fails; file restored (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| I1 | import aliases | plain imports not tracked | KILLED |
| I2 | import aliases | from-import `as` alias ignored | KILLED |
| I3 | import aliases | import-as alias ignored | KILLED |
| I4 | import aliases | relative imports treated as absolute | SURVIVED (LOW, F3) |
| X1 | star/assign | `import *` not flagged | KILLED |
| X2 | star/assign | local alias assignment not followed | SURVIVED (F2) |
| X3 | star/assign | assign alias never set | SURVIVED (F2) |
| V1 | value use | bare-name uses not flagged | KILLED |
| V2 | value use | attribute chain visited again after the flag | SURVIVED, EQUIVALENT (the inner `authn` name resolves to the module path, never the target) |
| V3 | value use | attribute use not flagged | KILLED |
| C1 | scope names | async functions not scoped | SURVIVED (F1) |
| C2 | scope names | class names not in the scope path | KILLED |
| C3 | scope names | only the innermost name kept | KILLED |
| F1 | file selection | conftest.py scanned | SURVIVED (LOW, equivalent in practice: conftest files sit in tests dirs that SKIP_DIRS already skips; I did not enumerate a root-level one) |
| F2 | file selection | plugins not scanned | KILLED |
| F3 | file selection | only packages and services scanned | KILLED |
| F4 | file selection | home exemption broken | KILLED |
| F5 | file selection | tests directories scanned | KILLED |
| P1 | problems | new-site finding disabled | KILLED |
| P2 | problems | stale-entry finding disabled | KILLED |
| P3 | problems | one extra use per site tolerated | KILLED |
| P4 | problems | a partly fixed site (count dropped) not stale | KILLED |
| P5 | problems | allowlist counts read as 1 | KILLED |
| P6 | problems | per-site counts collapsed to 1 | KILLED |

Counted from the table: 24 rows (import aliases 4, star/assign 3, value use 3, scope names 3, file selection 5, problems 6). KILLED 18, SURVIVED 6: V2 equivalent, F1 equivalent in practice, I4/X2/X3/C1 real but LOW. Kill rate on non-equivalent rows 18 of 22 = 82%. Per behaviour: import aliases 3/4, star/assign 1/3, value use 2/2 non-equivalent, scope names 2/3, file selection 4/4 non-equivalent, problems 6/6.

## Findings
- F1 LOW (HIGH, run): C1. No fixture puts a call inside an `async def`, so the reported function name for async sites is unpinned; the site is still found.
- F2 LOW (HIGH, run): X2, X3. `h = authn.auth_headers; h()` is tested only with a `>= 1` count; the alias-following code adds nothing the test can see, because the assignment's own value is already flagged. Either assert the exact count or drop the dead alias logic.
- F3 LOW: I4, a relative `from .authn import auth_headers` inside field_core is the only case and field-core is exempt.

## Not verified
Rebased run on 97dcfec1 with PRs 467/468 applied; CI; GX10; independent per-line recount of the 40 uses.
