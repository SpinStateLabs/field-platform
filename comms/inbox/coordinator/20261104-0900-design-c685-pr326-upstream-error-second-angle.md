# C-685: read of PR 326 (an upstream reply body is never part of an error message), second angle, Lane 10

Head 203810f (field-core `errors.upstream_error`, six call sites in clients.py, two in conformance-sentinel). Read-only; UNVERIFIED on any estate. The first angle is reviewer C-584; this is the class-C view (my note 20261102-1500-design-error-text-echo.md, C-490). Probe: my AST sweep (20261102-1500-design-error-echo-sweep.py) on the head, a DEBUG-path probe of the helper, 4 mutants.

VERDICT: PASS on 203810f for what it changes (the six field-core sites and the two sentinel sites no longer put a body in a message). 13 sites outside the changed files still carry a body, by design or not yet migrated; the DEBUG path is bounded and escaped but unredacted by choice. Confidence HIGH (run).

## ASSUMPTIONS
1. The invariant (C-490 note): a message that crosses a service boundary carries a fixed phrase, the status code and caller-supplied identifiers, never an upstream body.
2. The DEBUG record is a log, not a message.

## Objections first
1. The DEBUG path writes the first 200 characters of the upstream body, `ascii()`-escaped, to the `field_core.upstream` logger. Probe: at WARNING the marker is in neither the message nor the log; at DEBUG the marker IS in the log (one line). The module docstring says so ("no redaction is done on the debug record"); a deployment that turns DEBUG on for that logger accepts it. A body that quotes a submitted secret reaches the log at DEBUG. LOW-MEDIUM, stated trade-off.
2. The helper formats `status` with no type check: a stand-in object whose status text is `500; DROP` prints it (probe). Real httpx responses give an int, and the injected-client interface is internal. LOW.
3. The body is read (`resp.text`) only when DEBUG is enabled (good), but no test pins that: my mutant "read the body always" stays green (17 passed). A performance and memory property, not a leak. LOW.
4. 13 sites outside this PR (sweep: 13 `raise`/error-object sites with `.text` or the page's `_body`, down from 37 on main): field-agent `federation.py:152`, `liveness.py:66`, `usage.py:114` and `:151` (the customer SDK raises with a body); lifecycle-manager `engine.py:867, :884, :902, :927, :966, :1062, :1079` (the `_body` helper truncates to 500 characters and is verbatim by design: engine.py:432-438 docstring), plus two direct `.text` uses at `engine.py:927` and `:1063` with no truncation. Not changed by this PR. MEDIUM-LOW for the SDK ones, which a customer's logs will carry.
5. Transport exceptions still travel as `str(exc)` (`LedgerUnreachableError(str(exc))`, `RegistryUnreachableError(str(exc))` in clients.py and the relays in kill-switch api.py), which is the C-504 card, not this PR. INFO.
Steelman: one helper, status only, bounded and escaped debug record, a test per call site, and the two sentinel sites migrated too.

## Results
- Helper behaviour (probe): the message is `"<what> returned <status>"` for every body I tried (a marker, newlines, a forged log line, an ANSI escape, 5,000 characters, an undecodable body, no status); at DEBUG the log line is one line, truncated to 200 characters plus the prefix (255 total for a 5,000-character body), with no control characters (the newline, carriage return and ESC are escaped by `ascii()`), so no log injection.
- Mutants of mine, each red unless noted: body back in the message (11 failed), debug record not escaped (1), debug record not truncated (1); body read even when DEBUG is off survives (equivalent in output).
- Suites: field-core 1,132 passed, 1 skipped (the new test file included); conformance-sentinel's tests need the service CWD and its dependencies: the new tests passed in the first run, the whole sentinel suite not run to green here.
- The AST sweep on the head: raise-with-body 4 and error-object-with-body 9 (main: 37 combined), api-reply with exception text 40 (unchanged), CLI echo with a body 31: the CLI echoes are operator tools.

## Findings
F-C685-1 MEDIUM-LOW: migrate field-agent `federation.py:152`, `liveness.py:66`, `usage.py:114`, `:151` to `upstream_error` (the SDK is customer-facing); confirm with the maintainer of lifecycle-manager whether `_body` verbatim text is wanted and bound the two untruncated uses at `engine.py:927` and `:1063`.
F-C685-2 LOW: pin (a) the body is not read when DEBUG is off and (b) a non-int status is formatted with `int(...)` or `%s` of a checked value.
F-C685-3 INFO: C-505 (the lint) would keep the class closed.

## What I did NOT do
Did not run the whole sentinel suite. Did not trace every `.text` outside the sweep's variable names. Did not read C-584's report before writing this (independent angle). Did not edit the PR.
