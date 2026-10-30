# PR 361 and PR 366 updates for the C-739 and C-777 reviews (builder Lane 12, C-397)

## PR 361 (workflow lint, slice 1): head b7c514f8
GX10: FULL run on that exact head, 16 "== " suites, 0 failed|error. C-739 verdict was PASS; its one finding is closed.
- F-C739-4 LOW: the `\b` of the dynamic-key rule was unpinned. Added the green case `${{ mygithub[format('{0}','event')] }}`. New mutant M9 (dynamic key without `\b`) KILLED; M1-M8 from the earlier report still killed (131 passed in the file).

## PR 366 (signer non-text message, slice 3): head 3436007e
GX10: FULL run on that exact head, 16 "== " suites, 0 failed|error. C-777 verdict: PASS WITH CONDITIONS.
- F-C777-2 LOW-MEDIUM closed: the canary was shaped like a vendor key; it is now a made-up marker (`MADE-UP-MARKER-NOT-A-SECRET-...`, per the C-584 convention). Both mutants (echo the value, echo its first 8 characters) re-run and KILLED.
- F-C777-1 MEDIUM-LOW NOT fixed here: `POST /pack` with a non-text signer returns a framework 422 whose body echoes the value (api.py:53, `signer: str`). It is a production change in compliance-crosswalk, the same class as C-651/C-712; PR 325 also touches that api.py. Needs a card (suggest: custom validation handler for the pack route that drops the `input` field, one test per shape, mutant: handler removed). I can take it once PR 325 lands.
- F-C777-3 LOW (a class NAME carrying a value; a raising str subclass propagates its own error): pathological, not changed.

## PR 369 note (C-782, Lane 15: FAIL on f685e08, PASS WITH CONDITIONS on 1f4fbc7)
Both of its blocking findings were the ones fixed in 1f4fbc7. Open there: C1 (services must pass `service=` and `write_only_paths`; state-changing GETs enumerated before any deployment sets a read key) and C2 (the seven read-only POST routes, e.g. introspect and the crosswalk pack route, answer 401 to a read key: a design decision for Don: allow a `read_post_paths` list, or run those tools with the full key). C3 (constant-time) is now pinned by a compare_digest spy test (head 1f4fbc7).
