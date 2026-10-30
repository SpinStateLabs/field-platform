# Changelog

## Unreleased

### Changed - review rounds on main, batches F to P (PRs 126 to 159, merged 2026-10-29)
Each batch is one fast-forward of reviewed commits; the commit ids below are the ones on main (`git log`). The PR number is the batch PR; the source PR and card numbers are in each commit message and in `comms/STATUS.md` on the `comms` branch. Code behaviour is stated as the commits state it; nothing here says where anything is deployed.
- Batch F (PR 126): `renew_token` signs its ledger appends with the caller key when `FIELD_LEDGER_CALLER_ID` and `FIELD_LEDGER_CALLER_KEY` are set, counts a lost append as `dropped_ledger_appends=N` on the failure line, and a signing error sends no POST (80fdd1a, 18c4059); its signing tests run with the interpreter that has field-core's dependencies (29a924f) and the runbook says a system python loses the signed record (4c67c37). `todo.md` C2 follows the segments journal (8ae7dbf); the ops-console README states the shared secret has no secure-context gate (727a785).
- Batch G (PR 133): a retired agent's owner, domain and `manifest_ref` are frozen, refused 409 in every operator mode inside the same atomic store step as retired-is-terminal; the name stays editable (84570e7). ops-console tests: manifest symlink and size guard, the refusal ledger append, upstream and registry error text (ef0ba78), and the dashboard escaping pinned with a hostile-estate jsdom probe (d16c424). Docs: the Fly rehearsal log is removed from the tip and `STATE.md` drops deployed image, volume, snapshot and machine ids and present-tense deploy claims (6793a90, f75baab).
- Batch H (PR 142): `operator_keygen` tests for key file permissions and content, usage errors exiting 2 and the program entry (803dd35); claude-approver pins for the shadowed tool case, the split-batch rejected label, halt skips and deadline, and config shape checks (9cc9ed2); `STATE.md` present-tense estate lines and deploy-status headings removed (fb52eef).
- Batch I (PR 145): the estate's private address becomes `<gb10-lan-address>` in docs, comments and help text (c124b5c); independent tests use a documentation-range address (d42901c); the GB10 proxy's TLS address comes from `FIELD_GB10_LAN_IP`, required with no default, and CI uses an RFC 5737 documentation address (c771f7b); `estate_probe` gains `--expect-mode` on the status pairing, restores the canary after a catalogue run, bounds its reads (c90b3c2, c293b2a) and keeps its canary and token guards ahead of any write, with a static guard test (4847520); one `env` block in `compose-upgrade-smoke`, a duplicate key had made the workflow invalid (b07f648).
- Batch J (PR 149): tests that `register` fails closed on any answer but 201 or 409, reads after a 409 only on 200, and `on_behalf_of` has its own gate (0750b60); force-gateway pins for the upstream non-200 passthrough, the hygiene judge key and status guards, and the resolver (e9dcada).
- Batch K (PR 152): delegation-authority tests of the mint grantor rule end to end (907c142); a symlink loop in the ops-console manifest path is refused 404, not a 500 (26d95e6); a test that no workflow or compose file has a duplicate mapping key at any depth (c3b6a25).
- Batch L (PR 153): ops-console tests pin each containment check alone and the signed refusal append, built for the ledger client's own headers (97432d5, a97402f); dated notes on ADR packs 10, 07 and 02 (0acf2e6, 73bc4e7).
- Batch M (PR 154): field-agent pins for the canary halt body guards, `x3_check` refusals, the heartbeat-age boundary and federation argument checks (5d0515a); defence-shield pins for the allowlist negatives, the AUTHORIZED exit code and the detection boundaries (b099b28).
- Batch N (PR 155): `phase_g_check` closes two fail-opens: a keyed run needs at least two registry status changes, and without `--expect-mode` an inferred OFF is a FAIL and an inferred armed mode exits 4 (NOT VERIFIED), never 0; a failed check (1) outranks 4 (d2ce25f).
- Batch O (PR 156): the compliance-crosswalk evidence pack says it is a named-signer document, not a cryptographically signed one (README paragraph and Declared row, the pack header line, an ADR 07 wording note) (a946d26).
- Batch P (PR 159): `operator_keygen` validates the registry before writing or printing a key, so a refused `--add-to` leaves no key file or printed key whose hash was never registered (fd32d64); attestation-reporter: a wrong-shape ledger or token answer fails one metric closed (3bbc9d3).

### Changed - review rounds on main, 2026-10-28 (PRs 58 to 96)
Each line names the main commit; dates are the commit dates in `git log`. Merge evidence per PR is in `comms/STATUS.md` on the `comms` branch.
- Operators file and loader: format 2 break-glass id must be a `rotation:` sealed row (PR 58, 75a84c8); the break-glass alias belongs to the break-glass row alone (PR 63, 84d26a4) and is refused in the shared `validate_rows`, format 1 too (PR 64, a8bd47c); duplicate JSON keys are refused and deep nesting takes the designed refusal (ec60512, 2518d1d); one shared decoder `decode_registry_document` serves the loader, `operator_health` `slot_witness` and `operator_keygen --check`, so `--check` and the service agree on every file shape (PR 95, b1872ee).
- Observer: the sealed-ledger operator observer witnesses a content-only edit of the operators file (PR 61, ecb3ffd) and its bytes-only change event is documented (aaae5ec).
- Operator health: a refusal with no ledger to write to is counted as dropped (PR 66, a91b819).
- Alerts: ntfy push alerts with an alert-test CLI and runbook (b4d0495, 0a9fadb); an environment proxy never receives the alert, the module default opener is pinned against it (PR 59, 07f072a, e75d9bb); `stage_aborted` and `rotation_halted` classes (c6883e5).
- Clients and proxies: `field_agent.FieldClient` takes no environment proxy and reads a bounded reply (b5e07d0, 39d02e9).
- LLM callers: `field_core.llm.make_http_client` is the one way the hygiene judge, the sentinel judge and the crosswalk suggester build their Messages client, with `trust_env=False` so an environment proxy no longer receives the Anthropic key, the perimeter secret or the token id; a plain-http `FORCE_GATEWAY_URL` outside the estate is refused (`cleartext_ok`, `InsecureBaseURLError`) (PR 96, 7b54f26). Open follow-up F-C197-1 (PR 104); the claude-approver SDK client is not covered (F-C187-3, not deployed).
- Force-gateway: the upstream key never goes back to the caller and judge errors name the class only (45a36f5); warn once, opt-in `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM`, wider base64 and prefix scrub, class-name error texts (PR 75, 9292246).
- Console edge: `X-Frame-Options`, `frame-ancestors` and `nosniff` on the ops-console catch-all of both Caddyfiles (0917267, e043257).
- Machine verifier (P35): the verifier identity reaches the canaries only, mint and revoke for the canaries alone; section 7 verification runs under `svc-verifier-<estate>` (PR 73, 583519d to 66aa869, 1845f49).
- Delegation: a list-bound identity cannot tell an unknown token from one it may not revoke (151cd3f); the unknown-token revoke 403 is a counted, ledgered refusal (PR 77, 444e49b).
- Registry: a retired agent cannot be reactivated by PATCH in any mode (D-22, 0843123); the retired-is-terminal rule sits in the store's atomic update (6f5ee96).
- Tests only: operator_health survivors (PR 79, ad33a60), spend-governor cap window (PR 81, 284f14b), kill-switch drill detection and `/liveness` cutoff (15a7304, b92ec10), sealed-ledger rename retry (70fa59f), observer fetch deadline (0b44dee), delegation red-team follows D-22 (7b4d6f7), field-core deep-nesting loader (2518d1d). Crosswalk README: FC-E-04..06 cite nothing (4cf73d5).

### Changed - Phase G Stage 1 and key rotation, 2026-10-27 (PRs 43 to 54)
- Key rotation R1 to R3: operators file format 2 parser (PR 53, b273d5b), lifecycle-manager builds operator auth headers per request (PR 51, 34d680c), and `verify-hash`, rotation state, roster digest and break-glass counters (PR 54, c8ecba7).
- Phase G: sign operator events in the form the ledger stores and count failed record appends (PR 52, cefb81b); per-process operator identities on the Fly machine (PR 44, f6c348f); `ops-console` refuses an operator key outside a secure context (PR 50, ca5e895).
- Hardening and follow-ups: observer whole-exchange deadline, `fullmatch`, ledger UNREADABLE vs busy, `field verify-chain` exit 2 (PR 45, d288a2f); `set_status` per-call headers, `estate_probe` RT1-RT3 pairing, P29 no-change re-provision (PR 46, efe430b); `ledger verify` with no ledger at `--path` exits 2 unless `--allow-empty` (PR 47, af17cc4); DOA job-grantor rows folded into `doa-roster.example.yaml`, `generate_doa_roster --job-rows` (PR 49, 3b3be05).
- P30: Claude 5.5 generation priced; session ids on sentinel and governor ledger rows (PR 43, ac2d981).

### Added - P28(c): `field_agent.field_client.FieldClient` (lifted from cost-optimizer)
- The cost-optimizer's stdlib FIELD client (`SpinStateLabs/cost-optimizer` 817aace, `field_client.py` +
  `safe_http.py`) now lives in `packages/field-agent` with its behaviour unchanged, re-exported as
  `field_agent.FieldClient` / `field_agent.FieldStop`, so the next FIELD-guarded gateway (deploy guide pattern D)
  does not re-implement the five fail-closed rules. Tests: the source's 13, 5 gap-closing additions and 6
  contract tests against the real sentinel, governor and kill-switch apps (in-process, no network). The
  cost-optimizer is not changed and still uses its own copy.

### Changed - Phase G Stage 0 follow-ups (code and descriptors)
- C-6 switched on in the compose and Fly descriptors: the ledger's operator observer runs (`FIELD_LEDGER_OBSERVE_EVERY` default 60 s,
  `FIELD_LEDGER_OBSERVE_HEALTH` = the seven other operator-block services), on the ledger only. CI's three smoke
  jobs check the start-up `operator.mode_changed` / `operator.registry_changed` rows on the real containers.
  The observer streams each `/health` body with a 64 KiB / 3 s cap (a trickled or huge answer is no answer).
  `phase_g_check` check 5 (collateral) lists observer rows (those two types, no agent id) as `[INFO]` instead
  of failing on them.
- `operator_on_behalf_of` is a reserved ledger key (field-core `RESERVED_KEYS`): a shared-secret caller can no
  longer put it on a row once an operator mode is armed; the registry records it only through field-core's
  `bind_on_behalf_of` (a `bypass_operator_list` identity), and the ledger keeps it only from a writer whose
  `ledger_attribute` `event_prefixes` reach the event type: any such holder on its own prefixes (design 2.2.1:
  `svc-registry` `registry.`, `svc-killswitch` `kill.`, `svc-delegation` `delegation.`, `svc-lifecycle`
  `lifecycle.`/`orphan.`), not only the registry.
- `sweep_kill` (C-11) is a known field-core scope in `EXPLICIT_ONLY`: `*` does not imply it for any `has_scope`
  reader, and `operator_keygen.py` writes it only when named.

### Added - pilot S2: `services/claude-approver` v0 (compose profile `approver`)
- A Claude Managed Agents client that answers every `always_ask` tool call (`evaluated_permission: ask`)
  with the conformance-sentinel's verdict: `allow` only on an exact `ALLOW` from a 200, every other
  outcome a `deny` (`<clause>: <reasons>`, `escalated: a human holds this item; ...`, or
  `claude-approver: <reason>`); kill-switch heartbeat per handled call; governor `/usage` from
  `session.usage` deltas with a restart-safe cursor; `POST /halt/{agent}` (interrupt, wait, archive) for the
  kill-switch allowlist; `/stats` with p50/p95 latency. Per-agent estate routing (`estate_base_url` +
  `secret_file`). Custom tools are not executed in v0. Own image (the only one with `anthropic>=2.3.0,<3`);
  never started by a plain `up`.

### Changed - Phase G Stage 0: field-core and `/health` (PR #32; code only)
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

### Added - Phase G: authenticated operators (code only)
- `field_core.operator_auth`: operator keys (`x-field-operator`, `x-field-operator-key`), a local
  `operators.json` verifier (sha256 only, constant-time, scoped), `FIELD_OPERATOR_REGISTRY`
  (log-only) and `FIELD_OPERATOR_REQUIRE` (enforce), both unset by default.
- Guarded writes: kill, kill/domain, revive, drill, attest, rotate, hold, hold/release, mint,
  decommission. 401 no key; 403 wrong key / mismatch / scope / not in `authorized_operators`
  (identical body); 503 when the operator registry is unreadable; 400 on malformed headers.
- Ledger payloads carry `operator_id_authenticated`, `operator_claimed`, `operator_key_fp`.
- `tools/operator_keygen.py`; internal callers present `FIELD_OPERATOR` / `FIELD_OPERATOR_KEY`.
- Kill-switch README Enforced-vs-Declared row; runbook section 7.

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
