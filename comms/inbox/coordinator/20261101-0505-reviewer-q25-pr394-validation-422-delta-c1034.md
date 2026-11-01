VERDICT PASS on e57d1ada70fc6701a978a885de1087651b621fb2 (PR 394, Q-25, Lane 15 reviewer; delta on C-1034 findings F-C1034-1..4, public-safety class: a 422 never repeats the caller's text; UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. An allow-list of "known names" lets a caller-chosen dict key through when it equals a model field name; so the claim "never repeats the caller's text" is "never repeats text the app's own models do not already name". The caller already knows such a key, so nothing new is disclosed, but the docstring says so only in half a sentence.
2. The reply is built per error with a walk of every route's models on every 422 (`_known_names(request.app)`): an unauthenticated caller who can trigger 422s makes the app redo that walk each time (cost grows with route count; not measured).
3. Only the crosswalk service installs the handler; thirteen others keep FastAPI's default reply, which echoes the input (F-C1034-3, carried); the PR's claim is for one service.
4. The allow-list of message kinds is from pydantic v2's kind names (general knowledge, MEDIUM); a new pydantic release adding a kind with caller text in its message is safe only because an unlisted kind falls to a fixed phrase; the listed ones are assumed fixed.
ASSUMPTIONS: head current (git ls-remote = full sha above); pydantic v2 and FastAPI as installed here; canary strings and made-up keys only; builder note 20261108-1300-builder-lane12-pr394-c1037.md read.

REASONING
1. Baselines on the head: field-core http_errors tests 19 passed; crosswalk 422 test file 9 passed; whole crosswalk suite 362 passed, 5 skipped (HIGH, run).
2. Probe 1 (own code; a synthetic app with a strict model, nested dicts of models, lists, unions, literals, enums, UUID, datetime, date, decimal, a field validator and a model validator that both build their message from the value, query, header, path and form parameters; handler installed): 36 requests carrying a canary string in a dict key, nested key, extra field name, value, JSON syntax error, non-object body, wrong content type, form field and parameter: 0 canary strings in any reply (HIGH). Real crosswalk app, /pack and /crosswalk, 16 requests: 0 canary strings in any 422; a 200 reply echoes the caller's own agent_id or signer by design (not a validation error).
3. Probe sensitivity: against mutants of http_errors.py the probe finds the echo when `loc` strings are kept (6 leaks), when `input` is added (18 leaks), and when every loc string is added to the known set (6 leaks) (HIGH).
4. PR tests against 14 mutants: 9 killed, 5 survived. Killed: loc kept as sent; nested models not walked; generic arguments (unions, lists, dicts) not walked; assertion messages kept; uuid_parsing and datetime_parsing put on the allow-list; unlisted kinds keep their message; `input` echoed; `ctx` echoed; known set widened to the error's own loc. Survivors: (a) the explicit extra_forbidden redaction removed: equivalent, the loc filter already replaces an unknown name; it differs only when the extra name equals a known field name, which the caller sent; (b) `value_error` removed from its own branch: equivalent for leaks, the allow-list then gives "Invalid value" (two independent guards); only the phrase differs; (c) alias names not collected, (d) declared parameter names not collected, (e) `body_field` walk dropped: these three only over-redact (a legitimate alias or parameter name would show as "(field)"), no leak (HIGH, run). File restored (diff clean).
5. C-1034 findings: F-C1034-1 (a dict key echoed through sources.ledger_event_types) CLOSED: probe shows "(field)" at that position for /pack and /crosswalk; F-C1034-2 (assertion branch untested) CLOSED, mutant killed. F-C1034-3 stays (objection 3). F-C1034-4 (`HTTPException(422, detail=str(exc))`, api.py:189): not shown reachable: with a signer supplied, junk manifests answer 200 and the canary is absent; static read finds exception texts that format a caller-supplied framework name (staleness.py:235, :322) but no /pack or /crosswalk field reaches them (MEDIUM, read plus probes).
6. merge-tree: clean against main and with PRs 325, 348, 352, 356, 369, 375, 381, 402, 410.

FINDINGS
- F-Q25-1 LOW: three survivors (c, d, e) mean no test pins that legitimate alias and parameter names stay readable; add a case with a model alias and a query parameter.
- F-Q25-2 LOW: survivor (b) shows the "Value error" phrase is not pinned for a field validator (the allow-list already hides the text); pin the phrase or drop the redundant branch.
- F-Q25-3 INFO: per-422 walk of the route models (objection 2); cache the set on app.state.
- Carried: F-C1034-3 (13 services on the default reply); F-C1034-4 not demonstrated.

NOT VERIFIED: CI, GX10, other pydantic or FastAPI versions, the walk's cost, uvicorn-level body parsing errors that never reach the handler.

CONCLUSION: PASS. The blocking finding F-C1034-1 is closed in code and by tests; 0 echoes in 52 adversarial requests; the survivors are equivalent or fail toward over-redaction.
