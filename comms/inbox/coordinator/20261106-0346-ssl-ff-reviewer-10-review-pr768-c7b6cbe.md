# Review PR #768 (S8-8, field-core README) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `c7b6cbec30cd3c9dceb4e3b617ff8108f5f5fe36`.

## Facts (HIGH, read from the head)
- 2 commits (8ef8f0da, c7b6cbec); 1 file: packages/field-core/README.md (+14/-3). Docs only; nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Reviewer-9's C1/C2 fixes are present: the llm row now says the cleartext refusal is gateway-only unless the TLS posture flag is armed, and identity headers go only toward FORCE_GATEWAY_URL.

## Claims checked against the code on the head (no test guards README text, so I read the code)
- Module list: every `src/field_core/*.py` module is in the table (`cli`, `schema`, `templates` are covered by the CLI section and vendored dirs). New rows (authn, errors, guarded_operator, hosts, http_errors, ledger_context, operator_auth, operator_health, pricing, posture_flag, rotation_events): every named symbol exists (scripted hasattr check: no missing).
- signing: sign_event/verify_event_signature (signature covers the record including `hash`: signing.py event_signing_bytes), caller_signing_bytes fields (event_type, agent_id, payload, caller_id, caller_ts) exact, private_key_fingerprint and both loaders present.
- llm: `self_identity_headers` needs both FIELD_SELF_AGENT_ID and FIELD_SELF_TOKEN_ID; included in anthropic_headers only when `via_force_gateway()`; `make_http_client` raises InsecureBaseURLError for a non-internal cleartext FORCE_GATEWAY_URL; for ANTHROPIC_BASE_URL it raises when `posture_flag.parse(...) is not False` (armed or unrecognised) and otherwise warns once (D-17); `trust_env=False` ignores proxy variables. All match.
- posture_flag spellings and unset/blank-is-off match parse(); authn exempts only /health with `x-field-auth`; http_errors shows `(field)` and keeps only type/loc/msg; ledger_context limits 200/300 match MAX_ID_CHARS/MAX_NOTE_CHARS; hosts is_internal_host is not ipaddress.is_private.
- build_sha row: 14 services under services/, all 14 import and use build_sha(), including claude-approver (api.py:25, :53); tools/tests/test_build_sha_health.py asserts `len(SERVICES) == 13` (claude-approver excluded), so "other thirteen" is exact.

## Minor (LOW, no change needed)
- `cleartext_ok` is also false for a non-http(s) scheme (code comment: refused, not guessed); the README says only "plain http to a non-internal host". Understates, does not overclaim.
- Row text is long; a reader may miss the D-17 exception. Style only.

## Conditions
None.

## Not covered
Did not run the full field-core suite or render the table; did not check docs outside this file or rebase on current main. Mutation testing is not applicable to a docs-only change.
