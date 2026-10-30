# v2 one-liners: old to new wording, Enforced vs Declared

**Global estate status.** Both estates run pre-v1.2 images. Every Enforced word below is test/CI-proven at the cited commit; per-system estate status is **Declared** until the estates redeploy. Phase G operator identity is not armed on either estate (REQUIRE is off everywhere; Stage 1 is LOG-ONLY on the GB10 only), so no one-liner relies on it. Nothing here claims compliance or certification.

**Provenance of the "old" column.** The old text is quoted verbatim from [`v2-one-liners-source.md`](v2-one-liners-source.md), recovered 2026-09-12 from `AI-CTO/claude-files/Force-Field_Build_Prompt.md` (outside this repo). Where the 2026-09-12 audit quotes a phrase not literally present there (for example "API-key scans", "Continuous", "org-wide"), the audit paraphrased the underlying claim; this file quotes the source text. Numbering is the audit's 1-12.

**How to read the tables.** Each Enforced word names `path::test_name`, the commit that introduced that test, and a `needle`: a literal string that must appear inside that test's body. `python tools/phase_e_gate.py` checks that the test exists, that the needle is in its body, that the commit exists, and that no service README row marks an Enforced word "Declared only". A needle shows the test asserts the word's subject; it does not replace reading the test. Some cited commits are squash commits that introduced several tests at once.

The Declared lists are not apologies: each names the reason no test backs the word, or why it holds only when something is deployed that is not.

## 1 — Agent Registry

**Old (verbatim):** **1 — Agent Registry** ("the passport office") — system of record where every AI
agent is registered with identity, owner, and FIELD manifest; discovers
unregistered shadow agents by scanning service accounts, API keys, and workflow
platforms. (FIELD-I · CIO)

**New:** Registry of AI agents: identity, owner (a recorded string, not verified as a current human) and a manifest reference that must resolve when set. Discovery turns an n8n export, a service-account inventory, a credential-inventory CSV and pasted text into a review queue. API-key scans are file-based and heuristic: no live IAM connector; coverage is only what you feed it.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| system of record for AI agents: identity, owner ... status persist | `services/agent-registry/tests/test_agent_registry.py::test_crud_roundtrip` | `8527e85` | `killed` |
| manifest reference that must resolve when set | `services/agent-registry/tests/test_d3b_manifest_ref_resolves.py::test_an_unresolvable_set_ref_is_422_and_nothing_is_written` | `4b8b352` | `422` |
| n8n export / service-account inventory ... review queue (renamed workflow still flagged) | `services/agent-registry/tests/test_agent_registry.py::test_adversarial_renamed_workflow_still_flagged` | `8527e85` | `wf-999` |
| service-account inventory and unregistered workflow surface, registered ones do not | `services/agent-registry/tests/test_agent_registry.py::test_discovery_finds_shadow_agents` | `8527e85` | `wf-103` |
| credential-inventory CSV scan (file-based) | `services/agent-registry/tests/test_d3_credential_scan.py::test_the_fixture_inventory_surfaces_exactly_the_four_shadow_keys` | `4b8b352` | `invoicing-agent-prod` |
| heuristic (breadth-labeled patterns) | `services/agent-registry/tests/test_d3_credential_scan.py::test_breadth_labels_name_the_broad_and_generic_patterns` | `4b8b352` | `broad` |

Declared:

- **owner (a recorded string, not verified as a current human)** — README Declared only: owner is a real, current human; roster reconciliation is lifecycle-manager's job
- **coverage is only what you feed it** — README Declared only: the registry knowing ALL agents in the org; discovery sees only the artifacts supplied
- **manifest reference ... keeps pointing at a valid manifest after registration** — Not claimed: PATCH does not re-check manifest_ref (README Declared only)
- **attested_by is the human who attested** — Not claimed in one-liner: recorded string, not an authenticated identity
- **estate status of every word** — Both estates run pre-v1.2 images until redeploy (D3 credential scan and D3b are v1.2); Declared per estate

Reworded:

- "discovers unregistered shadow agents by scanning ... API keys, and workflow platforms" → "turns an n8n export, a service-account inventory, a credential-inventory CSV and pasted text into a review queue; API-key scans are file-based and heuristic" — Audit row 1: no API-key scanner existed at audit time; the D3 file-based scan now exists (CSV inventory + secrets-text), but it reads files you export, and 'workflow platforms' is the n8n JSON export only
- "every AI agent is registered" → "(dropped) coverage is only what you feed it" — README:37 Declared only: the registry cannot know about all agents
- "owner" → "owner (a recorded string, not verified as a current human)" — README Declared only: owner is a real, current human

## 2 — Conformance Sentinel

**Old (verbatim):** **2 — Conformance Sentinel** — An agent that continuously audits deployed agents
against their FIELD manifests and blocks non-conforming actions at the
policy-enforcement point — scope breaches, expired authority, missing ledger
writes — before they execute.

**New:** Checks each proposed action against the agent's manifest, token, kill status, ledger and rate window at the agent's action boundary (SDK/@governed; cooperative perimeter: a process that does not ask is not stopped). In enforce mode it blocks before execution. Also intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate).

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| kill status (killed agent blocked E.kill_switch on next check) | `services/conformance-sentinel/tests/test_sentinel.py::test_killed_agent_blocks_instantly` | `3b42cfc` | `E.kill_switch` |
| manifest/token scope (out-of-scope action blocked D.scope) | `services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_out_of_scope_blocks` | `3b42cfc` | `D.scope` |
| token (revoked token blocked D.revoked) | `services/conformance-sentinel/tests/test_sentinel.py::test_revoked_token_blocks_with_clause` | `3b42cfc` | `D.revoked` |
| ledger (unreachable ledger blocks every action, L.unreachable) | `services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_ledger_down_blocks_everything` | `3b42cfc` | `L.unreachable` |
| ledger (enforce mode: an ALLOW whose ledger record failed is BLOCK, never metered) | `services/conformance-sentinel/tests/test_f2_fail_closed.py::test_enforce_failed_allow_append_is_block_l_unreachable_and_never_metered` | `3f82811` | `allow_record_failed` |
| rate window (exhausted window blocks E.rate_limit with retry_after) | `services/conformance-sentinel/tests/test_throttle_metering.py::test_exhausted_window_blocks_with_rate_limit_context_and_ledger` | `4b8b352` | `E.rate_limit` |
| intercepted at the LLM egress (only when FORCE_GATEWAY_ENFORCE=1 AND gateway is mandatory egress) | `services/force-gateway/tests/test_f1_enforce.py::test_killed_agent_is_refused_403_e_kill_switch_with_no_upstream_call` | `5ae3600` | `E.kill_switch` |

Declared:

- **agents route actions through /check at all (cooperative perimeter)** — README Declared only + LIMITS: a malicious process with direct tool access simply does not ask; the one-liner states this inline
- **continuously audits deployed agents (removed)** — No background audit loop is documented or tested; the service answers POST /check on request. Wording dropped
- **missing ledger writes (removed)** — README LIMITS: post-hoc executed-vs-ledgered reconciliation is not implemented or tested; only a pre-execution reachability gate exists
- **expired authority blocked (D.expired) at the sentinel** — Only evidence is the log-only scorecard seed EXP-01 (test_scorecard.py::test_per_seed_table_complete, would-be clause); no enforce-mode D.expired test in test_sentinel.py. Delegation's own expiry on introspect is Enforced under system 3. Left out of the new one-liner
- **FORCE gateway is the mandatory egress** — Network policy is operator-side; GB10 compose isolates canary-agent only; no estate runs it (pre-v1.2 images); Declared
- **semantic judgment of actions (judge)** — Judge default OFF on both estates; real-model path Declared-untested; not claimed
- **blocks vs observes on an estate** — Code default is log_only (README table: served default); the one-liner says 'In enforce mode'; per-estate mode is Declared per deploy config, not verified here

Reworded:

- "continuously audits deployed agents against their FIELD manifests" → "Checks each proposed action against the agent's manifest, token, kill status, ledger and rate window" — Audit row 2: it is a request-time POST /check, not a continuous auditor
- "at the policy-enforcement point" → "at the agent's action boundary (SDK/@governed; cooperative perimeter) ... also intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate)" — Audit row 2: cooperative check, not an interception point; F1 is real in code+tests (services/force-gateway/tests/test_f1_enforce.py) but only when the gateway is the mandatory egress
- "scope breaches, expired authority, missing ledger writes" → "kill status, token, scope, ledger reachability, rate window" — Audit row 2 / README LIMITS: missing-write detection not implemented; expired covered only by scorecard seed

## 3 — Delegation Authority Service

**Old (verbatim):** **3 — Delegation Authority Service** — scoped, expiring, revocable authority
tokens chained to the human delegation-of-authority matrix; every agent action
traces to a named human grant. OAuth for agents. (FIELD-D · GC)

**New:** Scoped, expiring, revocable delegation tokens bound to a registered, active agent; every mint and revoke is ledgered before it takes effect. Mint is checked against a DOA roster only when FIELD_DOA_ROSTER is set (whether either estate sets it is not verified here: delegation-authority README lines 212 and 235 disagree); grantor name recorded, not authenticated. OAuth-style: RFC 7662-shaped introspection of opaque database tokens, not an OAuth server.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| expiring (expired token fails introspection) | `services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_expired_token_fails_introspection` | `84c9c70` | `expired` |
| revocable (revoked token fails introspection; revoke idempotent) | `services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_revoked_token_fails_introspection` | `84c9c70` | `revoked` |
| ledgered before it takes effect (ledger down => 502, no token minted) | `services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_ledger_down_mint_fails_closed` | `84c9c70` | `refusing to mint` |
| scoped: mint refused when scope exceeds the grantor's roster scope (only when FIELD_DOA_ROSTER is set) | `services/delegation-authority/tests/test_doa_roster.py::test_scope_beyond_grantor_allowed_scope_is_403_d_grantor` | `9e5b642` | `draft invoices` |
| DOA roster check only when FIELD_DOA_ROSTER is set (off-roster grantor refused 403 D.grantor) | `services/delegation-authority/tests/test_doa_roster.py::test_grantor_off_roster_is_403_d_grantor` | `9e5b642` | `D.grantor` |
| RFC 7662-shaped introspection of opaque tokens | `services/delegation-authority/tests/test_oauth_introspect.py::test_active_token_exact_key_set_and_types` | `9e5b642` | `opaque` |

Declared:

- **grantor name recorded, not authenticated (the caller is the named grantor)** — README Declared only: granted_by is a string; roster proves membership of a string, not identity. Phase G operator-auth not live
- **DOA roster applies on an estate** — FIELD_DOA_ROSTER unset on both estates per plan qualifier and README:235; README:212 contradicts (see readme_rows_to_check); Declared until verified
- **every agent action traces to a named human grant (removed)** — Agents presenting tokens is the sentinel's check (Declared only); granted_by is free text
- **chained to the human DOA matrix (removed)** — No authority matrix beyond an optional membership roster; Declared
- **mint checks scope subset of manifest when roster unset** — Not enforced without the roster; the sentinel narrows at action time
- **OAuth for agents (removed)** — Not an OAuth 2.0 server: opaque DB records, no JWT/bearer, no caller client auth beyond shared secret

Reworded:

- "chained to the human delegation-of-authority matrix; every agent action traces to a named human grant" → "Mint is checked against a DOA roster only when FIELD_DOA_ROSTER is set (whether either estate sets it is not verified here: delegation-authority README lines 212 and 235 disagree); grantor name recorded, not authenticated" — Audit row 3: granted_by is free-text; roster membership list is not an identity check
- "OAuth for agents" → "OAuth-style: RFC 7662-shaped introspection of opaque database tokens, not an OAuth server" — Audit row 3: tokens are DB rows with bespoke introspect; README LIMITS says RFC 7662-shaped, not an OAuth 2.0 server

## 4 — Kill-Switch Command Plane

**Old (verbatim):** **4 — Kill-Switch Command Plane** — resolvable kill endpoints and heartbeats for
every registered agent; one-command domain shutdown and drill mode.
(FIELD-E · CEO/CISO)

**New:** One command halts an agent, or every agent in a registry domain, by flipping its registry status; its heartbeat poll then says halt and the sentinel blocks its next check. Drill mode kills, verifies, restores. Kill endpoints: allowlisted, best-effort signal, not a process stop; only canary-gb10 declares one. Heartbeats for agents that check in; none do on either estate today.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| One command halts an agent (registry status flipped, kill ledgered) | `services/kill-switch/tests/test_kill_switch.py::test_kill_agent_flips_registry_and_logs` | `557c7d9` | `killed` |
| every agent in a registry domain (and only that domain) | `services/kill-switch/tests/test_kill_switch.py::test_kill_domain_kills_only_that_domain` | `557c7d9` | `crm-agent` |
| heartbeat poll says halt (unknown agent told to halt, fail closed) | `services/kill-switch/tests/test_kill_switch.py::test_adversarial_unknown_agent_heartbeat_says_stop` | `557c7d9` | `unregistered` |
| Drill mode kills, verifies and restores | `services/kill-switch/tests/test_kill_switch.py::test_drill_kills_verifies_and_restores` | `557c7d9` | `restored_status` |
| kill succeeds during ledger outage (act-first) | `services/kill-switch/tests/test_kill_switch.py::test_kill_survives_ledger_outage` | `557c7d9` | `killed` |
| Kill endpoints: allowlisted, best-effort signal (called only when host allowlisted) | `services/kill-switch/tests/test_endpoint_and_liveness.py::test_allowlisted_endpoint_200_is_called_and_ledgered` | `f195168` | `kill.endpoint_called` |
| allowlisted (allowlist unset => never called; metadata IP skipped) | `services/kill-switch/tests/test_endpoint_and_liveness.py::test_adversarial_metadata_endpoint_skipped_with_allowlist_unset` | `f195168` | `allowlist_unset` |
| Heartbeats for agents that check in (POST records last_seen; GET never writes) | `services/kill-switch/tests/test_endpoint_and_liveness.py::test_checkin_records_last_seen_and_get_never_writes` | `f195168` | `GET must not write` |

Declared:

- **the agent's own process stops (in-flight halt)** — README Declared only: no process supervisor; endpoint call is a signal, not a stop; the one-liner says 'not a process stop'
- **heartbeats arrive from agents on an estate (none do today)** — No agent POSTs check-ins on either estate until SDK/skills redeploy; stale means no check-in, not dead process; estate pre-v1.2 images lack POST /heartbeat and /liveness
- **kill endpoint signal reaches an agent on an estate** — FIELD_KILL_ENDPOINT_ALLOWLIST unset on both estates; GB10 arming step A6 pending; Fly has no agent-side endpoint; real canary path proven only by packages/field-agent/tests/test_canary_agent.py (not run on the estate)
- **heartbeats for every registered agent (removed)** — Only for agents that check in; none do today
- **Operator authorization on kill/revive/drill (Phase G)** — REQUIRE not armed anywhere; Stage 1 LOG-ONLY only on the GB10; not claimed

Reworded:

- "resolvable kill endpoints" → "Kill endpoints: allowlisted, best-effort signal, not a process stop; only canary-gb10 declares an agent-side endpoint" — Audit row 4 (written 2026-09-12): the manifest endpoint was never called. Since v1.2 X3 the service resolves manifest_ref and calls the endpoint when the host is allowlisted, so the word is now Enforced in code with qualifiers
- "heartbeats ... for every registered agent" → "Heartbeats for agents that check in; none do on either estate today" — Server-side liveness exists only for agents that POST check-ins (README row 'Heartbeats: server-side liveness')
- "one-command domain shutdown" → "One command halts an agent, or every agent in a registry domain, by flipping its registry status" — Audit row 4: a kill is a registry status flip discovered by polling or at the next /check; domain = registry record field

## 5 — Sealed Ledger Service

**Old (verbatim):** Sealed Ledger Service — managed, cryptographically chained append-only record of agent actions with auditor read-only export and retention policies. (FIELD-L · CFO/audit committee)

**New:** Hash-chained (sha-256) record of agent actions with Ed25519-anchored heads; per-event ledger-signed when the signing key is set (caller authorship Declared); auditor export re-verifiable offline (served export unsigned); estate retention by segment rotation (mechanism; no estate rotates today, key custody undecided).

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| hash-chained | `services/sealed-ledger/tests/test_sealed_ledger.py::test_adversarial_on_disk_mutation_detected` | `04cf52f` | `mutated` |
| Ed25519-anchored | `services/sealed-ledger/tests/test_sealed_ledger.py::test_signed_anchor_tamper_detected` | `2e001e0` | `signature invalid` |
| per-event ledger-signed (when the signing key is set) | `services/sealed-ledger/tests/test_event_signing_f2.py::test_cli_verify_relinked_tamper_of_a_signed_event_fails_naming_the_index` | `3f82811` | `SIGNATURE INVALID` |
| auditor export re-verifiable offline | `services/sealed-ledger/tests/test_export_bundle.py::test_editing_one_exported_event_fails_naming_its_index` | `db5ad33` | `index 2` |
| (served export unsigned) | `services/sealed-ledger/tests/test_export_bundle.py::test_served_export_writes_signed_false` | `db5ad33` | `summary["signed"] is False` |
| retention by segment rotation (mechanism) | `services/sealed-ledger/tests/test_ledger_retention.py::test_archival_keeps_live_verify_ok_and_sidecar_verifies_standalone` | `700301d` | `archived_segments` |

Declared:

- **append-only** — dropped from the line: filesystem write access defeats it (README Declared 'Nobody can rewrite history at all', L559); plain verify is blind to a full re-chain (test pins it); only anchors held off-box detect it
- **managed** — dropped: single-process JSONL service, no managed/HA offering
- **read-only auditor** — dropped: no read-only auditor role; every shared-secret holder can call /export (README LIMITS L773-775)
- **caller authorship (F2b)** — Declared per plan: Enforced only where FIELD_LEDGER_CALLER_KEYRING is set (GB10 only, step A7b; evidence against actors without box access); Declared on Fly; tests exist (test_caller_signing_f2b.py) but estate arming is not live
- **per-event signing on the estates** — mechanism proven in CI only; FIELD_LEDGER_SIGN_KEY not armed on either estate (README L561, A7); both estates run pre-v1.2 images
- **no estate rotates today / key custody undecided** — deployment fact, not testable
- **Merkle** — chain is linear sha-256, not Merkle (README LIMITS ~L763); not claimed
- **off-box anchor placement / WORM** — deployment responsibility (README L559-560)
- **estate status** — Declared: pre-v1.2 images on both estates until redeploy

Reworded:

- "managed, cryptographically chained append-only record" → "Hash-chained (sha-256) record ... Ed25519-anchored heads" — audit row 5: 'crypto-chained' -> 'hash-chained, Ed25519-anchored'; no managed service; append-only not defensible against file access
- "auditor read-only export" → "auditor export re-verifiable offline (served export unsigned)" — no read-only role; /export dumps server-side, always unsigned; signed only via CLI --sign-key
- "retention policies" → "estate retention by segment rotation (mechanism; no estate rotates today, key custody undecided)" — audit row 5 found zero retention code; since built (rotate/archive/hold, C2) but not operated on any estate; manifest retention_days is only compared (retention check), not enforced per agent

## 6 — Incident Replay Agent

**Old (verbatim):** Incident Replay Agent — reconstructs from the ledger who authorized an agent, what it did, and which manifest clause failed; outputs the RACI-ready post-mortem. (FIELD-L · CISO)

**New:** Reconstructs from the sealed ledger who granted authority, what ran, and which manifest clause failed first, after verifying the chain (tampered or busy ledgers are flagged, never reported clean). RACI-seeded: R/A/C/I from registry, grant, manifest with labeled defaults; names are recorded strings, and replay is only as complete as the ledger.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| reconstructs who granted authority, what ran, which clause failed first | `services/incident-replay/tests/test_incident_replay.py::test_replay_reconstructs_incident` | `a88efb3` | `D.scope` |
| after verifying the chain (tampered ... flagged) | `services/incident-replay/tests/test_incident_replay.py::test_adversarial_tampered_ledger_flagged_loudly` | `a88efb3` | `LEDGER INTEGRITY FAILED` |
| busy ... never reported clean | `services/incident-replay/tests/test_raci_from_data.py::test_busy_ledger_is_unverified_never_a_broken_chain_and_never_ok` | `e96dc89` | `INTEGRITY NOT VERIFIED` |
| R from registry (labeled) | `services/incident-replay/tests/test_raci_from_data.py::test_responsible_is_registry_owner_labeled` | `e96dc89` | `(agent owner)` |
| A from grant | `services/incident-replay/tests/test_raci_from_data.py::test_covering_grant_beats_earlier_non_covering_grant` | `e96dc89` | `grant covering 'transfer funds'` |
| C/I from manifest with labeled defaults | `services/incident-replay/tests/test_raci_from_data.py::test_empty_or_absent_operators_use_clause_default` | `e96dc89` | `(default)` |

Declared:

- **complete trail** — replay is only as complete as the ledger; actions outside the sentinel/decorator perimeter never become events (README L84, LIMITS)
- **authenticated names** — grantor/operator names are recorded strings, not authenticated identities (LIMITS)
- **Accountable = the token presented** — names a grant covering the failing action; conformance events do not record the token id (LIMITS)
- **manifest as at the incident** — manifest is read at replay time; later edits change Consulted/Informed for past incidents (LIMITS)
- **C/I are org-chart facts** — fallbacks are a static clause-letter->exec map and 'CEO / board (attestation-reporter)'
- **estate status** — Declared: pre-v1.2 images on both estates until redeploy

Reworded:

- "RACI-ready post-mortem" → "RACI-seeded: R/A/C/I from registry, grant, manifest with labeled defaults" — audit row 6: C/I are defaults when the manifest has no operators/principal
- "reconstructs from the ledger" → "reconstructs from the sealed ledger ... after verifying the chain (tampered or busy ledgers are flagged)" — integrity-first behaviour is real and tested; completeness is not claimed
- "(audit note) blind to conformance.shadow_*" → "not a reword: shadow verdicts are now handled (test_shadow_block_is_first_failure_labeled_log_only, labeled log-only)" — audit row 6 gap closed in code

## 7 — Compliance Crosswalk Engine

**Old (verbatim):** Compliance Crosswalk Engine — Maps every FIELD manifest to OSFI E-23, EU AI Act, ISO 42001, and NIST AI RMF control requirements, and generates the evidence pack on demand.

**New:** Maps FIELD manifest fields to OSFI E-23, EU AI Act and NIST AI RMF controls, citing only retrieved text (ISO/IEC 42001 pending text purchase, none cited). On-demand evidence pack: named signer required, unsigned, blocked while a source-change flag stands. Scheduled content-change detection of cited sources (semantics by named review; live fetch verified manually, not in CI).

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| citing only retrieved text; ISO/IEC 42001 pending text purchase | `services/compliance-crosswalk/tests/test_crosswalk.py::test_adversarial_no_ungrounded_citations` | `f6e78fc` | `pending-purchase` |
| on-demand evidence pack: named signer required | `services/compliance-crosswalk/tests/test_evidence_pack.py::test_signer_required_empty_and_whitespace` | `806d8c0` | `no pack ships without a named signer` |
| unsigned (named signer, no cryptographic signature) | `services/compliance-crosswalk/tests/test_evidence_pack.py::test_pack_markdown_contents` | `806d8c0` | `This pack carries no cryptographic signature` |
| blocked while a source-change flag stands | `services/compliance-crosswalk/tests/test_pack_api.py::test_adversarial_stale_flag_409_names_framework_and_affected_controls` | `f69f9ae` | `there is no override` |
| content-change detection of cited sources | `services/compliance-crosswalk/tests/test_regwatch.py::test_changed_bytes_flag_with_url_sha_prefixes_and_byte_diff` | `4b8b352` | `raw bytes` |
| scheduled | `services/compliance-crosswalk/tests/test_regwatch.py::test_served_scheduler_runs_a_check_after_the_interval` | `4b8b352` | `"scheduler"` |

Declared:

- **mapping correctness / sufficiency** — mapping is conservative: 16 of 52 control x framework cells cited (OSFI 5/13, EU AI Act 5/13, NIST 6/13, ISO 0/13; counted from mapping.CONTROLS 2026-10-30, no test pins the count); correctness needs expert review (README L278-279). EU Arts 12/14 via mirror, EUR-Lex cross-check open
- **ISO/IEC 42001** — all 13 entries pending-purchase; text not bought
- **continuous** — dropped: no continuous monitoring (SPEC L28 point-in-time); OSFI page returns HTTP 403 to this client so OSFI is detected only via manual `regwatch check-file` (README L318-325); daily cadence on an estate Declared (L291)
- **live fetch of real sources** — CROSSWALK_LIVE_FETCH=1 test is manual, not CI; README L287
- **flagged change is material** — content change not semantics; named human re-review decides (README L290)
- **pack cryptographically signed / signer verified** — signer is a recorded name; served packs unsigned drafts (F4 covers attestation-reporter, not crosswalk) (README L275)
- **compliance/sufficiency** — coverage of controls is not compliance with a regulation; the pack never says 'you comply' (test_word_discipline_complian_only_in_disclaimer)
- **crosswalk served on estates** — CLI by design; serve exists but uncomposed (audit row 7); estate status Declared, pre-v1.2 images

Reworded:

- "Maps every FIELD manifest" → "Maps FIELD manifest fields ... controls, citing only retrieved text" — audit row 7: only part of the grid is grounded; unverified entries carry no reference
- "ISO 42001" → "ISO/IEC 42001 (pending text purchase, none cited)" — audit row 7: 0 cells grounded; test forbids citing it
- "(plan word) Continuous" → "Scheduled content-change detection ... (semantics by named review; live fetch verified manually, not in CI)" — Deviation from plan qualifier: the word 'Continuous' is not used because OSFI blocks the client (403) so detection there is manual, and the interval daemon only exists under `serve --every`. All plan sub-qualifiers retained.
- "generates the evidence pack on demand" → "On-demand evidence pack: named signer required, unsigned, blocked while a source-change flag stands" — audit row 7: pack gates are real; no cryptographic signing

## 8 — Federation Broker

**Old (verbatim):** Federation Broker — trust gateway for agents crossing org boundaries; validates counterparty manifests, enforces data-scope borders, records inter-org contract semantics. (FIELD-F · CIO/GC)

**New:** Crossing-decision service, not a traffic proxy: validates counterparty manifests, verifies their Ed25519 signature inbound against a contract-registered key (keyless contract blocks inbound), allows only the contract's scopes and data-class labels (envelope only, no payload inspection), and ledgers each verdict. Cooperative: an agent that does not ask is invisible.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| validates counterparty manifests | `services/federation-broker/tests/test_federation_broker.py::test_adversarial_invalid_manifest_blocked` | `4ead650` | `I.manifest` |
| verifies their Ed25519 signature inbound against a contract-registered key | `services/federation-broker/tests/test_federation_broker.py::test_adversarial_tampered_manifest_after_signing_blocked` | `ab55dd1` | `signature invalid` |
| keyless contract blocks inbound | `services/federation-broker/tests/test_federation_broker.py::test_keyless_contract_blocks_an_inbound_crossing` | `aa73df5` | `inbound crossings require a contract key` |
| allows only the contract's ... data-class labels | `services/federation-broker/tests/test_federation_broker.py::test_out_of_contract_data_class_blocked` | `4ead650` | `customer PII` |
| ledgers each verdict | `services/federation-broker/tests/test_federation_broker.py::test_governed_crossing_allowed` | `4ead650` | `federation.allow` |
| outbound mirror (our agent held to the same contract) | `services/federation-broker/tests/test_federation_outbound.py::test_outbound_in_contract_allowed_with_direction_in_context_and_ledger` | `4b8b352` | `outbound` |

Declared:

- **trust gateway for traffic** — dropped: decision API (POST /crossing -> ALLOW/BLOCK); nothing is proxied or relayed (README L1-5, L107)
- **data-scope borders on content** — gates the request envelope's data_class label; no payload inspection (README L109)
- **agent asks before crossing** — cooperative: field-agent SDK `cross` asks first, but an agent that crosses without asking is invisible (README L105, L107)
- **replay protection / freshness** — no nonce, timestamp or window; a captured signed manifest verifies again (README L107)
- **outbound manifest authenticity** — outbound is not signature-checked; broker does not fetch registry manifest_ref (README L104, LIMITS)
- **contract signed by both GCs** — contract_ref points at the instrument; broker records, does not verify (README L108)
- **key rotation / revocation** — none; key exchange out-of-band (LIMITS)
- **ledger delivery** — best-effort (README L97)
- **estate status** — Declared: pre-v1.2 images on both estates until redeploy

Reworded:

- "trust gateway for agents crossing org boundaries" → "Crossing-decision service, not a traffic proxy" — audit row 8: nothing passes through it
- "enforces data-scope borders" → "allows only the contract's scopes and data-class labels (envelope only, no payload inspection)" — audit row 8: string membership on a caller-supplied label
- "validates counterparty manifests" → "validates ... verifies Ed25519 signature inbound against a contract-registered key (keyless contract blocks inbound)" — audit row 8 said keyless = consistency only; fixed in code by C-175/D-19 (keyless now BLOCKs inbound), tested
- "records inter-org contract semantics" → "allows only the contract's scopes and data-class labels" — contract store holds allowed scopes/data classes, one active per org; no semantics beyond that

## 9 — Spend & Resource Governor

**Old (verbatim):** Spend & Resource Governor — real-time metering of every agent's token, compute, and action spend against manifest caps; throttles at thresholds, escalates to a human before the budget event. (FIELD-E · CFO/CTO)

**New:** Meters agent tokens and actions against manifest caps in integer cents; escalates to a human queue at 80% before the cap; reports BLOCK at the cap and THROTTLED over rolling per-action windows (periods the governor can parse; session Declared). Actions metered at the sentinel, tokens at the gateway; otherwise self-reported; compute has no observer (dropped).

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| integer cents (no float drift) | `services/spend-governor/tests/test_spend_governor.py::test_adversarial_integer_threshold_no_float_drift` | `0769024` | `599_999` |
| escalates to a human queue at 80% before the cap | `services/spend-governor/tests/test_spend_governor.py::test_threshold_escalates_before_cap` | `0769024` | `exactly 80%` |
| reports BLOCK at the cap | `services/spend-governor/tests/test_spend_governor.py::test_hard_cap_blocks` | `0769024` | `cap reached` |
| THROTTLED over rolling per-action windows | `services/spend-governor/tests/test_throttle.py::test_action_window_n_allowed_then_throttled_until_the_period_passes` | `4b8b352` | `retry_after_seconds` |
| tokens priced from the model against the cap | `services/spend-governor/tests/test_usage.py::test_escalate_before_cap_on_token_cost` | `dbedd29` | `claude-opus-4-8` |
| actions metered at the sentinel | `services/conformance-sentinel/tests/test_throttle_metering.py::test_one_allow_meters_exactly_one_and_self_stays_zero` | `4b8b352` | `spent_actions_metered` |
| tokens metered at the gateway | `services/force-gateway/tests/test_f1_enforce.py::test_allowed_call_is_forwarded_injected_and_metered_for_the_header_agent` | `5ae3600` | `usage.recorded` |

Declared:

- **otherwise self-reported (spend truthful)** — README:130 Declared only; an agent that never calls /spend never hits the cap
- **compute metering** — dropped: no observer exists (README:130); the word is removed, not Declared
- **session rate limits** — stored declared_unenforced, never throttles (README:134)
- **BLOCK/THROTTLED stop the agent** — service only reports state; stopping is the sentinel's /check, and the gateway only under ENFORCE=1 as mandatory egress (README:131)
- **live on either estate** — estates run pre-v1.2 images until redeploy

Reworded:

- "real-time metering of every agent's token, compute, and action spend" → "meters agent tokens and actions ... metered at the sentinel / gateway, otherwise self-reported; compute dropped" — audit row 9: no compute dimension; self-reported unless via sentinel/gateway (F3 real in code+tests; deployment Declared; platform metering holds only for agents that pass through the sentinel/gateway)
- "throttles at thresholds" → "reports THROTTLED over rolling per-action windows" — audit row 9: state only, nothing is rate-limited or rejected here; nothing answers 429 (README:10)
- "escalates to a human before the budget event" → "escalates to a human queue at 80% before the cap" — mechanism is exact; a human-review queue, no notification channel claimed

## 10 — FORCE Gateway

**Old (verbatim):** FORCE Gateway — An LLM-traffic proxy that injects FORCE runtime constraints on outbound model calls and dashboards hygiene telemetry. Governs what the AI says while FIELD governs what it is.

**New:** Reverse proxy that injects the FORCE runtime protocol into model calls routed through it, preserving the caller's system prompt, and records regex hygiene telemetry (mechanism; judge and sycophancy drift off on both estates). Fails open. With ENFORCE=1 and the gateway as mandatory egress (not deployed so on either estate) it also intercepts calls. Not org-wide.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| injects the FORCE runtime protocol | `services/force-gateway/tests/test_force_gateway.py::test_inject_preserves_string_system` | `b6f3a7d` | `# FORCE Runtime Protocol` |
| preserving the caller's system prompt | `services/force-gateway/tests/test_force_gateway.py::test_inject_preserves_block_list_system` | `b6f3a7d` | `You are the invoicing agent.` |
| regex hygiene telemetry | `services/force-gateway/tests/test_force_gateway.py::test_telemetry_detects_force_markers` | `b6f3a7d` | `confidence_tags == 2` |
| hygiene rates (null for an empty window) | `services/force-gateway/tests/test_d2_rates.py::test_mixed_responses_rate_half` | `4b8b352` | `0.5, 0.5, 0.5` |
| sycophancy drift alert (mechanism) | `services/force-gateway/tests/test_d2_drift_dimensions.py::test_sycophancy_drifts_while_overall_holds_exactly_one_sycophancy_alert` | `4b8b352` | `sycophancy` |
| fails open | `services/force-gateway/tests/test_gateway_delta.py::test_instrumentation_fault_bypasses_without_failing_traffic` | `a92bbe4` | `telemetry crashed` |
| intercepts calls at the egress under ENFORCE=1 | `services/force-gateway/tests/test_f1_enforce.py::test_killed_agent_is_refused_403_e_kill_switch_with_no_upstream_call` | `5ae3600` | `E.kill_switch` |
| tokens metered at the egress for the header's agent | `services/force-gateway/tests/test_f1_flags.py::test_f3_a_forwarded_request_meters_the_response_tokens_for_the_header_agent` | `5ae3600` | `force-gateway LLM call` |

Declared:

- **org-wide** — opt-in via ANTHROPIC_BASE_URL/agent config; agents route through it cooperatively (README:267); platform judge calls are passthrough, excluded from hygiene telemetry; dropped from the one-liner
- **mandatory egress / ENFORCE=1 live** — README:268,273: estates run enforce=0; only GB10 canary-agent has the gateway as its sole LLM path; Fly Declared
- **sycophancy drift signal on the estates** — README:253: judge OFF on both estates, no judgments, no series
- **model obeys the FORCE block / telemetry equals compliance** — README:265-266 Declared; markers are heuristics
- **streaming** — stream:true is not intercepted (LIMITS)
- **GB10 real upstream** — audit row 10: GB10 ran --mock; estate status Declared

Reworded:

- "injects FORCE runtime constraints on outbound model calls" → "injects ... into model calls routed through it" — audit row 10: opt-in routing; Declared cooperative perimeter
- "dashboards hygiene telemetry" → "records regex hygiene telemetry (mechanism)" — audit row 10: heuristic counts/rates; judge off on both estates; no dashboard claim made
- "Governs what the AI says while FIELD governs what it is" → "(dropped)" — injection is not compliance (README:265); no claim of governing output
- "(none)" → "With ENFORCE=1 ... intercepts calls (F1 variant, qualified)" — F1 real in code+tests (test_f1_enforce.py); qualifier 'when mandatory egress, not deployed as such' kept

## 11 — Agent Lifecycle Manager

**Old (verbatim):** Agent Lifecycle Manager — provisioning-to-decommission: authority expiry, re-attestation cadences, orphan detection for agents whose human owner left. (FIELD-I/D · CIO/CHRO)

**New:** Detects expiring authorities, stale re-attestation (attester name recorded, not authenticated) and orphaned agents against an owners roster; auto-kill only with an explicit flag. CLI provision (validate, register, cap, mint) and decommission (revoke, kill, retire). Sweep not scheduled on either estate (roster unset).

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| expiring authorities | `services/lifecycle-manager/tests/test_lifecycle_manager.py::test_sweep_findings` | `7ce20b5` | `days_left == 10` |
| orphaned agents against an owners roster | `services/lifecycle-manager/tests/test_lifecycle_manager.py::test_sweep_findings` | `7ce20b5` | `lifecycle.orphan` |
| auto-kill only with an explicit flag | `services/lifecycle-manager/tests/test_lifecycle_manager.py::test_adversarial_auto_kill_requires_flag` | `7ce20b5` | `auto_kill_orphans=False` |
| stale re-attestation (attester name recorded) | `services/lifecycle-manager/tests/test_transitions.py::test_attesting_moves_the_basis_and_names_the_attester` | `017a10f` | `attested_by` |
| staleness cannot be hidden by editing the record | `services/lifecycle-manager/tests/test_transitions.py::test_adversarial_kill_revive_cycle_does_not_hide_staleness` | `017a10f` | `reattestation_due` |
| provision (validate, register, cap, mint) | `services/lifecycle-manager/tests/test_transitions.py::test_happy_path_provision_registers_caps_and_mints` | `017a10f` | `"validate", "register", "cap", "mint"` |
| decommission (revoke, kill, retire) | `services/lifecycle-manager/tests/test_transitions.py::test_decommission_revokes_kills_retires_and_records` | `017a10f` | `lifecycle.decommissioned` |

Declared:

- **attester is the human who attested** — README: attested_by is a recorded string, not an authenticated identity
- **re-attestation actually happens** — sweep reports staleness; a human must call registry attest; platform does not verify the review
- **roster current/complete; aliases name the same human** — declared by whoever writes the CSV
- **sweep runs on schedule on the estates** — deployed on both estates but FIELD_LIFECYCLE_ROSTER unset until arming A1: every tick is a recorded skip
- **decommission is final at the registry** — final at the kill-switch only; PATCH /agents/{id} can set retired back to active (LIMITS)
- **provision/decommission atomic** — neither is atomic or rolled back; reports say where the run stopped

Reworded:

- "provisioning-to-decommission" → "CLI provision (validate, register, cap, mint) and decommission (revoke, kill, retire)" — audit row 11 said no provisioning code and no retire path; both now exist (test_transitions.py), so the words are kept but scoped to CLI transitions; not atomic; retire reversible at the registry
- "re-attestation cadences" → "stale re-attestation (attester name recorded, not authenticated)" — audit row 11: was proxied from registry updated_at; now attested_at else created_at, name unauthenticated
- "orphan detection for agents whose human owner left" → "orphaned agents against an owners roster" — exact-string roster match; no HR link; roster currency Declared
- "(none)" → "Sweep not scheduled on either estate (roster unset)" — README Declared row: every scheduled tick is a recorded skip

## 12 — Executive Attestation Reporter

**Old (verbatim):** Executive Attestation Reporter — board-level rollup: agents in production, conformance percentage, incidents and replays, expiring authorities; generates the quarterly AI-governance attestation the CEO signs. (all letters · CEO/board)

**New:** Board pack of estate counts, shadow-aware conformance % (formula printed) and incident counts; no number without its source query, unavailable never zero, tampered chain shown BROKEN. Windowed to a UTC quarter; Ed25519-signed by a named signer via CLI; served packs are unsigned drafts unless the estate key is set. Key custody Declared.

**Deployment status:** Declared (estates run pre-v1.2 images).

| Enforced word | Test | Commit | Needle |
|---|---|---|---|
| no number without its source query | `services/attestation-reporter/tests/test_attestation_reporter.py::test_every_number_has_a_source` | `655b63d` | `lacks a source query` |
| unavailable never zero | `services/attestation-reporter/tests/test_attestation_reporter.py::test_adversarial_unavailable_service_never_fabricates_zero` | `655b63d` | `unavailable` |
| shadow-aware conformance % (formula printed) | `services/attestation-reporter/tests/test_attestation_reporter.py::test_log_only_shadow_verdicts_lower_the_conformance_rate` | `99ab9cb` | `37.5` |
| tampered chain shown BROKEN | `services/attestation-reporter/tests/test_attestation_reporter.py::test_broken_ledger_shows_in_pack` | `655b63d` | `BROKEN` |
| UTC quarter window | `services/attestation-reporter/tests/test_c4_window_and_signature.py::test_parse_period_both_spellings_give_the_utc_quarter` | `135330a` | `2026-10-01T00:00:00+00:00` |
| counts only in-window events | `services/attestation-reporter/tests/test_c4_window_and_signature.py::test_hand_chained_ledger_counts_only_in_window_events_and_stays_intact` | `135330a` | `2 / (2+1+0+0+0)` |
| signed by a named signer via CLI | `services/attestation-reporter/tests/test_c4_window_and_signature.py::test_cli_render_signs_and_verify_exits_0_1_1` | `135330a` | `signed by Don Hagell` |
| Ed25519 signature | `services/attestation-reporter/tests/test_c4_window_and_signature.py::test_verify_refuses_a_duplicated_key_a_non_finite_number_and_a_respelled_signature` | `135330a` | `Ed25519` |
| served packs unsigned drafts unless the estate key is set | `services/attestation-reporter/tests/test_f4_served_signing.py::test_served_pack_is_signed_by_the_estate_key_and_verifies_with_attest_verify` | `b648118` | `estate-key` |

Declared:

- **valid signature means the named person approved** — README: proves key + unaltered bytes only; key custody and the signer string are outside the service
- **estate-key signature = custodian review** — README: not the case by design; standing attestation, re-signed per request
- **estate key readable only by attest** — compose config; on Fly every process in the container can read it
- **CEO/board signs** — signer is a free string; any CEO signature is a human act outside the service
- **incidents and replays** — dropped: pack has no incident-replay metric; incidents are proxy event counts (blocks, escalates, kills, drills, federation)
- **pack covers everything the org runs** — covers what the platform governs only
- **signing live on estates** — FIELD_ATTEST_SIGNER/KEY arming step; estates pre-v1.2 until redeploy
- **tail-deletion detection** — a deleted tail record reads INTACT (README, pinned by test)

Reworded:

- "quarterly" → "windowed to a UTC quarter (--period)" — audit row 12: --period was a caption; C4 added strict UTC quarter windows. Point-in-time figures (registry, tokens, escalations, integrity) are as of generation, not quarter-end; archive per quarter
- "generates the quarterly AI-governance attestation the CEO signs" → "Ed25519-signed by a named signer via CLI; served packs unsigned drafts unless the estate key is set" — audit row 12: nothing signed; C4/F4 added signing. Name is a string, key custody Declared; no CEO claim
- "incidents and replays" → "incident counts" — no replay metric in the pack
- "expiring authorities" → "(pack row kept; not a word of the one-liner)" — covers tokens only, not attestations
