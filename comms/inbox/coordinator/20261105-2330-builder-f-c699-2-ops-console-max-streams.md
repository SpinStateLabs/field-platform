# Builder: F-C699-2 slice, ops-console FIELD_CONSOLE_MAX_STREAMS (UNVERIFIED, no GX10)
- Draft PR 534, branch fix/ops-console-max-streams-c699, head 2e1a7d6db9e71948e6b736a7aae9a59a6618f7ec, one commit on main cd3b7690.
- Claim check: no BACKLOG line, inbox claim, branch or PR for it (grep origin/comms, ls-remote). Reviewer notes say the sweep "is being dispatched" with no card number; if another lane holds it, release this one.
- Fix: `_max_streams_from_env()` in ops_console/api.py; non-integer or negative refuses to start, fixed text, `from None`. HIGH (run).
- Ran: new tests 7 passed (without the helper the import fails, so all red); mutant `< 0` to `< -1` gives 6 failed, restored; ops-console suite 464 passed; tools env/anchors/boundary-echo/proxy tests 267 passed; `environment_anchors --fix` moved 4 rows.
- Not done (scope): sealed_ledger/store.py:1477 `READ_CONCURRENCY_ENV` int (clamps with max, still raises on non-number), field_agent/canary.py:521 FIELD_CANARY_PORT (argparse default evaluated at parser build). Reviewer's separate force-gateway findings (store_error echo, public_origin) are not touched.
- Decision for coordinator: should the remaining two get one card each or one shared helper in field-core.
