# Design review: PR 295 (C-57 lint) against the evasion spellings (Lane 10)

Head reviewed: the PR branch `test/http-env-proxy-lint-c57`, one commit (tests only: tools/tests/test_http_env_proxy_lint_c57.py and http_env_proxy_allowlist.txt). Probe: 20261101-0610-design-c57-lint-evasion-probe-test.py (22 cases; `C57=<checkout>/tools/tests python -m pytest -q`). The PR's own 21 tests pass (HIGH, run).

## 0. Verdict on the design
Better than the plan I criticised in my note 20261101-0300: it resolves import aliases and `from` imports (test_http_env_proxy_lint_c57.py:51-62), treats `trust_env=<anything but literal False>` as a finding (:97-99), flags `urlopen` always and any `build_opener` that lacks an empty `ProxyHandler({})` (:100-105), and the allowlist must equal the scan in both directions (:121-125). PASS for what it states. Confidence HIGH.

## 1. Objections first (where it can still be bypassed)
1. A subclass of the client is never flagged: the scan matches only the library's own call names. `PerRequestAuthClient(httpx.Client)` (services/lifecycle-manager/src/lifecycle_manager/api.py:87) is built at api.py:117 and :128 with the perimeter secret and operator pair, and neither site is flagged or allowlisted (HIGH: the PR's scan passes on the repo, and a probe of the subclass shape is unflagged). This is a LIVE miss, not hypothetical: two secret-carrying clients escape the lint. `super().__init__()` inside a subclass is also unflagged.
2. A class or local alias of the callable (`K = httpx.Client; K()`) is unflagged: alias resolution is by import name only. LOW-MEDIUM (plausible refactor, none on main).
3. Other libraries and package names are invisible: `httpx2` (the name the constraints file lists, so a future import swap), `requests`, `urllib3`, `aiohttp`. Grep found no such import in non-test code today (MEDIUM, earlier grep), so this is a future-regression gap.
4. Adversarial shapes pass: `functools.partial(httpx.Client, ...)`, `getattr(httpx, 'Client')`, `importlib.import_module`, `from httpx import *`, setting `trust_env = True` after construction. LOW: a lint cannot stop a determined author; a review catches these.
5. Placement: `_is_test_file` skips any file under a directory named `build`, `dist`, `venv` or `tests`, anywhere in its path, and any file named `test_*.py` (:30-31). A real module in such a directory is never scanned. Probe red; no such file exists on the branch today (HIGH for the find, nothing hidden now).
6. A file the scanner cannot parse raises SyntaxError and aborts the whole test (red for everyone) instead of reporting that file. Fail-closed, but the message will not name the cause; LOW.
Handled (probe green): `trust_env` from a variable, `ProxyHandler(None)`, a `ProxyHandler` built apart, an aliased import, a `from` import, `**kw`, every top-level Python directory is in SCAN_ROOTS.
Steelman: items 3-6 are bounded by the allowlist-equals-scan rule plus review; only item 1 is a defect in what the PR claims ("every non-test client").

## 2. Recommendation
1. Fix item 1 before merge: track classes whose bases include a library client (resolve base through `dotted()`), and flag (a) an instantiation of such a class and (b) a `super().__init__` / `__init__` call in it lacking `trust_env=False`. Add the two lifecycle sites to the allowlist or, better, give `PerRequestAuthClient` a constructor that sets `trust_env=False`.
2. One line each: extend the call-name set to `httpx2`; make a flagged name list (`requests`, `urllib3`, `aiohttp`) a finding on import in non-test code unless allowlisted; drop `build` and `dist` from SKIP_DIRS or restrict them to the repo top level; wrap `ast.parse` to name the file.
3. Pin: the probe cases above as tests (green after the fix).

## What I did NOT do
Did not edit the PR or push to its branch. Did not run the PR's lint on a different Python version. Did not check whether `PerRequestAuthClient` callers pass a transport that makes the proxy moot (it does not at api.py:117/128 as read). Did not review the allowlist's per-site entries beyond the first 40 lines. No docker or compose.

## Request to the coordinator: more work for Lane 10
Lane 10 has no open card. Delivered so far: bind-source checker, operator key on the console, recurring classes, env-proxy class, this review. Candidates, in my order of preference, each needing a card or a go: (a) private-address spelling class (field_client.py `_private_host` and the C-197/C-213 reports): verify on main with an enumeration probe; (b) error text that echoes a body or value (C-40, C-64, C-376): sweep with an AST probe; (c) credential sent on reads as well as writes after PR 288 merges (console and service clients); (d) re-run the 33-case bind-source probe once the allowlist card lands. Reply by a card or inbox file; I cannot be reached by SendMessage and will pick (a) if no answer arrives.
