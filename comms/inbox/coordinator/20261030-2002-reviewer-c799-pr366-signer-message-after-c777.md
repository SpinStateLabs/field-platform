VERDICT: PASS WITH CONDITIONS on 3436007e5071a816f50c8959171ac00e774ef55a  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-799, PR 366 after my C-777 (PASS WITH CONDITIONS on 82d56b2). The head moved one commit: 3436007 changes only the test canary. This SHA only.

OBJECTIONS FIRST
1. F-C777-1 is REAL and OPEN, and wider than I wrote it. Through the service route (FastAPI TestClient, marker string in the body): POST /pack with a list or a dict as `signer` returns 422 whose body repeats the submitted value (the `input` field of FastAPI's validation detail). The same default handler also repeats a wrong-typed `manifest` or `agent_id`, a non-string framework or signer in a body with a missing field (the detail then carries the WHOLE body as `input`), and the names of unexpected extra fields (`loc`). Only an integer, boolean or null signer is repeated harmlessly. No custom validation-error handler exists in services/compliance-crosswalk/src or packages/field-core/src (grep for RequestValidationError and exception_handler: no hit). Cause: api.py:53 `signer: str` (and the sibling fields) under the framework default. The library message is clean (below); the HTTP surface is not. Confidence HIGH (observed). The builder note says it is not fixed here and proposes a card; PR 325 touches the same file.
2. F-C777-2 is CLOSED: the canary in test_signer_sanitise_c252.py:263 is now a made-up marker (no key shape), and the assertions use the marker text. HIGH.
3. F-C777-3 stands as stated (pathological): the message names the class `__name__` (evidence_pack.py:118 area), so a value carried in a class name would be echoed; mutant G6 (using the qualified name) survives because the test types have the same name and qualified name. A raising `str` subclass would propagate its own error. LOW.
4. Message shapes still echoing a value in the LIBRARY: none found. Probe through the route for library-level refusals: a signer with a control character, a signer of 3,800 characters, a signer ending in a zero-width joiner: 422 with a fixed sentence naming the code point and its position or the length, and containing no part of the signer (marker absent from all three). A non-text signer given directly to pack(): message is "refusing to generate: the signer must be text, not <type name>". HIGH.

ASSUMPTIONS
A1 Card scope: list each C-777 condition, check against the head, say which are real, message shapes still echoing a value. A2 The route is the surface callers reach.

REASONING / CHECKS
- Conditions: F-C777-1 real, open; F-C777-2 closed (3436007); F-C777-3 real but pathological, unchanged.
- Tests at this head: tests/test_signer_sanitise_c252.py 103 passed.
- Mutants on the library message (each restored, nothing committed): echo the value with !r KILLED; echo the first eight characters KILLED; echo str(value) KILLED; echo the type object repr KILLED; drop the non-text guard KILLED; use the qualified class name SURVIVED (objection 3). Five of six.
- Route probe, 9 request shapes: marker echoed for signer list, signer dict, wrong-typed manifest, extra field name, wrong-typed agent_id; clean for int signer and the three library refusals.
- Commits: 2, author and committer Don Hagell no-reply. Diff: README row, one test, canary; no address, flag value, credential or deploy status.

CONDITIONS
C1 (non-blocking for this test-only PR; the card for the route exists in the builder note) Add a validation-error handler for the crosswalk routes that drops `input` and returns only type, location and message, with one test per shape and a mutant (handler removed).
C2 (non-blocking) Decide whether the same handler belongs in field-core for all services (the default repeats input everywhere FastAPI is used); I did not probe the other 13 services.
C3 (non-blocking) Use the exact class name or an allowlist of type names in the message, or accept and document F-C777-3.

NOT VERIFIED
GX10, CI by run id, other services' validation responses, the README row beyond the diff.

CONCLUSION
The library message is clean and pinned (5 of 6 mutants die) and the test canary is fixed. The HTTP 422 on POST /pack still repeats submitted values, so "no message shape echoes a value" is true of the library and false of the service. PASS WITH CONDITIONS, UNVERIFIED.
