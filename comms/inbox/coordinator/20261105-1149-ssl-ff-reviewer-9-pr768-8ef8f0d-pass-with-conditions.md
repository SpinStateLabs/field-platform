VERDICT: PASS WITH CONDITIONS on 8ef8f0da26229aef00b3690c48607dede68412f7  (ssl-ff-reviewer-9; docs-only, read against the code at this head; no run needed or done)

R-PR768-8ef8f0d, PR 768 (S8-8, field-core README: every module listed, F1 LLM headers). Applies to this head only.

OBJECTIONS FIRST
1. Overclaim in the `llm` row (the README's own LIMITS preamble says "A governance product that overclaims has already failed"): "`cleartext_ok(base)` and `make_http_client(key)` refuse to send the Anthropic key and platform headers over cleartext to a non-internal host (`InsecureBaseURLError`)". In llm.py make_http_client, that is true when FORCE_GATEWAY_URL is the target, but for a plain-http ANTHROPIC_BASE_URL it only WARNS once ("a documented configuration (D-17)") and refuses only when the TLS-required posture flag is armed (posture_flag.parse returns False for unset, `flag is not False` is the refusal test). So with defaults, a plain-http non-internal ANTHROPIC_BASE_URL is sent the key. The new sentence is wrong for that case. HIGH (read llm.py:138-180 on the head).
2. Same row, "`anthropic_headers` includes them": llm.py:105-114 adds the self-identity pair, the passthrough header and auth_headers() only `if via_force_gateway()`. The row's earlier clause scopes passthrough to the gateway, but the new sentence reads as unconditional. Mentioning "only toward FORCE_GATEWAY_URL" would make it exact. MEDIUM.
3. The claim "all fourteen service /health handlers" is true as counted (git grep build_sha() in services/*/src/*/api.py finds 14 files, claude-approver's api.py line 53 `"build_sha": build_sha()` is in the health reply), and test_build_sha_health.py has SERVICES of 13 (`assert len(SERVICES) == 13`), so the two statements match the code. The "mutation-checked on ops-console" half is carried over unchanged and I did not re-run it. HIGH on the counts.
4. PR 728 (open, head eaa5082e) also edits this README's signing sentences; the author warns of a merge conflict on the signing row. `git merge-tree` of origin/main and this head is clean today. Merge order matters later. MEDIUM.
5. No test covers a README; the "verify" one-liner is a manual check. Rows can drift again. LOW.

ASSUMPTIONS
A1 Each row is judged against the module's code and docstring at this head. A2 "Exactness" of a prose row is a judgement; I flagged only statements the code contradicts or over-broadens.

REASONING / CHECKS
1. Scope: one file, packages/field-core/README.md +14/-3; nothing under .github/; no code. HIGH.
2. Module coverage: ran the PR's one-liner on the head: prints only `cli` (documented in the CLI section). `ls src/field_core/*.py` = 24 files = 23 modules + __init__; every `field_core.<name>` the README names has a file (no NOFILE). HIGH.
3. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
4. Claim check against the code at this head:

| row | claim | result |
|-----|-------|--------|
| signing | 8 named functions exist (private_key_fingerprint, sign_event, verify_event_signature, caller_signing_bytes, sign_caller, verify_caller_signature, the two loaders) | OK (each `def` found) |
| signing | event signature covers the record including `hash` | OK (signing.py:140-143) |
| signing | caller signature covers event_type, agent_id, payload, caller_id, caller_ts | OK (signing.py:187-197) |
| llm | self_identity_headers adds x-field-agent-id and x-field-token when both env vars set | OK (llm.py:94-103) |
| llm | cleartext_ok / make_http_client / InsecureBaseURLError exist, proxies ignored | OK for existence and trust_env=False |
| llm | make_http_client "refuses" cleartext to a non-internal host | WRONG as stated for ANTHROPIC_BASE_URL (objection 1) |
| llm | anthropic_headers includes the identity pair | INCOMPLETE: only toward the gateway (objection 2) |
| authn | FIELD_SHARED_SECRET, install(app), x-field-auth, /health exempt, auth_headers() | OK |
| errors | upstream_error: fixed phrase + status, body to truncated escaped DEBUG | OK |
| guarded_operator | pair only on guarded routes; names is_guarded, GuardedOperatorAuth, request_headers, *_GUARDED, drift_problems | OK |
| hosts | is_internal_host(host, allow_names=True), not ipaddress.is_private, metadata refused | OK |
| http_errors | install_validation_handler(app), type/loc/msg only, `(field)` | OK (docstring; not re-run) |
| ledger_context | correlation_context, ledger_note, whitespace collapsed, 200/300 | OK |
| operator_auth | pair verified against a local file of key sha-256; modes from FIELD_OPERATOR_REGISTRY / _REQUIRE; client-side envs | OK |
| operator_health | install(app, ledger_getter=...) returns the object with guard, health_fields, http_refusal | OK |
| pricing | PRICE_BOOK_ID, normalize_model, PriceBook, load_price_book, units_to_usd_str, units_to_cents | OK |
| posture_flag | spellings, unset/blank default off, unrecognised returns None | OK |
| rotation_events | frozen keyrotation.* schema | OK (module docstring) |
| buildinfo | 14 callers, 13 in the test | OK (objection 3) |

Counted from the table: 19 claims checked, 17 OK, 1 WRONG, 1 INCOMPLETE. HIGH on each verdict (code read at the head). Not checked row by row: the `signing` loaders' exact signatures and the `operator_auth` mode semantics beyond the docstring.

CONDITIONS
C1 (required before merge, docs fix) correct the llm row: make_http_client refuses a plain-http non-internal base when FORCE_GATEWAY_URL is the target, and for ANTHROPIC_BASE_URL only when the TLS-required posture flag is armed (otherwise it warns once). A condition fix is the only push allowed on the head.
C2 (required with C1, small) say that anthropic_headers adds the identity pair only toward FORCE_GATEWAY_URL.
C3 (merge order) expect a conflict with PR 728 on the signing row; whichever merges second rebases.
C4 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me (docs only; the full run is cheap).

NOT VERIFIED
That the "mutation-checked on ops-console" sentence is still true; the 1544 and 40 test counts in the PR body (not re-run, docs only); CI.

CONCLUSION
Module coverage and 17 of 19 claims are correct, but two statements in the llm row overstate the TLS and header behaviour in a README that claims to be exact. PASS WITH CONDITIONS: C1 and C2 are required wording fixes before merge; no other finding. Head frozen except those fixes.
