# R-14 reviewer report: services/incident-replay (engine.py 609 lines, api.py 50) on main 444e49b

VERDICT: the integrity handling (intact / unverified / broken), the first-failure selection and the RACI sources are pinned; the per-event labelling (`enforced`, `_summarize`) and the Markdown "revoked" cell are not. 50 mutants, 35 killed, 15 survived.

OBJECTIONS FIRST
1. A post-mortem is evidence; a service whose rendering can be wrong with every test green weakens the evidence even if the data model is right.
2. My generator makes only `if` and single-comparison mutants; `api.py` produced 0.
3. I read `replay()` (:367-505) and the helpers around the survivors, not `render_markdown` end to end.

ASSUMPTIONS
1. Main 444e49b; incident-replay suite 74 tests (3.5 s); engine.py mutated in two halves (39 and 11 mutants). [HIGH]

REASONING
1. Results: engine.py 50 mutants, 35 killed, 15 survived; api.py 0 mutants. [HIGH]
2. `replay()` integrity: `verify()` `ok` -> `intact`; a `LEDGER_BUSY_PREFIX` reason -> `unverified` ("never OK"); anything else -> `broken` (engine.py:368-380). All mutants in that block were killed. [HIGH]
3. LOW, F-R14-1: `_enforced` (engine.py:245-251) L248 `startswith("conformance.")` forced True survives: with it every non-shadow event type (delegation, kill, spend) would be labelled `enforced: true` instead of None; nothing pins the None. `_enforced` drives the "log-only vs enforced" column of the timeline. [HIGH]
4. LOW, F-R14-2: `_summarize` (:253-274): every branch (L256 conformance, L264 mint, L267 revoke, L269 kill, L271 spend), each with `if->False`, `if->True` and `==`->`!=` where applicable, survives except what the suite incidentally covers: 12 survivors in L248-271. The summary text of mint, revoke, kill and spend events is untested. [HIGH]
5. LOW, F-R14-3: `_revoked_text` (:606-609) `if not g.revoked:` both `if->False` and `if->True` survive: the Markdown "Revoked" cell for the Accountable grant (:595-598) could read "no" for a revoked token, or "yes" for a live one, with every test green. The JSON `accountable_grant.revoked` is not affected. [HIGH]
6. LOW, F-R14-4: `_earliest_live_note` (:342) `if not isinstance(health, dict): return None` survives; a malformed `/health` would then raise on `.get` instead of returning no note (caught? the `try` covers only `.health()`, not the `.get` calls). [MEDIUM: reasoned, not probed]
7. Design note (INFO, F-R14-5): `verify()` and `events()` are separate calls (:368, :384); events appended between them are in the timeline but outside the "chain intact over N events" statement. The report does not say so. [HIGH on the code, LOW on impact]
8. Pinned: first failure = first of FAILURE_EVENTS by ledger order, counts, the grant overlap window (`issued_at <= until`, `expires_at > since`), the archived-segments note, RACI Responsible from the registry owner or `<unregistered agent>`, the unverified/broken integrity states. [HIGH on mutants]

CONCLUSION
No defect. Add: a timeline test per event type (enforced + summary), a Markdown test for a revoked and a live Accountable grant, a malformed `/health` test. Not done: render_markdown read, arithmetic/argument mutants.
