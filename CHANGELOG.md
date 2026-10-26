# Changelog

## Unreleased

### Added - pilot S2: `services/claude-approver` v0 (compose profile `approver`, flags OFF)
- A Claude Managed Agents client that answers every `always_ask` tool call (`evaluated_permission: ask`)
  with the conformance-sentinel's verdict: `allow` only on an exact `ALLOW` from a 200, every other
  outcome a `deny` (`<clause>: <reasons>`, `escalated: a human holds this item; ...`, or
  `claude-approver: <reason>`); kill-switch heartbeat per handled call; governor `/usage` from
  `session.usage` deltas with a restart-safe cursor; `POST /halt/{agent}` (interrupt, wait, archive) for the
  kill-switch allowlist; `/stats` with p50/p95 latency. Per-agent estate routing (`estate_base_url` +
  `secret_file`). Custom tools are not executed in v0. Own image (the only one with `anthropic>=2.3.0,<3`);
  never started by a plain `up`; nothing on Fly. Live Managed Agents shapes not yet verified on the GB10.

### Changed - Phase G Stage 0: field-core and `/health` (PR #32; code only, flags unset, not deployed)
- C-10: `assert_operator` is split into `bypass_operator_list` (skips a manifest's `authorized_operators` check)
  and `ledger_attribute` (reserved operator fields survive the ledger only on event types inside the row's
  `event_prefixes`). `*` implies neither. A registry file that still grants `assert_operator` is refused whole
  (503 under REQUIRE) and `operator_keygen.py` will not write it. This supersedes every `assert_operator`
  sentence in the entries below.
- C-18: every row needs `status` exactly `active` or `revoked` and lower-case hex; one bad row makes the file
  unavailable; zero active rows under REQUIRE is a 503. `operator_keygen.py --check FILE`; atomic `--add-to`.
- C-17: an unrecognised non-empty `FIELD_OPERATOR_REQUIRE` arms ENFORCE (fail closed) and logs one error.
- C-1: `FIELD_OPERATOR_KEY_FILE`, read on every call. C-15: `operator.unauthenticated` keeps `claimed_id` and is
  accepted from any shared-secret caller, `self_reported: true` unless the caller holds `ledger_attribute` (the
  ledger's own guard rows too); every other `operator.*` type is refused to every HTTP caller.
- C-8: `/health` on the eight flag-bearing services reports the operator mode, the registry file's sha256 prefix and
  row count, the service's own identity, the last registry error and drop/refusal counters (never a key, a key hash
  or a row). C-9: spend-governor and federation-broker guards ledger `operator.unauthenticated`. C-16:
  `operator.refused` under ENFORCE, at most 30 records per 60 s per service.
- Registry errors and records never echo a status value, an id or alias carrying the key prefix, or an unbounded
  request path (clipped to 200 characters, printable URL-path text only). The claimed `x-field-operator` value
  stored in ledger rows (`claimed_id`, `operator_claimed` on `operator.*`, `kill.*`, `ledger.legal_hold.*` and
  every other attributed row) is `(not shown)` when it could be a key: the key prefix, or a 40+ character
  unbroken token (an alias in a registry error: 24+); the ledger masks a `claimed_id` posted by any caller too.

### Added - Phase G: authenticated operators (code only, not armed)
- `field_core.operator_auth`: operator keys (`x-field-operator`, `x-field-operator-key`), a local
  `operators.json` verifier (sha256 only, constant-time, scoped), `FIELD_OPERATOR_REGISTRY`
  (log-only) and `FIELD_OPERATOR_REQUIRE` (enforce), both unset by default.
- Guarded writes: kill, kill/domain, revive, drill, attest, rotate, hold, hold/release, mint,
  decommission. 401 no key; 403 wrong key / mismatch / scope / not in `authorized_operators`
  (identical body); 503 when the operator registry is unreadable; 400 on malformed headers.
- Ledger payloads carry `operator_id_authenticated`, `operator_claimed`, `operator_key_fp`.
- `tools/operator_keygen.py`; internal callers present `FIELD_OPERATOR` / `FIELD_OPERATOR_KEY`.
- Kill-switch README Enforced-vs-Declared row; runbook section 7.
- Not deployed, not armed. Arming `FIELD_OPERATOR_REQUIRE` is not undone by an image rollback.

### Phase G review round (independent red team)
- Guarded: registry `PATCH` with `status`, delegation token revoke, ledger `/retention/apply`, lifecycle `/sweep`.
- `POST /events`: reserved operator keys are dropped unless the caller holds the `assert_operator` scope. (Superseded by C-10, PR #32: `ledger_attribute` with `event_prefixes`.)
- Unresolvable manifest denies; empty `authorized_operators` still requires authentication; body operator replaced by the authenticated id; BOM and lone-surrogate registry handling; bounded log-only ledger write; ops-console forwards the human's headers.

### Phase G second review round
- Registry PATCH honours `authorized_operators`; `registry_edit` scope for manifest_ref/owner; `retired -> active` refused.
- Guarded: `POST /agents` (`register`), ledger `/export` (confined to `FIELD_EXPORT_ROOT`), spend-governor caps/rate-limits/policies/escalations, federation contracts.
- Flags-OFF byte-identical (reserved-key rewrite and `operator.*` refusal only when armed); attribution-loss warning; capped log-only appends; ops-console sign-in panel.

### Phase G third review round
- `names` (display-name aliases) per operator so shipped manifests' `authorized_operators` match; `operator_keygen --alias`.
- The `assert_operator` exemption is shared by every `authorized_operators` check (kill-switch included). (Superseded by C-10, PR #32: `bypass_operator_list`.)
- Registry: no transition out of `retired`; `manifest_ref` edits must resolve; `domain` edits need `registry_edit`; combined PATCH needs the union of scopes.
- Nested reserved keys stripped; `operator.` event-type check ignores case and whitespace; agent-facing routes listed as declared-unguarded.

### Phase G fourth review round
- A registry with duplicate operator ids, an alias equal to an id, an alias shared by two operators, or the alias `*` fails closed (503); `operator_keygen` refuses to write such a row.
