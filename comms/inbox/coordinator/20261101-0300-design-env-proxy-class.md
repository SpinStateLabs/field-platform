# Design note: environment proxy and secret-carrying HTTP clients (Lane 10)

Scope: main 3ee2e5d and comms queue as fetched. Probes: probe3.py (local listener plays the proxy; made-up header value, no real secret, no estate address) and count_sites.py (AST count). Both run in a scratch directory with only `httpx` installed.

## 0. Status correction
D-13 (tasks/DECISIONS-FOR-DON.md:43-45, PROVISIONAL, MEDIUM) and cards C-56 (shared constructor plan) and C-57 (lint) are still OPEN in comms/TASK-QUEUE.md:60-61. Result on main: 59 non-test `httpx.<call>` sites by AST count, 1 sets `trust_env=False` (core llm.py:203), 58 do not (HIGH, count_sites.py). urllib sites already use an empty ProxyHandler (alerts.py:467, field_client.py:80, canary.py:318, estate_kill_watcher.py:78, renew_token.py:398, estate_probe.py:289) except five fixture or tool sites (upgrade_flow.py:77, signing_fault.py:59, check_edge_block.py:55, check_rows.py:44, fly_identity_check.py:188; HIGH those sites exist, MEDIUM which carry a secret: not read).

## 1. Objections to "fix with a factory plus a lint" (C-56/C-57 as written)
1. A call-site lint over `httpx.Client(` misses a subclass: `PerRequestAuthClient(httpx.Client)` (lifecycle-manager api.py:87) is built by its own name. Same for `from httpx import Client`, `import httpx as h`, `httpx.Client(**kw)` where kw carries trust_env, and the `httpx2` package name the constraints file lists. These are the "spelling classes" that made the bind checker whack-a-mole: the lint must be written against the invariant, not against `httpx.Client(` text.
2. `trust_env=False` as a literal is checkable; `trust_env=flag` is not. A variable must be a failure.
3. Test doubles: injected `client=` parameters (clients.py:262, core.py:336 `http or httpx.Client(...)`) bypass the factory by design; the lint must flag the DEFAULT construction, not the injection.
4. Proxy support may be wanted later (Fly witness, Anthropic calls from a corporate network). `trust_env=False` silently breaks that; the explicit-setting design (a named env var read once) must exist before the lint turns it mandatory, or a later operator "fixes" it by deleting the lint.
5. NO_PROXY in compose only (the D-13 alternative) protects one deployment and nothing else (field-agent runs outside compose).
Steelman for doing nothing yet: the coordinator's read-only check found no proxy variable on the estate host or running containers (D-13; MEDIUM: docker exec errors were ignored; Fly not checked). Exposure needs a variable that today is absent. Cost of the fix is mechanical but touches 58 sites in 17 packages (count_sites.py).

## 2. The invariant
Every HTTP client that is built in non-test code and may carry a credential (any of `x-field-auth`, `x-field-operator-key`, an API key, a token) is built with `trust_env=False` and `follow_redirects=False`, through ONE constructor in field-core, unless the site is named in an allowlist file with its reason. The same for urllib: every opener includes `ProxyHandler({})`. A proxy is used only if a single named setting (for example `FIELD_EGRESS_PROXY`) says so, read by the constructor.

## 3. Probe (current state, RED)
probe3.py, run on this container:
- default client (the repo's construction, clients.py:275 style): proxy_hit=True, secret_in_clear=True
- `trust_env=False` (llm.py:203 style): proxy_hit=False
- `follow_redirects=False` only (witness.py:149 style): proxy_hit=True, secret_in_clear=True
So witness.py:149/154/346 and core.py:336 do NOT close the class by setting only redirects (HIGH, probe). https targets show a CONNECT only to the proxy; the content is protected unless the proxy terminates TLS (general knowledge, MEDIUM): rank plain-http internal calls first.

## 4. Recommendation (one structure, three parts)
1. Constructor `field_core.http.client(**kw)` and `async_client(**kw)`: `trust_env=False`, `follow_redirects=False`, timeout required, optional `FIELD_EGRESS_PROXY`. It exists in embryo: `make_http_client` (llm.py:175). Move it, do not write a second one.
2. Lint (AST, same family as tools/topology_lint.py) that fails on any non-test: a call of the library's Client/AsyncClient/get/post/put/patch/delete/request/stream/head reached by ANY import spelling (`import httpx`, `import httpx as x`, `from httpx import ...`, `httpx2`); a class that subclasses the library's client without calling the constructor with `trust_env=False`; a `trust_env=` that is not the literal False; a `urlopen`/`build_opener` without `ProxyHandler({})`. Allowlist file: path, line-independent symbol, reason. Cost: one file, about 80 lines, plus the allowlist.
3. One parametrised test per client class with a proxy variable set to a local listener asserting zero hits (probe3.py is the template, 30 lines).
Order: 1 then 3 for the field-core clients (LedgerClient, RegistryClient; every service's ledger and registry call passes through them), then the lint, then the 58 sites in groups by package, internal plain-http first.

## 5. What a builder card should pin
- A client built by each class, with the proxy variable set, never reaches the listener (red on main today).
- The lint goes red on each spelling in objection 1 (subclass, aliased import, `from` import, variable `trust_env`) and green on the factory.
- Mutants: remove `trust_env=False` from the factory; allowlist an entry without a reason.

## What I did NOT do
Did not set a proxy on any real process or host. Did not read the five urllib sites that carry no ProxyHandler to see whether they send a secret. Did not check Fly or any running container (D-13 already says "I do not know"). Did not open the sibling `requests`/`aiohttp` question: grep found no import of either in non-test code (HIGH for that grep). Did not merge or build a PR. Delivered in chat if the push is refused.
