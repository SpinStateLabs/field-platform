# Changelog

## Unreleased

### Added - pilot S2: `services/claude-approver` v0 (compose profile `approver`, flags OFF)
- A Claude Managed Agents client that answers every `always_ask` tool call (`evaluated_permission: ask`)
  with the conformance-sentinel's verdict: `allow` only on an exact `ALLOW` from a 200, every other
  outcome a `deny` (`<clause>: <reasons>`, `escalated: a human holds this item; ...`, or
  `claude-approver: <reason>`); kill-switch heartbeat per handled call; governor `/usage` from
  `session.usage` deltas with a restart-safe cursor; `POST /halt/{agent}` (interrupt, wait, archive) for the
  kill-switch allowlist; `/stats` with p50/p95 latency. Per-agent estate routing (`estate_base_url` +
  `secret_file`). Custom tools are not executed in v0. Own image (the only one with `anthropic>=2.3.0`);
  never started by a plain `up`; nothing on Fly. Live Managed Agents shapes not yet verified on the GB10.

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
- `POST /events`: reserved operator keys are dropped unless the caller holds the `assert_operator` scope.
- Unresolvable manifest denies; empty `authorized_operators` still requires authentication; body operator replaced by the authenticated id; BOM and lone-surrogate registry handling; bounded log-only ledger write; ops-console forwards the human's headers.

### Phase G second review round
- Registry PATCH honours `authorized_operators`; `registry_edit` scope for manifest_ref/owner; `retired -> active` refused.
- Guarded: `POST /agents` (`register`), ledger `/export` (confined to `FIELD_EXPORT_ROOT`), spend-governor caps/rate-limits/policies/escalations, federation contracts.
- Flags-OFF byte-identical (reserved-key rewrite and `operator.*` refusal only when armed); attribution-loss warning; capped log-only appends; ops-console sign-in panel.

### Phase G third review round
- `names` (display-name aliases) per operator so shipped manifests' `authorized_operators` match; `operator_keygen --alias`.
- The `assert_operator` exemption is shared by every `authorized_operators` check (kill-switch included).
- Registry: no transition out of `retired`; `manifest_ref` edits must resolve; `domain` edits need `registry_edit`; combined PATCH needs the union of scopes.
- Nested reserved keys stripped; `operator.` event-type check ignores case and whitespace; agent-facing routes listed as declared-unguarded.

### Phase G fourth review round
- A registry with duplicate operator ids, an alias equal to an id, an alias shared by two operators, or the alias `*` fails closed (503); `operator_keygen` refuses to write such a row.
