Both estates run pre-v1.2 images; every Enforced word is test/CI-proven; per-system estate status is Declared until redeploy.

# v2 one-liners: old wording, new wording, Enforced and Declared (Phase E, E1)

**Old-wording provenance.** The "old" wording of each row is quoted verbatim from `docs/capstone-evidence/v2-one-liners-source.md` (recovered 2026-09-12 from the build prompt, outside this repository), which is the text the 2026-09-12 audit (`tasks/audit-v2-12-systems-vs-production-build-2026-09-12.md`, not read for this file) checked the build against. The audit paraphrases some fragments ("API-key scans", "Continuous", "org-wide"); where it does, the row says so and quotes the source text. Numbering is the audit's, 1 to 12.

**How to read a row.** An *Enforced* word is a line `- ENFORCED: <word> | CITE: <path>::<test_name> @ <commit> | KEY: <token>`: a test at that commit whose source mentions the key. `python tools/check_one_liners.py` confirms, for every such line, that the commit exists, the file exists at it, the test function exists in it and its source contains the key. It does not run the test and cannot judge whether the test proves the word: that is the independent adversarial review the E-gate also requires. Every cited test was also run on 3804d0b9 for this file (see the pull request). A *Declared* word has no test or no implementation, or is only a mechanism. The Deployment status column is Declared for every row: nothing was armed or redeployed when this was written (G16 is unrecorded), so no row claims a live state.

**Not in this file (by the E1 decision):** README and ROADMAP edits (E2), STATE.md (E3), live catalogue evidence, the declared ledger, soak evidence, canary demonstrations. A row whose words depend on a real model call carries a keyless line (not live-verified, needs the API key).

## 1 — Agent Registry

**Old wording** (verbatim, `v2-one-liners-source.md` row 1): "the passport office" — system of record where every AI agent is registered with identity, owner, and FIELD manifest; discovers unregistered shadow agents by scanning service accounts, API keys, and workflow platforms.

**New wording:** A register of agents (one record per unique agent id, a non-empty human owner string, and a manifest reference that must resolve to a valid manifest when one is set at registration) with discovery of unregistered shadow-agent candidates from supplied artifacts: service-account CSVs, an n8n workflow export, and API-key scans (file-based, heuristic).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "every AI agent" is not true (discovery sees only the artifacts it is given); "FIELD manifest" is optional at registration and is checked only then; "workflow platforms" is one platform, an n8n JSON export (the audit paraphrases the old text as "API-key scans"; the old text says "API keys").

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: one record per agent id | CITE: services/agent-registry/tests/test_agent_registry.py::test_duplicate_registration_conflicts @ 3804d0b9 | KEY: conflicts
- ENFORCED: a non-empty human owner | CITE: services/agent-registry/tests/test_registry_update_validation.py::test_create_with_an_empty_name_or_owner_is_422 @ 3804d0b9 | KEY: owner
- ENFORCED: a set manifest reference must resolve at registration | CITE: services/agent-registry/tests/test_d3b_manifest_ref_resolves.py::test_an_unresolvable_set_ref_is_422_and_nothing_is_written @ 3804d0b9 | KEY: unresolvable
- ENFORCED: discovers unregistered shadow-agent candidates | CITE: services/agent-registry/tests/test_agent_registry.py::test_discovery_finds_shadow_agents @ 3804d0b9 | KEY: shadow
- ENFORCED: by scanning service accounts (a CSV you export) | CITE: services/agent-registry/tests/test_agent_registry.py::test_discovery_finds_shadow_agents @ 3804d0b9 | KEY: bot-crm-enrich
- ENFORCED: API-key scans (file-based, heuristic) | CITE: services/agent-registry/tests/test_d3_credential_scan.py::test_the_fixture_inventory_surfaces_exactly_the_four_shadow_keys @ 3804d0b9 | KEY: shadow

**Declared words** (no test, no implementation, or only a mechanism): every AI agent registered (org-wide completeness); the owner is a real, current human; the manifest reference stays valid after registration; live IAM, cloud or secret-manager scanning; workflow platforms other than n8n; discovery as a verdict (it is a review queue).

Qualifier: API-key scans (file-based, heuristic)

## 2 — Conformance Sentinel

**Old wording** (verbatim, `v2-one-liners-source.md` row 2): An agent that continuously audits deployed agents against their FIELD manifests and blocks non-conforming actions at the policy-enforcement point — scope breaches, expired authority, missing ledger writes — before they execute.

**New wording:** A policy-enforcement service that, when FIELD_SENTINEL_MODE=enforce (the served default is log-only, which blocks nothing), checks each action put to it at the agent's action boundary (SDK/@governed; cooperative perimeter) against the agent's FIELD manifest and delegation token, and returns ALLOW, BLOCK or ESCALATE with a clause id; it blocks scope breaches, killed agents, and no-ledger cases before the guarded function runs, and records each verdict in the sealed ledger. + intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "An agent that continuously audits" has no implementation: the sentinel is a request-driven service (POST /check) with no scheduler or loop, and its LLM judge is optional and off by default. "Missing ledger writes" is not detected after the fact (post-hoc reconciliation is not implemented); what is enforced is that the ledger must be reachable and appendable before an action is allowed.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: blocks (enforce mode only) | CITE: services/conformance-sentinel/tests/test_sentinel.py::test_enforce_mode_still_blocks @ 3804d0b9 | KEY: BLOCK
- ENFORCED: scope breaches | CITE: services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_out_of_scope_blocks @ 3804d0b9 | KEY: D.scope
- ENFORCED: killed agents | CITE: services/conformance-sentinel/tests/test_sentinel.py::test_killed_agent_blocks_instantly @ 3804d0b9 | KEY: E.kill_switch
- ENFORCED: no ledger, no action | CITE: services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_ledger_down_blocks_everything @ 3804d0b9 | KEY: L.unreachable
- ENFORCED: an allow whose own record fails to append is a BLOCK (enforce mode) | CITE: services/conformance-sentinel/tests/test_f2_fail_closed.py::test_enforce_failed_allow_append_is_block_l_unreachable_and_never_metered @ 3804d0b9 | KEY: allow
- ENFORCED: before the guarded function runs (@governed) | CITE: services/conformance-sentinel/tests/test_sentinel.py::test_governed_decorator_allows_and_blocks @ 3804d0b9 | KEY: never
- ENFORCED: against their FIELD manifests (an invalid manifest blocks) | CITE: services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_invalid_manifest_blocks @ 3804d0b9 | KEY: I.manifest
- ENFORCED: expired authority, as a D.expired verdict (log-only scorecard seed; shadow, not an enforce-mode test) | CITE: services/conformance-sentinel/tests/test_scorecard.py::test_per_seed_table_complete @ 3804d0b9 | KEY: D.expired

**Declared words** (no test, no implementation, or only a mechanism): continuously audits (no loop); agent (a service; the judge is off by default); missing ledger writes (post-hoc reconciliation); agents routing their actions through /check at all; semantic understanding quality; "blocks" as an estate-wide fact (the served default is log-only); a direct enforce-mode test of D.expired (only the log-only seed and the delegation test of token expiry exist).

Qualifier: at the agent's action boundary (SDK/@governed; cooperative perimeter)

KEYLESS: not live-verified - needs ANTHROPIC_API_KEY (the semantic judge: every judge test uses a deterministic mock).

## 3 — Delegation Authority Service

**Old wording** (verbatim, `v2-one-liners-source.md` row 3): scoped, expiring, revocable authority tokens chained to the human delegation-of-authority matrix; every agent action traces to a named human grant. OAuth for agents. (FIELD-D · GC)

**New wording:** Scoped, expiring, revocable delegation tokens for registered, active agents, minted and revoked ledger-first, with OAuth-style (RFC 7662-shaped) introspection, and a mint-time check of the grantor name, scope and lifetime against a roster of human grantors when FIELD_DOA_ROSTER is set (unset on both estates); grantor name recorded, not authenticated.

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "chained to the DOA matrix" is a roster-membership check at mint, and only when FIELD_DOA_ROSTER is set; "every agent action traces to a named human grant" is not proven end to end (the grantor is on the mint event, the sentinel's allow event carries only the token id, and no test joins them); "OAuth for agents" is an RFC 7662-shaped introspection of opaque tokens, not an OAuth server.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: scoped | CITE: services/delegation-authority/tests/test_oauth_introspect.py::test_scope_is_rfc_string_and_scope_list_keeps_the_spaces @ 3804d0b9 | KEY: scope_list
- ENFORCED: expiring | CITE: services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_expired_token_fails_introspection @ 3804d0b9 | KEY: expired
- ENFORCED: revocable | CITE: services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_revoked_token_fails_introspection @ 3804d0b9 | KEY: revok
- ENFORCED: minted ledger-first (no ledger, no token) | CITE: services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_ledger_down_mint_fails_closed @ 3804d0b9 | KEY: fails_closed
- ENFORCED: only for registered, active agents | CITE: services/delegation-authority/tests/test_delegation_authority.py::test_mint_refused_for_killed_agent @ 3804d0b9 | KEY: killed
- ENFORCED: a mint ledgers the grantor name | CITE: services/delegation-authority/tests/test_pins_c198.py::test_the_mint_event_carries_its_pinned_fields @ 3804d0b9 | KEY: granted_by
- ENFORCED: grantor, scope and lifetime checked against a roster (when FIELD_DOA_ROSTER is set) | CITE: services/delegation-authority/tests/test_doa_roster.py::test_grantor_off_roster_is_403_d_grantor @ 3804d0b9 | KEY: D.grantor
- ENFORCED: OAuth-style introspection | CITE: services/delegation-authority/tests/test_oauth_introspect.py::test_active_token_exact_key_set_and_types @ 3804d0b9 | KEY: token_type

**Declared words** (no test, no implementation, or only a mechanism): chained to the human DOA matrix (a roster, not an identity check); every agent action traces to a named human grant; the caller is the named grantor (under an armed operator mode the grantor must equal the caller's own id or alias); OAuth proper (no token endpoint, no signed tokens); scope strings carry meaning (exact-string match only).

Qualifiers: when FIELD_DOA_ROSTER is set (unset on both estates); grantor name recorded, not authenticated. OAuth-style.

Estate value of FIELD_DOA_ROSTER: the repository contradicts itself. The compose and Fly defaults leave it unset; `services/delegation-authority/README.md` has one row saying it is set on both estates as of 2026-10-23 (presence-only) and a LIMITS bullet saying it is unset until arming step A3; STATE.md:906-920 records A3 armed on the GB10 and on Fly on 2026-09-14. The plan's "unset on both estates" is therefore an estate fact this repository cannot establish: it stays as the plan wrote it, and it is Declared until redeploy.

## 4 — Kill-Switch Command Plane

**Old wording** (verbatim, `v2-one-liners-source.md` row 4): resolvable kill endpoints and heartbeats for every registered agent; one-command domain shutdown and drill mode. (FIELD-E · CEO/CISO)

**New wording:** Registry-flip kill of a registered, non-retired agent (one command per agent or per domain) with a measured, self-restoring drill; kill endpoints allowlisted, best-effort; only the GB10 canary manifest declares an agent-side endpoint, and the allowlist is unset on both estates; heartbeats for agents that check in; none do on either estate today.

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "resolvable kill endpoints … for every registered agent": the registry flip works for any registered, non-retired agent, but the outbound halt signal is sent only when FIELD_KILL_ENDPOINT_ALLOWLIST names the host and only one shipped manifest declares an agent-side endpoint; "heartbeats for every registered agent" is true only for agents that post check-ins. The plan's qualifier "no shipped manifest declares an agent-side endpoint" is false: `manifests/canary-gb10.yaml:49` declares `http://canary-agent:8090/halt` (and `services/kill-switch/README.md` row "Resolvable kill endpoints" says one shipped manifest does). See "Deviations".

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: one-command domain shutdown | CITE: services/kill-switch/tests/test_kill_switch.py::test_kill_domain_kills_only_that_domain @ 3804d0b9 | KEY: domain
- ENFORCED: drill mode | CITE: services/kill-switch/tests/test_kill_switch.py::test_drill_kills_verifies_and_restores @ 3804d0b9 | KEY: drill
- ENFORCED: kill of a registered agent flips the registry | CITE: services/kill-switch/tests/test_kill_switch.py::test_kill_agent_flips_registry_and_logs @ 3804d0b9 | KEY: registry
- ENFORCED: an unknown agent is told to halt | CITE: services/kill-switch/tests/test_kill_switch.py::test_adversarial_unknown_agent_heartbeat_says_stop @ 3804d0b9 | KEY: unregistered
- ENFORCED: the halt signal is called when the allowlist names the host | CITE: services/kill-switch/tests/test_endpoint_and_liveness.py::test_allowlisted_endpoint_200_is_called_and_ledgered @ 3804d0b9 | KEY: allowlist
- ENFORCED: nothing is sent when the allowlist is unset | CITE: services/kill-switch/tests/test_endpoint_and_liveness.py::test_adversarial_metadata_endpoint_skipped_with_allowlist_unset @ 3804d0b9 | KEY: allowlist_unset
- ENFORCED: heartbeats: stale after the window | CITE: services/kill-switch/tests/test_endpoint_and_liveness.py::test_liveness_stale_window_on_a_frozen_clock @ 3804d0b9 | KEY: stale
- ENFORCED: heartbeats: a check-in records last_seen | CITE: services/kill-switch/tests/test_endpoint_and_liveness.py::test_checkin_records_last_seen_and_get_never_writes @ 3804d0b9 | KEY: last_seen

**Declared words** (no test, no implementation, or only a mechanism): a kill stops the agent's process (the halt is the registry flip the sentinel reads plus the agent's own next check); estate-wide kill endpoints; heartbeats from every agent (stale means no check-in, not a dead process); the canary round trip on an estate.

Qualifiers: allowlisted, best-effort; only the GB10 canary manifest declares an agent-side endpoint (plan text corrected, see Deviations). for agents that check in; none do on either estate today.

## 5 — Sealed Ledger Service

**Old wording** (verbatim, `v2-one-liners-source.md` row 5): managed, cryptographically chained append-only record of agent actions with auditor read-only export and retention policies. (FIELD-L · CFO/audit committee)

**New wording:** A tamper-evident record of events appended by estate services: hash-chained, Ed25519-anchored; estate-level retention by segment rotation (mechanism; no estate rotates today - key custody undecided); an offline-re-verifiable export (a served export is unsigned); per-event ledger-signed when FIELD_LEDGER_SIGN_KEY is set; caller authorship Declared on the estates (Enforced in code when a caller keyring is set).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "managed" is not true (a self-run FastAPI service and CLI); "cryptographically chained" is a plain SHA-256 hash chain, not a Merkle tree; "append-only" is tamper-evident (edits and deletions are detected, a filesystem writer is not prevented); "record of agent actions" is a record of events its callers append, completeness is not claimed; "auditor read-only export" is an offline-re-verifiable bundle with no read-only auditor role (any holder can call /export); "retention policies" is estate-level retention by segment rotation, with no per-agent purge by design.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: hash-chained | CITE: services/sealed-ledger/tests/test_sealed_ledger.py::test_append_links_chain @ 3804d0b9 | KEY: prev_hash
- ENFORCED: tamper-evident: an edit on disk is detected | CITE: services/sealed-ledger/tests/test_sealed_ledger.py::test_adversarial_on_disk_mutation_detected @ 3804d0b9 | KEY: mutat
- ENFORCED: Ed25519-anchored | CITE: services/sealed-ledger/tests/test_sealed_ledger.py::test_signed_anchor_tamper_detected @ 3804d0b9 | KEY: signature
- ENFORCED: a full self-consistent rewrite passes verify but fails the anchors | CITE: services/sealed-ledger/tests/test_sealed_ledger.py::test_adversarial_full_history_rewrite_beats_verify_but_not_anchors @ 3804d0b9 | KEY: anchor
- ENFORCED: offline-re-verifiable export | CITE: services/sealed-ledger/tests/test_export_bundle.py::test_editing_one_exported_event_fails_naming_its_index @ 3804d0b9 | KEY: export
- ENFORCED: a served export is unsigned | CITE: services/sealed-ledger/tests/test_export_bundle.py::test_served_export_writes_signed_false @ 3804d0b9 | KEY: signed
- ENFORCED: retention by segment rotation (mechanism) | CITE: services/sealed-ledger/tests/test_ledger_rotation.py::test_rotate_twice_verify_ok_across_three_segments @ 3804d0b9 | KEY: rotat
- ENFORCED: archival of closed, verified segments | CITE: services/sealed-ledger/tests/test_ledger_retention.py::test_archival_keeps_live_verify_ok_and_sidecar_verifies_standalone @ 3804d0b9 | KEY: archiv
- ENFORCED: the estate retention check reports a manifest that asks for more | CITE: services/sealed-ledger/tests/test_ledger_retention.py::test_retention_check_estate_365_vs_manifest_2555_exit_3 @ 3804d0b9 | KEY: estate
- ENFORCED: per-event ledger-signed (when the signing key is set) | CITE: services/sealed-ledger/tests/test_event_signing_f2.py::test_key_loaded_every_append_is_signed_and_verifies @ 3804d0b9 | KEY: signature
- ENFORCED: caller authorship (when a caller keyring is set) | CITE: services/sealed-ledger/tests/test_caller_signing_f2b.py::test_signed_caller_append_stored_and_verifies @ 3804d0b9 | KEY: caller

**Declared words** (no test, no implementation, or only a mechanism): managed; append-only against a filesystem writer (WORM); a read-only auditor role; per-agent retention; completeness of the record of agent actions; anchor proof of Fly's head; that any estate rotates or signs per event today (not armed; key custody undecided).

Qualifier: hash-chained, Ed25519-anchored; estate-level retention by segment rotation (mechanism; no estate rotates today - key custody undecided). "No estate rotates today - key custody undecided" is an estate fact this repository cannot verify; it stays as the plan wrote it and is Declared.

## 6 — Incident Replay Agent

**Old wording** (verbatim, `v2-one-liners-source.md` row 6): reconstructs from the ledger who authorized an agent, what it did, and which manifest clause failed; outputs the RACI-ready post-mortem. (FIELD-L · CISO)

**New wording:** A deterministic (no LLM) post-mortem that, from ledger events, the registry, delegation grants and the manifest, lists the grantor recorded on a grant covering the failing action (grantor name recorded, not authenticated), a chronological timeline of what the ledger recorded, and the first failing FIELD clause id recorded in a ledger verdict, with R/A/C/I from registry, grant, manifest with labeled defaults.

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "Agent" overclaims (a deterministic query engine; the report path has no LLM); "reconstructs from the ledger" also reads the registry, grants and manifest, and keeps only the newest N events within a cap; "who authorized" names a covering grant's recorded grantor name, not an authenticated person; "which manifest clause failed" is the clause id recorded in a ledger verdict, not a manifest evaluation; "RACI-ready" is R/A/C/I with labeled defaults.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: what it did: a chronological timeline of ledger events | CITE: services/incident-replay/tests/test_incident_replay.py::test_replay_reconstructs_incident @ 3804d0b9 | KEY: timeline
- ENFORCED: a tampered ledger is flagged loudly | CITE: services/incident-replay/tests/test_incident_replay.py::test_adversarial_tampered_ledger_flagged_loudly @ 3804d0b9 | KEY: tamper
- ENFORCED: only the newest N events within a cap, and it says so | CITE: services/incident-replay/tests/test_replay_truncation.py::test_over_the_cap_keeps_the_newest_n_and_says_so @ 3804d0b9 | KEY: truncated
- ENFORCED: who authorized: a grant covering the failing action | CITE: services/incident-replay/tests/test_raci_from_data.py::test_covering_grant_beats_earlier_non_covering_grant @ 3804d0b9 | KEY: covering
- ENFORCED: which clause failed: the clause id recorded in a verdict (log-only labeled) | CITE: services/incident-replay/tests/test_raci_from_data.py::test_shadow_block_is_first_failure_labeled_log_only @ 3804d0b9 | KEY: shadow
- ENFORCED: R/A/C/I from registry, grant, manifest with labeled defaults | CITE: services/incident-replay/tests/test_raci_from_data.py::test_responsible_is_registry_owner_labeled @ 3804d0b9 | KEY: registry
- ENFORCED: deterministic (no LLM) post-mortem | CITE: services/incident-replay/tests/test_incident_replay.py::test_markdown_report_is_raci_ready @ 3804d0b9 | KEY: no LLM

**Declared words** (no test, no implementation, or only a mechanism): agent (no LLM, no autonomy); completeness of the trail for actions outside the perimeter; who authorized as an authenticated identity; which manifest clause as a manifest evaluation; executive owners from an org chart (a static letter map); the manifest as it stood in the window (it is read at replay time).

Qualifier: R/A/C/I from registry, grant, manifest with labeled defaults

## 7 — Compliance Crosswalk Engine

**Old wording** (verbatim, `v2-one-liners-source.md` row 7): Maps every FIELD manifest to OSFI E-23, EU AI Act, ISO 42001, and NIST AI RMF control requirements, and generates the evidence pack on demand.

**New wording:** Evaluates a FIELD manifest against 13 Spin State controls mapped to OSFI E-23, EU AI Act (Articles 12 and 14) and NIST AI RMF (16 of 52 entries cited, the rest pending-text), with ISO/IEC 42001 (pending text purchase) mapped but never cited; produces a named-signer evidence pack on demand (no pack without a signer; blocked by a stale-source flag until a named human clears it); Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "every FIELD manifest" and "control requirements" are 13 Spin State controls evaluated per manifest, three of them declaration-only, with 16 of 52 framework entries cited; "ISO 42001" is pending text purchase for all 13 entries; "evidence pack" is a named-signer document, nothing signs its bytes; "on demand" needs a named signer and is blocked by a stale flag. The audit's "Continuous" is not in the old text: what exists is content-change detection of the cited pages.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: evaluates a manifest: declared versus evidenced | CITE: services/compliance-crosswalk/tests/test_crosswalk.py::test_coverage_declared_only @ 3804d0b9 | KEY: declared
- ENFORCED: evidence changes the verdicts | CITE: services/compliance-crosswalk/tests/test_crosswalk.py::test_evidence_changes_verdicts @ 3804d0b9 | KEY: evidenced
- ENFORCED: a broken ledger chain fails the evidence | CITE: services/compliance-crosswalk/tests/test_crosswalk.py::test_broken_ledger_fails_evidence @ 3804d0b9 | KEY: broken
- ENFORCED: no ungrounded citations (all four frameworks cited or pending) | CITE: services/compliance-crosswalk/tests/test_crosswalk.py::test_adversarial_no_ungrounded_citations @ 3804d0b9 | KEY: ungrounded
- ENFORCED: ISO/IEC 42001 (pending text purchase) | CITE: services/compliance-crosswalk/tests/test_crosswalk.py::test_adversarial_no_ungrounded_citations @ 3804d0b9 | KEY: pending-purchase
- ENFORCED: NIST AI RMF (MANAGE 2.4 on the stop button control) | CITE: services/compliance-crosswalk/tests/test_crosswalk.py::test_kill_switch_control_carries_stop_button_citations @ 3804d0b9 | KEY: MANAGE 2.4
- ENFORCED: generates the evidence pack (named signer, disclaimer) | CITE: services/compliance-crosswalk/tests/test_evidence_pack.py::test_pack_markdown_contents @ 3804d0b9 | KEY: named-signer
- ENFORCED: no pack without a signer | CITE: services/compliance-crosswalk/tests/test_evidence_pack.py::test_signer_required_empty_and_whitespace @ 3804d0b9 | KEY: signer
- ENFORCED: a stale-source flag blocks the pack | CITE: services/compliance-crosswalk/tests/test_evidence_pack.py::test_stale_flags_block_generation_hard @ 3804d0b9 | KEY: StalePackError
- ENFORCED: on demand (POST /pack) | CITE: services/compliance-crosswalk/tests/test_pack_api.py::test_pack_happy_path_200_with_disclaimer_and_signer @ 3804d0b9 | KEY: signer
- ENFORCED: content-change detection of the cited sources | CITE: services/compliance-crosswalk/tests/test_regwatch.py::test_changed_bytes_flag_with_url_sha_prefixes_and_byte_diff @ 3804d0b9 | KEY: sha
- ENFORCED: a served scheduler runs the check (in process) | CITE: services/compliance-crosswalk/tests/test_regwatch.py::test_served_scheduler_runs_a_check_after_the_interval @ 3804d0b9 | KEY: scheduler

**Declared words** (no test, no implementation, or only a mechanism): every manifest field or control; full requirement coverage; mapping correctness and sufficiency; the pack is signed or tamper-evident; ISO text mapping; automatic detection of an OSFI change (its page answered 403 to the manual live fetch of 2026-09-13); the daily cadence on an estate; a flagged change is material (a named human decides).

Qualifiers: Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI). ISO/IEC 42001 (pending text purchase). Rider: the manual live fetch got EUR-Lex, NIST and both mirrors, and OSFI answered 403, so an OSFI page change is reported unreachable, not detected.

## 8 — Federation Broker

**Old wording** (verbatim, `v2-one-liners-source.md` row 8): trust gateway for agents crossing org boundaries; validates counterparty manifests, enforces data-scope borders, records inter-org contract semantics. (FIELD-F · CIO/GC)

**New wording:** A crossing-decision service for agents crossing org boundaries: it validates a counterparty's FIELD manifest (valid, non-isolated, names us as a peer, Ed25519-signed when the contract holds their key; an inbound crossing without a contract key is blocked), checks the requested scope and data class against a GC-registered contract record, and ledgers the ALLOW or BLOCK verdict with its direction (best-effort). It does not carry the traffic or inspect payloads.

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "trust gateway" is a decision service: it does not carry or gate the traffic, and an agent that crosses without asking is invisible to it; "data-scope borders" are exact-match lists of scope and data-class strings declared by the caller, with no payload inspection; "inter-org contract semantics" is a stored record (counterparty, allowed scopes and data classes, an optional reference and key), nothing about obligations or terms is parsed.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: an in-contract crossing is allowed and ledgered | CITE: services/federation-broker/tests/test_federation_broker.py::test_governed_crossing_allowed @ 3804d0b9 | KEY: ALLOW
- ENFORCED: validates counterparty manifests: an invalid manifest is blocked | CITE: services/federation-broker/tests/test_federation_broker.py::test_adversarial_invalid_manifest_blocked @ 3804d0b9 | KEY: I.manifest
- ENFORCED: a manifest broadened after signing is blocked | CITE: services/federation-broker/tests/test_federation_broker.py::test_adversarial_tampered_manifest_after_signing_blocked @ 3804d0b9 | KEY: signature
- ENFORCED: an isolated counterparty is blocked | CITE: services/federation-broker/tests/test_federation_broker.py::test_isolated_counterparty_blocked @ 3804d0b9 | KEY: F.isolated
- ENFORCED: data-scope border: a data class outside the contract is blocked | CITE: services/federation-broker/tests/test_federation_broker.py::test_out_of_contract_data_class_blocked @ 3804d0b9 | KEY: customer PII
- ENFORCED: data-scope border: a scope outside the contract is blocked | CITE: services/federation-broker/tests/test_federation_broker.py::test_out_of_contract_scope_blocked @ 3804d0b9 | KEY: not in contract
- ENFORCED: outbound crossings are decided and ledgered with their direction | CITE: services/federation-broker/tests/test_federation_outbound.py::test_outbound_in_contract_allowed_with_direction_in_context_and_ledger @ 3804d0b9 | KEY: direction

**Declared words** (no test, no implementation, or only a mechanism): trust gateway (traffic carrier); payload or data-content borders; contract semantics beyond a stored allowlist record; a contract signed by both GCs; replay protection; key rotation or revocation; the outbound manifest being the agent's real one; a ledger delivery guarantee (a ledger failure is swallowed and the verdict stands).

Qualifier: crossing-decision service

## 9 — Spend & Resource Governor

**Old wording** (verbatim, `v2-one-liners-source.md` row 9): real-time metering of every agent's token, compute, and action spend against manifest caps; throttles at thresholds, escalates to a human before the budget event. (FIELD-E · CFO/CTO)

**New wording:** On-report metering of each agent's tokens (gateway-metered when calls go through the gateway; self-reported otherwise) and cents and actions (self-reported, plus actions the sentinel meters at /check; the source label is not authenticated) against manifest caps, with integer arithmetic; it opens a human-review escalation at 80% of a cap before the cap is reached, reports BLOCK at the cap and THROTTLED (with retry_after_seconds) when a rolling per-action or token window is exhausted; the sentinel, not the governor, pauses the agent; compute has no observer (dropped, reason stated).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "real-time metering of every agent" is on-report (an agent that never reports is unmetered, and the governor intercepts nothing); "compute" has no observer and no field; "throttles at thresholds" is two mechanisms: the cap threshold escalates, and a rolling window reports THROTTLED, and neither stops anything inside the governor; "escalates to a human" opens a row in a review queue, nobody is notified.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: on-report metering of cents | CITE: services/spend-governor/tests/test_spend_governor.py::test_spend_within_limits_ok @ 3804d0b9 | KEY: spent_cents
- ENFORCED: against manifest caps | CITE: services/spend-governor/tests/test_spend_governor.py::test_cap_from_financial_manifest @ 3804d0b9 | KEY: limit_cents
- ENFORCED: escalates to a human before the cap | CITE: services/spend-governor/tests/test_spend_governor.py::test_threshold_escalates_before_cap @ 3804d0b9 | KEY: ESCALATE
- ENFORCED: reports BLOCK at the cap | CITE: services/spend-governor/tests/test_spend_governor.py::test_hard_cap_blocks @ 3804d0b9 | KEY: cap reached
- ENFORCED: throttle: a per-action window reports THROTTLED | CITE: services/spend-governor/tests/test_throttle.py::test_action_window_n_allowed_then_throttled_until_the_period_passes @ 3804d0b9 | KEY: THROTTLED
- ENFORCED: governor-parseable periods | CITE: services/spend-governor/tests/test_throttle.py::test_rate_period_grammar @ 3804d0b9 | KEY: parse_rate_period
- ENFORCED: gateway-metered tokens | CITE: services/force-gateway/tests/test_f1_enforce.py::test_allowed_call_is_forwarded_injected_and_metered_for_the_header_agent @ 3804d0b9 | KEY: usage
- ENFORCED: sentinel-metered actions (a source label, not an identity) | CITE: services/conformance-sentinel/tests/test_throttle_metering.py::test_one_allow_meters_exactly_one_and_self_stays_zero @ 3804d0b9 | KEY: metered

**Declared words** (no test, no implementation, or only a mechanism): real-time; every agent; compute; platform-metered; the truthfulness of self-reported spend; BLOCK stops the agent; `session` rate limits (the test proves a `session` entry is declared_unenforced and never locks anything out: `services/spend-governor/tests/test_throttle.py::test_session_entry_is_declared_unenforced_ledgered_and_never_locks_out`); a human is notified; source=sentinel authenticity (no adversarial test of the sentinel-metered path exists); an atomic throttle.

Qualifiers: throttle (per-action windows over self-reported action counts, plus sentinel-metered counts when a sentinel posts them (D1 options A and B are on main; the source label is unauthenticated); governor-parseable periods; `session` Declared). on-report metering (gateway-metered tokens, self-reported spend, sentinel-metered actions only as an unauthenticated label; no adversarial test of that path; compute has no observer (dropped, reason stated))

## 10 — FORCE Gateway

**Old wording** (verbatim, `v2-one-liners-source.md` row 10): An LLM-traffic proxy that injects FORCE runtime constraints on outbound model calls and dashboards hygiene telemetry. Governs what the AI says while FIELD governs what it is.

**New wording:** A Messages-API proxy that injects FORCE protocol blocks into the calls sent through it and exposes regex-heuristic hygiene telemetry rates plus per-dimension drift alerts as JSON (hygiene telemetry rates + sycophancy drift (mechanism; judge off on both estates today)), and, with FORCE_GATEWAY_ENFORCE=1 when the gateway is the mandatory egress, refuses calls from killed, revoked, unregistered, over-cap or throttled agents: org-wide when deployed as the LLM egress proxy (not deployed as such on either estate; platform judge traffic deliberately passthrough - excluded from hygiene telemetry).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "dashboards" has no UI (a JSON endpoint and a CLI); "Governs what the AI says" is injection, not obedience (the model obeying the FORCE block is Declared); the audit's "org-wide" holds only when the gateway is the mandatory egress. The gateway is not that on either estate by default (FORCE_GATEWAY_ENFORCE defaults to 0 in compose and the Fly entrypoint); the one exception by design is the GB10 canary-agent, whose compose network allows only the gateway as its LLM path (`integration/demo/docker-compose.gb10.yml:140-148`), and whether enforce is armed there is an estate .env fact this repository cannot show.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: an LLM-traffic proxy | CITE: services/force-gateway/tests/test_force_gateway.py::test_proxy_roundtrip_records_telemetry @ 3804d0b9 | KEY: telemetry
- ENFORCED: injects FORCE runtime constraints on outbound model calls | CITE: services/force-gateway/tests/test_force_gateway.py::test_inject_preserves_string_system @ 3804d0b9 | KEY: inject
- ENFORCED: hygiene telemetry rates (regex heuristic) | CITE: services/force-gateway/tests/test_d2_rates.py::test_mixed_responses_rate_half @ 3804d0b9 | KEY: rate
- ENFORCED: sycophancy drift (mechanism) | CITE: services/force-gateway/tests/test_d2_drift_dimensions.py::test_sycophancy_drifts_while_overall_holds_exactly_one_sycophancy_alert @ 3804d0b9 | KEY: sycophancy
- ENFORCED: platform judge traffic deliberately passthrough, excluded from hygiene telemetry | CITE: services/force-gateway/tests/test_d2_upstream_passthrough.py::test_secretless_passthrough_is_forwarded_untouched_counted_and_ledgered @ 3804d0b9 | KEY: passthrough
- ENFORCED: enforce mode refuses a killed agent with no upstream call | CITE: services/force-gateway/tests/test_f1_enforce.py::test_killed_agent_is_refused_403_e_kill_switch_with_no_upstream_call @ 3804d0b9 | KEY: kill_switch

**Declared words** (no test, no implementation, or only a mechanism): dashboards; governs what the AI says (the model obeys the FORCE block); the telemetry equals true FORCE compliance; the sycophancy drift signal on the estates (judge off on both); the estates routing judge calls through the gateway; FORCE_GATEWAY_ENFORCE live on an estate; streaming (stream: true is not intercepted).

Qualifiers: org-wide when deployed as the LLM egress proxy (not deployed as such on either estate; platform judge traffic deliberately passthrough - excluded from hygiene telemetry). hygiene telemetry rates + sycophancy drift (mechanism; judge off on both estates today). Exception by compose design: the GB10 canary-agent's only LLM path is the gateway.

KEYLESS: not live-verified - needs ANTHROPIC_API_KEY (the real upstream call and the real judge: every test uses a mock upstream and a mock judge).

## 11 — Agent Lifecycle Manager

**Old wording** (verbatim, `v2-one-liners-source.md` row 11): provisioning-to-decommission: authority expiry, re-attestation cadences, orphan detection for agents whose human owner left. (FIELD-I/D · CIO/CHRO)

**New wording:** provision → decommission, named re-attestation (name recorded, not authenticated): validate, register, cap, rate-limit and mint transitions, and revoke, kill and retire transitions, plus a sweep that reports tokens expiring within a horizon, re-attestation staleness against one configurable threshold, and agents whose registry owner is not on a supplied roster (escalate only; auto-kill only on an explicit flag).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "authority expiry" is detection and a report (token expiry itself is the delegation service's); "re-attestation cadences" is one global staleness threshold per sweep (default 90 days), with no per-agent cadence and no scheduling of attestations; "orphan detection for agents whose human owner left" is a registry owner string absent from a roster CSV, nothing detects that a person left.

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: provision | CITE: services/lifecycle-manager/tests/test_transitions.py::test_happy_path_provision_registers_caps_and_mints @ 3804d0b9 | KEY: provision
- ENFORCED: decommission | CITE: services/lifecycle-manager/tests/test_transitions.py::test_decommission_revokes_kills_retires_and_records @ 3804d0b9 | KEY: decommission
- ENFORCED: authority expiry: tokens lapsing inside a horizon are reported | CITE: services/lifecycle-manager/tests/test_lifecycle_manager.py::test_sweep_findings @ 3804d0b9 | KEY: expiring
- ENFORCED: orphan detection against a supplied roster | CITE: services/lifecycle-manager/tests/test_lifecycle_manager.py::test_sweep_findings @ 3804d0b9 | KEY: orphan
- ENFORCED: named re-attestation (name recorded) | CITE: services/lifecycle-manager/tests/test_transitions.py::test_attesting_moves_the_basis_and_names_the_attester @ 3804d0b9 | KEY: attest
- ENFORCED: auto-kill only on an explicit flag | CITE: services/lifecycle-manager/tests/test_lifecycle_manager.py::test_adversarial_auto_kill_requires_flag @ 3804d0b9 | KEY: auto_kill

**Declared words** (no test, no implementation, or only a mechanism): re-attestation cadences (one threshold only); the owner left (roster membership only); the sweep running on either estate (the roster is unset, so every scheduled tick is a recorded skip); attested_by is the human; the roster is current; authority expiry enforced here (report only).

Qualifier: provision → decommission, named re-attestation (name recorded, not authenticated)

## 12 — Executive Attestation Reporter

**Old wording** (verbatim, `v2-one-liners-source.md` row 12): board-level rollup: agents in production, conformance percentage, incidents and replays, expiring authorities; generates the quarterly AI-governance attestation the CEO signs. (all letters · CEO/board)

**New wording:** A rollup of agents in production, a sourced conformance percentage, block, escalation and kill counts and expiring authorities, counted over a UTC-quarter window: quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs unsigned drafts unless F4).

**Deployment status:** Declared (both estates run pre-v1.2 images).

**REWORD, and why:** "incidents and replays" has no metric (the pack counts verdicts, kill activations, drills, escalations, federation crossings and orphans; no replay is counted); "AI-governance attestation" is a count-and-source report, not a compliance assertion; "the CEO signs" is a named signer string (nothing binds it to the CEO or to any person or role).

**Enforced words** (each is a test at the pinned commit):

- ENFORCED: every number has a source | CITE: services/attestation-reporter/tests/test_attestation_reporter.py::test_every_number_has_a_source @ 3804d0b9 | KEY: source
- ENFORCED: agents in production (registry status active) | CITE: services/attestation-reporter/tests/test_attestation_reporter.py::test_pack_numbers_match_staged_state @ 3804d0b9 | KEY: production
- ENFORCED: conformance percentage (ALLOW over the window's verdicts) | CITE: services/attestation-reporter/tests/test_attestation_reporter.py::test_pack_numbers_match_staged_state @ 3804d0b9 | KEY: conformance
- ENFORCED: expiring authorities (within 30 days; revoked tokens excluded) | CITE: services/attestation-reporter/tests/test_attestation_reporter.py::test_pack_numbers_match_staged_state @ 3804d0b9 | KEY: expiring
- ENFORCED: a log-only estate cannot read 100% | CITE: services/attestation-reporter/tests/test_attestation_reporter.py::test_log_only_shadow_verdicts_lower_the_conformance_rate @ 3804d0b9 | KEY: shadow
- ENFORCED: quarterly (UTC-quarter window) | CITE: services/attestation-reporter/tests/test_c4_window_and_signature.py::test_parse_period_both_spellings_give_the_utc_quarter @ 3804d0b9 | KEY: quarter
- ENFORCED: signed by a named signer (CLI); verify exits 0 or 1 | CITE: services/attestation-reporter/tests/test_c4_window_and_signature.py::test_cli_render_signs_and_verify_exits_0_1_1 @ 3804d0b9 | KEY: signer
- ENFORCED: served pack signed with the estate key when configured (F4) | CITE: services/attestation-reporter/tests/test_f4_served_signing.py::test_served_pack_is_signed_by_the_estate_key_and_verifies_with_attest_verify @ 3804d0b9 | KEY: estate-key

**Declared words** (no test, no implementation, or only a mechanism): incidents; replays; AI-governance attestation as a compliance statement; the CEO signs (no role binding); a valid signature means the named person approved the pack; the pack covers everything the organisation runs; the estates' served packs being signed.

Qualifier: quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs unsigned drafts unless F4). F4 is on main: a served pack is signed with the estate key only when FIELD_ATTEST_SIGNER and FIELD_ATTEST_SIGN_KEY are set, and the repository's compose and Fly files forward them blank, so the estates' served packs are unsigned drafts until the estate .env sets them (an estate fact, Declared).

## Deviations from the plan's qualifier text

The plan (`tasks/todo.md`, E1) lists qualifiers that must survive verbatim. Every one is present verbatim except one, which the code contradicts:

1. **Kill endpoints.** The plan says `allowlisted, best-effort; no shipped manifest declares an agent-side endpoint`. `manifests/canary-gb10.yaml:49` declares `http://canary-agent:8090/halt` (the other manifests point back at the kill-switch or at an unresolvable `.invalid` host). The file says `allowlisted, best-effort; only the GB10 canary manifest declares an agent-side endpoint`. If the plan's text is wanted back, the manifest or this row must change first.

Four qualifiers are kept verbatim and carry an added note, because the repository cannot settle or partly contradicts an estate fact: `FIELD_DOA_ROSTER` "unset on both estates" (row 3), the ledger's "no estate rotates today - key custody undecided" (row 5), the gateway's "not deployed as such on either estate" (row 10, canary-agent exception by design), and "served packs unsigned drafts unless F4" (row 12, F4 is on main). Those are estate facts: they are Declared until redeploy and a coordinator or verifier card establishes them.
