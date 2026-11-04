# LANE O post-merge review (completes part of my MERGE 17 report): lifecycle CLI service-client guard test (C-1087) @ 40aec372

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Read-only mutant review of the one commit my MERGE 17 report left uncovered: 40aec372 (services/lifecycle-manager/tests/test_lifecycle_service_client_guard_c1087.py, +55, tests only), at the batch tip 40aec372. Author and committer Don Hagell numeric noreply (read from `git show`). `git fetch origin main` first; neither the test file nor lifecycle_manager/cli.py changed on main after 40aec372 (`git log origin/main` on both shows 40aec372 and older commits only). Still NOT covered: field-core guarded_operator.py (merged earlier, MERGE 12; "I do not know").

Objections first: (1) the test pins two controls (L2: `headers=_perimeter()`, L4: the pair on a guarded POST); the guard table `GUARDED_ROUTES` is checked on one guarded and one unlisted route of one service, so the service scoping of the table is barely pinned. (2) The test sets `FIELD_SHARED_SECRET` but no operator environment pair, so the docstring rule "never `authn.auth_headers()`, it adds the env pair to every request" cannot fail here. (3) Four of my 21 mutants are outside the commit's claim (the base URL and the timeout); they are pre-existing code and are reported only as information.

Baseline (unmutated, measured): lifecycle-manager suite 269 passed. Survivor check ran the whole suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 a read carries x-field-auth and no operator pair (L2) | 7 | 6 | 0 | 1 |
| B2 the pair rides a guarded POST and not an unlisted one (L4) | 7 | 6 | 0 | 1 |
| B3 the client never follows a redirect (outside this commit's claim) | 2 | 0 | 1 | 1 |
| B4 the base URL comes from the service's variable, slash stripped, timeout 20 (outside the claim) | 5 | 0 | 2 | 3 |
| Total | 21 | 12 | 3 | 6 |

Totals counted from the table: 21 = 12+3+6; no invalid, no noapply.

Survivors, 6 = 2 real gaps in the commit's claim + 1 equivalent + 3 outside the claim:
Real gaps (in the claim):
- B1 `headers=authn.auth_headers()`: no operator environment pair is set in the test, so adding the env pair to every request is not detected.
- B2 an auth object built from every service's routes: the delegation client would send the pair on another service's guarded route; only one unlisted route is tried.
Equivalent:
- B3 `follow_redirects` argument omitted: httpx defaults to not following; the `True` mutant is killed by an older test (821f77d6's pin).
Outside the claim (pre-existing, unpinned by the whole suite):
- B4 base URL without `rstrip("/")`, with an appended `/`, and the default timeout changed to 2.0: all pass the whole suite.

Conditions: none blocking. Optional: set `FIELD_OPERATOR_ID`/key in the environment in the read test and assert no pair leaves; assert that another service's guarded route (for example registry POST /agents) carries no pair on the delegation client. Confidence: HIGH on counts, MEDIUM on classification. Token/cost: I do not know.
