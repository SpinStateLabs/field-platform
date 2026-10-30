# C-586: review of PR 330 (guarded operator pair, C-511 slice 1), Lane 10

Reviewed: PR 330 head f09efe7 (`fix/guarded-operator-pair-c511`, builder Lane 1; new `field_core/guarded_operator.py`, `clients.py`, lifecycle `PerRequestAuthClient`, kill-switch CLI, five receiver drift tests; 12 files, +616 -67; one commit on b929f12). This implements section 3-4 of my note 20261102-2000-design-credential-on-reads.md. Probe: 20261103-1700-design-c586-guarded-client-probe-pr330.py (20 request shapes through the lifecycle client), my three C-491 probes, an independent route enumeration of the four receivers, 6 own mutants.

VERDICT: PASS WITH ONE CONDITION on f09efe7. The mechanism is right: the pair is attached only to a (method, path) of the target's table, every table matches its receiver, my three red probes are green, and every mutant goes red. The condition is a merge conflict with PR 318 on the same constructor (below). Confidence HIGH (run).

## ASSUMPTIONS
1. A route that reads the pair is one with `op_health.guard`, or one whose handler reads the pair itself (the PR names ledger `POST /events` and registry `PATCH /agents/{id}`).
2. The shared secret on every request is intended (perimeter), the pair on guarded writes only.

## Objections first (where the design could fail)
1. A guarded write missing from a table loses its identity and fails 401 under ENFORCE: an availability failure that appears on the estate, not in unit tests. Mitigation exists (drift tests, both directions); verified independently below.
2. The table is regex on the decoded path: `/tokens/` (trailing slash), `//tokens`, `/TOKENS` do not match, so such a write goes out WITHOUT the pair (fails closed: 401, never leaks). Fail-closed is the right direction. Callers use hard-coded paths, so none hits it today. MEDIUM-LOW.
3. The route tables are in field-core while the receivers own the routes: a route added to a receiver and not to the table is caught only if that receiver's drift test runs (it does: one per receiver, plus the non-vacuity test).
4. Redirects: with `follow_redirects=True` the guarded write and BOTH headers (the pair and the shared secret) followed a 307 to another host in my probe (second request to `elsewhere.invalid` carried them). Default is False and no call site enables it, so latent; the constructor does not force it. LOW-MEDIUM.
5. An absolute URL to ANOTHER host: the pair is withheld (good, probe) but the shared secret is still sent (`perimeter_headers()`), as before this PR. No call site passes an absolute URL. LOW.
Steelman: the previous state (the pair on every request, reads included) was the larger exposure; this change cuts it to four write families without a behaviour change for the receivers.

## Results (the card's questions)
- Route tables vs receivers (independent enumeration: I built each real app and listed every route with its dependencies, then searched each handler for operator-pair use): registry `POST /agents`, `POST /agents/{id}/attest`, `PATCH /agents/{id}` (handler reads the pair itself); ledger `POST /events` (`admit_ledger_event`), `/export`, `/rotate`, `/hold`, `/hold/release`, `/retention/apply`; delegation `POST /tokens`, `POST /tokens/{id}/revoke`; kill-switch `POST /kill/{id}`, `/kill/domain/{domain}`, `/revive/{id}`, `/drill/{id}`. Each table equals the receiver's set; nothing is missing; the other writes (`/operator/verify-hash`, `/discover`, `/introspect`, `/oauth/introspect`, `/heartbeat/{id}`) do not read the pair. The builder's two judgement calls (ledger `POST /events`, registry `PATCH`) are correct.
- Reads: `GET` of the same path, `GET /health?next=/tokens`, other methods (`PATCH`, `DELETE`) on a guarded template: no pair, secret present. HIGH.
- Query string and fragment on a guarded write: pair present (path without query is what is matched). Lower-case method: pair present. Encoded slash in an id, dot segment: no pair (fail closed). Another service's guarded path (`/kill/a1` sent to the delegation client): no pair.
- Base URL with a path prefix: the pair is attached for a request that httpx merges into a guarded path under the prefix and withheld for the doubled-prefix path. Correct.
- The three red probes of the C-491 note: now green (5 passed, including the two controls).
- Lifecycle client constructor and `trust_env`: this PR leaves `trust_env` at its default (a proxy-listener probe on the PR head: proxy hit, secret in clear), i.e. the exposure that PR 318 fixes. Both PRs rewrite `PerRequestAuthClient.__init__` (PR 330 adds `guarded_routes`, PR 318 forces `trust_env=False`): they CONFLICT textually. FIRST MERGED WINS; the second must combine.
- Mutants of mine, each red: pair on every request (16 failed), delegation revoke entry misspelled (10), `fullmatch` to `match` (5), method ignored (11), ledger `POST /events` dropped (2), foreign-origin check removed in the lifecycle client (1).
- Suites on the head: field-core, lifecycle-manager, kill-switch, agent-registry, delegation-authority all ran clean (no failure reported); the new and changed test files: 12 + 9 + 2 + 2 + 2 + 2 + 34 passed. Sealed-ledger whole suite not run here (only its new drift test: passed). Whole tools suite: NOT run to green (no full workspace install here).

## Findings
F-C586-1 MEDIUM-LOW (merge): whichever of PR 330 and PR 318 merges second must carry both changes. The combined constructor: `def __init__(self, *args, guarded_routes: Routes = (), **kwargs): kwargs.pop("trust_env", None); kwargs["follow_redirects"] = False; self._guarded_routes = guarded_routes; super().__init__(*args, trust_env=False, **kwargs)`. Add one test that builds the client with a proxy listener and `guarded_routes` set and asserts zero hits.
F-C586-2 LOW-MEDIUM: force `follow_redirects=False` in that constructor (objection 4); pin with the redirect stub used in my probe.
F-C586-3 LOW: for a URL on another origin send nothing, not the perimeter secret (objection 5): `perimeter_headers()` only when the origin matches the client's base URL.
F-C586-4 INFO: the other roughly 25 outbound clients still call `auth_headers()`; they hold no operator identity today (only the four identity-holding services do), so the pair does not ride them. The planned lint (`auth_headers()` outside field-core is a finding) is the closure; no card yet that I can see in this note's scope.

## What I did NOT do
Did not run the sealed-ledger whole suite or the whole tools suite. Did not test the kill-switch CLI against a live receiver. Did not check the GX10 or any estate (UNVERIFIED there, as the card says). Did not read the builder's own mutants beyond running six of mine. Did not edit the PR.
