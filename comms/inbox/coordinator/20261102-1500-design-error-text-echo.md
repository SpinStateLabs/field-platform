# Design note: error text that echoes a body or a value (Lane 10, C-490)

Scope: main (a9dc4f3 per the card is not repeated here; checkout fetched at note time). Tools: 20261102-1500-design-error-echo-sweep.py (AST, `python echo_sweep.py <checkout>`), 20261102-1500-design-error-echo-probe-test.py (pytest, made-up marker, `FIELD_REPO=<checkout> python -m pytest -q`).

## 0. Correction
The class is not "a body is echoed". The harm needs a CHAIN: another service's body (or an exception built from it) becomes an exception message, a service then relays that message to ITS caller (HTTP 502/500 detail, a CLI line, a ledger or log record). Only the chain matters; a message that stays inside a trusted function is not a finding. The sweep's raw count (269 sites with exception or body text in a raise, an HTTPException, an error object or a CLI echo) is mostly benign: validation errors built from the service's own types. Confidence HIGH for the count (sweep), MEDIUM for "mostly benign" (a sample of 11 read, not all 269).

## 1. Objections first (failure conditions)
1. A body can carry a submitted secret back: the upstream service's 4xx/5xx text may include a value the caller sent (validation errors that quote the input). Echoed upstream, it lands in the next service's reply and in whoever reads it (the console shows `e.message` in the page; reports C-40 f4, C-64). Condition: an upstream that echoes input. MEDIUM (not shown on this estate; not tested).
2. Unbounded: a hostile or broken upstream can make the message arbitrarily large (probe: 5000 characters pass through whole). Log, ledger and UI cost, and room to smuggle data. HIGH (probe red).
3. Wording is a contract: services pattern-match error strings (the lifecycle `_body`, the "verbatim refusal text" docstring at lifecycle engine.py:432-438 says it intends to relay another service's words). Removing the echo changes a behaviour someone may rely on. MEDIUM.
4. Exception text from the transport (`str(exc)` of an httpx or urllib error) names the URL and may name a proxy or an address (it is the relay path of "registry unreachable ...: {exc}"). Not a secret, but an internal address surfaced to an API caller. MEDIUM.
5. A redactor is not a rule: agent-registry has `redaction.redact_text` (agent_registry/redaction.py:166) and the force-gateway has `scrub_secret` (api.py:124); each fixes its own sink. Same pattern as the host and bind classes: local fixes, no invariant.
Steelman: relaying the upstream's verbatim reason is useful to an operator debugging, and the replies are only reachable behind the perimeter secret. The cost of truncating and stripping is lost diagnostic detail.

## 2. The invariant
A message that crosses a service boundary (HTTP reply, CLI output, ledger record, log line) contains only: a fixed phrase, the upstream STATUS CODE, and identifiers the caller itself supplied. It never contains an upstream body, a header value, an environment value, or the unparsed text of a transport exception. A body may be written to a local debug log only after truncation and `redact`.

## 3. Findings (class and file:line; probe where marked)
1. field-core clients embed the upstream body: clients.py:302-304 (ledger append), :318, :334, :340, :369-371 (registry get), :394, :426 as `f"... returned {status}: {resp.text}"`. PROBE RED (marker passes through, 5000 characters pass through). HIGH.
2. Relays of those messages to a caller: kill-switch api.py:520, :536, :608, :689, :705, :739 (`registry unreachable ...: {exc}`), lifecycle api.py:464 (OSError text), sealed-ledger api.py:406-573 and delegation-authority api.py:163-387 (own-typed exceptions: benign, listed only because the sweep matches them). HIGH for the kill-switch lines (read), MEDIUM that nothing sanitises on the way.
3. Direct body echoes in the agent SDK and tools: field-agent bootstrap.py:58 and :92 (`register returned ...: {resp.text}`), sentinel cli.py:151, seeded.py:225 and :231, lifecycle engine.py:869-1121 (`_body(resp)`, truncated to 500, verbatim by design). The first is what a customer integration prints; the others are operator tooling. MEDIUM.
4. Environment value echoed: force-gateway api.py:297-299 (`InvalidPostureFlag` message includes the first 40 characters of the variable, case preserved; C-376 F-C376-2, still open). A secret mistakenly placed in a flag variable reaches the traceback. HIGH (code).
5. ops-console ServiceClient returns `str(exc)` (api.py:102, :109) in a Section `error` field that the page renders. MEDIUM.
6. Logging is mostly clean: the two log sites that take an exception pass only its type name (witness.py:318) or a fixed detail (lifecycle api.py:298). Pattern to copy.
Not findings: HTTPException(422, "agent_id in path and body must match") and similar fixed texts.

## 4. Recommendation
1. One helper in field-core (for example `field_core.errors.upstream_error(resp, what)`) returning `f"{what} returned {status}"` and nothing else; the body goes to a debug log truncated to 200 characters through `redact`. Use it for findings 1 and 3. Cost: ~12 call sites; tests that assert on the old wording change (grep for `returned 5` in tests before the card).
2. For transport exceptions use `type(exc).__name__` (witness.py:318's pattern), not `str(exc)`, in anything that crosses a boundary (findings 2 and 5).
3. Drop the env value from the message at force-gateway api.py:297 (name the variable only).
4. Lint (AST, the echo_sweep sinks as the rule): in non-test code a boundary sink (HTTPException, JSONResponse, an `*Error` constructor, `typer.echo`, a log call) may not interpolate `.text`, `.content`, `str(exc)`, `.headers` or `os.environ`; allowlist file with a reason per site, equal-to-scan in both directions (the C-57 lint shape, which already exists).
Order: 3, then 1 and 2, then the lint with the remaining sites allowlisted.

## 5. What a builder card should pin
The probe cases (marker absent, length bounded) for each client; a test per boundary that a 5xx upstream gives a reply containing the status and no body; mutants: put `resp.text` back; use `str(exc)` back.

## What I did NOT do
Did not read all 269 swept sites (11 sampled). Did not test an upstream that quotes input (objection 1 is conditional). Did not run the field-agent bootstrap entry point (probe case skips: function name differs). Did not look at the Fly or GX10 logs. Did not edit source, merge or open a PR.
