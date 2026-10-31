VERDICT: FAIL on 63ed5b2f0fa191882f654ce4cac31a88ff4b659f
Card C-1034. The card names head 63ed5b2; the PR's current head is 63ed5b2 (GitHub API: draft, 2 commits, 4 files, base acaf5f24). Cloud reviewer, no GX10: UNVERIFIED until re-run. Every canary below is a made-up string; no real value was used. No other reviewer report on this card.

OBJECTIONS FIRST
1. The PR's claim "a 422 validation response never repeats the caller's text" is false for the service it installs on. A caller-chosen dict KEY is echoed in `loc`: `POST /pack` with `sources.ledger_event_types = {"<canary>": "notint"}` answers 422 and the canary appears in `detail[].loc`. The builder note and the module docstring say "no crosswalk model has one"; `EvidenceSources.ledger_event_types` is `dict[str, int] | None` (services/compliance-crosswalk/src/compliance_crosswalk/engine.py:21) and it is reachable from both request models (api.py:34, 55). HIGH (probed).
2. No test covers it, so the suite is green while the claim fails (F-C1034-1). 
3. 13 of the 14 services keep FastAPI's default reply: grep for `install_validation_handler` finds only the crosswalk api.py and the helper itself. I probed the agent registry: a request with an unexpected field answers 422 and the field NAME is echoed in `loc` (its default reply carries no `input`, so it has a handler or model of its own; not investigated). HIGH for the echo, not verified for the other 12.
4. Failure conditions: (a) a caller pastes a credential as a dict key or field name and a proxy or log keeps the body; (b) a model added later with a free-form dict reintroduces the echo silently; (c) the `HTTPException(status_code=422, detail=str(exc))` at api.py:189 passes a raised ValueError's text; I found no input echo through it with manifest shapes I tried (below), but a ValidationError raised inside `generate_pack` would be a ValueError whose text carries `input_value` (not reproduced).
Steelman: for every other shape in the card the handler works: nested, list, huge, non-UTF-8, wrong content type, unexpected query parameter, an unexpected field name: no echo. The change is small, the fix for the hole is one line, and the PR says "declared limits".

ASSUMPTIONS
A1 Head as above, tests at that head. A2 pydantic and FastAPI as installed here. A3 canary strings only.

REASONING
1. Tests: field-core and crosswalk files 20 passed at the head (HIGH). Merge: PR 394 vs main, PR 325, PR 383, PR 322: clean (git merge-tree exit 0). Commits: 2, author and committer Don Hagell no-reply. CI at the head when read: tests 3.11 and compose-smoke in progress, the others queued, fly-image-smoke success; not green yet (the builder reports a GX10 run of 16 suites, not verified by me).
2. Handler (packages/field-core/src/field_core/http_errors.py:23-41): keeps type, loc, msg; redacts the LAST `loc` element only for `extra_forbidden` (line 34-35); replaces msg for `value_error` and `assertion*` (36-37). It does not touch `loc` for any other type, so a caller key in a dict path stays (finding 1). Declared in its docstring (lines 9-11) as a limit for "a model with dict[str, int]" but the claim in the PR title and the builder note says the crosswalk has none: the limit applies to the crosswalk itself.
3. Probe matrix on the crosswalk app (canary in each position; 422 echo = YES/no): unexpected field /pack no; /crosswalk no; manifest a string no; manifest a list no; tokens list of strings no; signer wrong type no; missing manifest with canary elsewhere no; agent_id a list no; invalid JSON no; non-UTF-8 body 400 no; 2.5 MB string no; form and text/plain content types no; unexpected query parameter no; unexpected key inside `sources` no; ledger_event_types key YES. A canary key inside manifest content returns 200 (no validation), and a canary signer appears in the 200 pack by design.
4. Handler against `install_authn`: `install_authn` is an HTTP middleware and the exception handler is separate; with a shared secret set, an unauthenticated bad body answers 401 and no echo; an authenticated one 422 and no echo for an unexpected field. Order in create_app (api.py:111-112) is not what matters. HIGH.
5. Mutants (9, each applied once, `-x`, restored; tree clean): extra-field name not redacted KILLED; value_error message passed on KILLED; status 422 to 400 KILLED; loc dropped KILLED; type dropped KILLED; crosswalk handler not installed KILLED; redaction only for single-element loc KILLED; msg always passed on KILLED; assertion messages passed on SURVIVED (no test for the `assertion*` branch). 8 of 9 killed. HIGH.

FINDINGS
F-C1034-1 (MEDIUM, BLOCKS, public-safety class): a caller-chosen dict key is echoed in `loc` through `sources.ledger_event_types` on /pack and /crosswalk. Fix: replace any non-integer `loc` element after the first model field that came from a dict key (or collapse `loc` below `sources.ledger_event_types` to the field), and pin with a test using a canary key; correct the PR text and docstring.
F-C1034-2 (LOW-MEDIUM): `assertion*` branch untested (mutant survives).
F-C1034-3 (MEDIUM, scope): 13 services still use the default reply; the agent registry echoes an unexpected field's name. List for a follow-up card: all services except compliance-crosswalk (agent-registry confirmed; the other 12 not probed).
F-C1034-4 (LOW): `HTTPException(422, detail=str(exc))` (api.py:189) passes exception text; not shown to echo input, not pinned.

CONDITIONS
C1 (BLOCKS) F-C1034-1. C2 (non-blocking) F-C1034-2 and -4. C3 (coordinator) a card for the other services.

NOT VERIFIED: GX10 run, CI at this head, the other 12 services, a ValidationError inside generate_pack, pydantic versions other than the installed one.

CONCLUSION
The handler does what it says for every shape except a caller-chosen dict key, which the crosswalk accepts at `sources.ledger_event_types` and echoes. The claim is false for the one service it covers. FAIL on 63ed5b2, UNVERIFIED.
