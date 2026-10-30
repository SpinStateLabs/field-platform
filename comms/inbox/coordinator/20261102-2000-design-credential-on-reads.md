# Design note: the operator pair on reads (Lane 10, C-491)

Scope: main after PR 288 and PR 299. Probe: 20261102-2000-design-credential-on-reads-probe-test.py (made-up values; `FIELD_REPO=<checkout> python -m pytest -q`).

## 0. Correction
"After PR 288" the console is CLOSED: `hdrs(withOperator)` attaches the operator pair only when the caller says so (console.html:778-785), reads, the stream and the export carry the perimeter secret alone, and guarded fetches use `redirect: "error"` (:836). The open part is the SERVICE side: `field_core.authn.auth_headers()` merges the service's own operator pair into every request (operator_auth.py:347-354 docstring says so: "every internal client carries its service identity once the env is set"). Confidence HIGH (code, probe).

## 1. Objections first (failure conditions)
1. Least privilege: a read, and a ledger or registry call that authenticates by other means (the ledger by a signed caller key, F2b), carries a key that only guarded writes at the receiver check. Every internal hop holds a bearer secret it does not need. Probe red (3 cases).
2. Compounding with an open class: while the proxy lint's migration (C-487) is incomplete, an ambient proxy variable would carry that pair in clear (note 20261101-0300). The two findings multiply; the second is the one with the fix in flight.
3. Receiver logs: any service or middlebox that logs request headers for debugging records the key for every read, i.e. at a far higher rate than for writes. NOT verified (no service log read; "I do not know").
4. Rotation blast radius: a key that rides every request is exposed at every request; compromise of any internal proxy or log reveals it. The `svc-*` pairs are only the four identity-holding services (registry, delegation, kill-switch, lifecycle: compose comments), so the set of keys at risk is small. MEDIUM.
Steelman for leaving it: the pair is a service identity inside one estate network, the shared secret already rides every call, per-request header reads were built on purpose (C-4, key rotation R3), and the guard on a write needs it present. A path allowlist adds a table to maintain per receiver.

## 2. Callers (class and file)
- Attach the pair to everything (via `auth_headers()`): field-core clients.py (`_request_auth`, used by LedgerClient and RegistryClient, reads included), lifecycle-manager api.py (`PerRequestAuthClient.build_request`, every request to delegation and kill-switch, reads included), and the callers that build `httpx.Client(headers=auth_headers())`: spend-governor cli.py (11), conformance-sentinel cli/engine/governed, incident-replay, federation-broker cli, force-gateway api/cli, attestation-reporter, compliance-crosswalk, claude-approver core, field-agent `_transport.py`, sealed-ledger witness/cli. For the services that hold NO identity (every service not in the four above) `auth_headers()` returns the shared secret only, so those sites are harmless today and become the same finding the day an identity is configured. HIGH for the mechanism (grep count by file), MEDIUM for which are live (depends on env).
- Closed, the pattern to copy: `GuardedOperatorAuth` with an `is_guarded(method, path)` allowlist in kill-switch cli.py:139-161 (its `_perimeter()` docstring says why: `auth_headers()` "adds the env operator pair to every request, reads included"), delegation-authority cli.py, lifecycle-manager cli.py, tools/provision_ssl_agents.py, tools/renew_token.py, tools/estate_probe.py, field-agent canary.py; and the console proxy: the console forwards the HUMAN's pair only from `_operator_kw`, i.e. for guarded routes, and its own client carries `x-field-auth` only (probe green).

## 3. The closed rule
The perimeter secret may accompany every internal request. The operator pair is attached only to a request whose (method, path) is in the target service's guarded-route allowlist, by one mechanism: `GuardedOperatorAuth` moved to field-core, with the route table owned by the service that guards them. `auth_headers()` is split into `perimeter_headers()` (secret only) and the operator pair (reachable only through the guarded auth). Non-test code may not call a function that returns the pair outside field-core.

## 4. Recommendation
1. Move `GuardedOperatorAuth` and `is_guarded` to field-core; give each identity-holding service's outbound clients (LedgerClient, RegistryClient, lifecycle's PerRequestAuthClient) the guarded auth with the route table of its targets. Cost: a route table per target (registry, delegation, kill-switch, ledger), copied from the receivers' `operator_auth.guard` declarations so it cannot drift; a test per table that every guarded route of the receiver is in it.
2. Rename or restrict `auth_headers()` so a caller cannot get the pair by accident; keep a compatibility wrapper only until the ~25 sites are migrated.
3. Lint (the C-57 shape): in non-test code `auth_headers()` outside field-core is a finding, allowlist equal-to-scan.
4. Order: lifecycle and field-core clients first (the only identity-holding callers), then the rest by lint.

## 5. What a builder card should pin
The three red probe cases flipped; for each guarded route a write carries both headers and a read of the same service carries neither; mutants: attach the pair on every request; drop one route from a table.

## What I did NOT do
Did not read the receivers' guarded-route declarations to build the tables (a builder step). Did not check any service or proxy log (objection 3). Did not test the ledger append path, only a read, because the append needs a signer. Did not check Fly or any running estate. Did not edit source, merge or open a PR.
