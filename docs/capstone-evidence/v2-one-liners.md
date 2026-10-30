# v2 one-liners — old wording, new wording, Enforced / Declared (Phase E1)

**Every Enforced word is test/CI-proven; per-system estate status is Declared until the estates run the images these tests ran against and Phase G is armed (REQUIRE not armed on either estate; Stage 1 LOG-ONLY only, on the GB10).** The proof is in this repository at base commit `48acfa6`; "test/CI-proven" means a named test asserts it, not that an estate behaves that way. This change did not touch or re-check either estate.

The plan's own wording was "both estates run pre-v1.2 images"; this document does not repeat it as fact, because the service READMEs record later estate changes (for example FIELD_DOA_ROSTER set on both estates as of 2026-10-23) that this change could not verify. STATE.md carries the deploy log.

## Provenance of the "old" column

The old sentences are the 2026-09-12 product one-liners, quoted verbatim from [v2-one-liners-source.md](v2-one-liners-source.md), which recovered them from `AI-CTO/claude-files/Force-Field_Build_Prompt.md` (outside this repository; Don's capstone folder). Numbering is the audit's 1–12 (`tasks/audit-v2-12-systems-vs-production-build-2026-09-12.md` in the parent workspace, not in this repository), not the README table's order. The audit paraphrases some phrases that are not literally in the source ("API-key scans" for row 1, "Continuous" for row 7, "org-wide" for row 10); the old column here quotes the source text, and each paraphrase is named in that row's "Why reworded". Each old sentence is checked verbatim against the source file by `tools/e_gate.py`. The FIELD letter and buyer tags in the source (for example "(FIELD-E · CEO/CISO)") are kept only where they are part of the quoted text.

## How to read a row

- **Enforced** rows cite `path::test_name` and the commit that introduced that test; the E-gate confirms the file and function exist, the body has an assertion, the body names the "asserts" keyword, and the commit contains the test. A test that cites a qualifier (for example "when FIELD_DOA_ROSTER is set") proves the behavior under that condition only.
- **Declared** rows state the reason and name the README row that says the same. The E-gate fails if the README row's status disagrees in either direction.
- Run: `python tools/e_gate.py`. It reads nothing outside this repository.

| # | System | Estate status |
|---|---|---|
| 1 | Agent Registry | Declared |
| 2 | Conformance Sentinel | Declared |
| 3 | Delegation Authority Service | Declared |
| 4 | Kill-Switch Command Plane | Declared |
| 5 | Sealed Ledger Service | Declared |
| 6 | Incident Replay Agent | Declared |
| 7 | Compliance Crosswalk Engine | Declared |
| 8 | Federation Broker | Declared |
| 9 | Spend & Resource Governor | Declared |
| 10 | FORCE Gateway | Declared |
| 11 | Agent Lifecycle Manager | Declared |
| 12 | Executive Attestation Reporter | Declared |

## The twelve

### 1 — Agent Registry

**Old (verbatim):** "system of record where every AI agent is registered with identity, owner, and FIELD manifest; discovers unregistered shadow agents by scanning service accounts, API keys, and workflow platforms."

**One-liner:** System of record for each registered agent's identity, human owner and manifest reference; surfaces unregistered workflows and accounts from the artifacts you feed it and from API-key scans (file-based, heuristic).

**New:** The passport office: a system of record where each registered AI agent has an identity, a human owner and a manifest reference; it surfaces unregistered AI workflows and accounts from the artifacts you feed it (n8n workflow export, service-account inventory) and from API-key scans (file-based, heuristic).

**Why reworded:** "scanning ... workflow platforms" and "API keys" read as a live scan of the estate. The scanner reads only files handed to it, and the key scan is a labeled heuristic over an inventory file. The audit paraphrases this as "API-key scans"; that phrase is not in the source line (see Provenance).

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/agent-registry/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | one record per agent id; a human owner is required | `services/agent-registry/tests/test_registry_update_validation.py::test_create_with_an_empty_name_or_owner_is_422` | `5304779` | `owner` | One record per agent id |
| Enforced | a duplicate registration is refused | `services/agent-registry/tests/test_agent_registry.py::test_duplicate_registration_conflicts` | `8527e85` | `409` | One record per agent id |
| Enforced | an unregistered AI workflow in a fed artifact surfaces, and renaming it does not hide it | `services/agent-registry/tests/test_agent_registry.py::test_adversarial_renamed_workflow_still_flagged` | `8527e85` | `renamed` | AI workflows/accounts in scanned artifacts |
| Enforced | API-key scan (file-based, heuristic): a key with no owner is surfaced | `services/agent-registry/tests/test_d3_credential_scan.py::test_blank_owner_is_surfaced_as_unowned` | `4b8b352` | `unowned` | File-based credential-inventory |
| Enforced | API-key scan: a key named after a registered agent but owned by nobody registered is still surfaced | `services/agent-registry/tests/test_d3_credential_scan.py::test_adversarial_key_named_after_a_registered_agent_is_surfaced_by_owner` | `4b8b352` | `owner` | File-based credential-inventory |
| Enforced | attestation cannot be forged by a PATCH | `services/agent-registry/tests/test_attestation_and_migration.py::test_adversarial_patch_cannot_forge_attestation` | `017a10f` | `attested` | `attested_at` moves only |
| Declared | the registry knows about all agents in the org | discovery covers only the artifacts fed to it; an agent outside the n8n export, the account inventory, the key inventory and pasted text is invisible | — | — | The registry knows about *all* agents |
| Declared | `attested_by` is the human who attested | a recorded string, not an authenticated identity | — | — | `attested_by` is the human who attested |
| Declared | `owner` is a real, current human | reconciliation against an HR roster is lifecycle-manager's job and runs only when a roster file is configured | — | — | `owner` is a real, current human |

### 2 — Conformance Sentinel

**Old (verbatim):** "An agent that continuously audits deployed agents against their FIELD manifests and blocks non-conforming actions at the policy-enforcement point — scope breaches, expired authority, missing ledger writes — before they execute."

**One-liner:** Checks each action an agent asks about against its manifest, token and the registry and blocks breaches before they run, at the agent's action boundary (SDK/@governed; cooperative perimeter), + intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate).

**New:** A decision service: each action an agent asks about is checked against its FIELD manifest, its delegation token and the registry, and a scope breach, expired or revoked authority, a killed agent or an unreachable ledger is blocked before the action runs — at the agent's action boundary (SDK/@governed; cooperative perimeter), + intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate). A served estate defaults to log-only (would-blocks are shadow-ledgered, not enforced).

**Why reworded:** "An agent that continuously audits" is wrong twice: it is a request/response service that judges what it is asked about (no background audit), and an agent that never calls it is invisible to it. "missing ledger writes" is narrowed to the ledger being unreachable before an ALLOW.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/conformance-sentinel/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | a killed agent fails its next check | `services/conformance-sentinel/tests/test_sentinel.py::test_killed_agent_blocks_instantly` | `3b42cfc` | `killed` | Killed agents fail their next check |
| Enforced | an out-of-scope action is blocked (D.scope) | `services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_out_of_scope_blocks` | `3b42cfc` | `D.scope` | Out-of-scope actions blocked |
| Enforced | a revoked token is blocked with the exact clause | `services/conformance-sentinel/tests/test_sentinel.py::test_revoked_token_blocks_with_clause` | `3b42cfc` | `revoked` | Expired/revoked tokens blocked |
| Enforced | an invalid manifest removes all authority | `services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_invalid_manifest_blocks` | `3b42cfc` | `manifest` | Invalid/missing manifest |
| Enforced | no ledger, no actions | `services/conformance-sentinel/tests/test_sentinel.py::test_adversarial_ledger_down_blocks_everything` | `3b42cfc` | `ledger` | No ledger |
| Enforced | in enforce mode an ALLOW whose ledger record failed is BLOCK L.unreachable | `services/conformance-sentinel/tests/test_f2_fail_closed.py::test_enforce_failed_allow_append_is_block_l_unreachable_and_never_metered` | `3f82811` | `L.unreachable` | In enforce mode, an ALLOW whose ledger record failed |
| Enforced | served estate observes before it enforces (log-only default) | `services/conformance-sentinel/tests/test_sentinel.py::test_served_estate_defaults_to_log_only` | `3be918f` | `log_only` | Safe-by-default |
| Enforced | intercepted at the LLM egress: a killed agent is refused with no upstream call (FORCE_GATEWAY_ENFORCE=1 and the gateway as mandatory egress) | `services/force-gateway/tests/test_f1_enforce.py::test_killed_agent_is_refused_403_e_kill_switch_with_no_upstream_call` | `5ae3600` | `403` | @force-gateway Interception at the LLM egress |
| Declared | agents route their actions through /check at all | the sentinel governs what it is asked about; an agent that bypasses it is invisible to it | — | — | Agents route their actions through `/check` at all |
| Declared | interception at the LLM egress is live on the estates | needs FORCE_GATEWAY_ENFORCE=1 and the gateway as the only LLM path; the estates run enforce=0 at this commit (gateway README arming step A10) | — | — | @force-gateway `FORCE_GATEWAY_ENFORCE=1` is live on the estates |
| Declared | semantic understanding quality of the judge | mock tests prove control flow, not judgment; judge is OFF by default | — | — | Semantic understanding quality |
| Declared | OS-level manifest immutability | process behavior is tested; the read-only mount is configuration awaiting a deploy | — | — | OS-level manifest immutability |

### 3 — Delegation Authority Service

**Old (verbatim):** "scoped, expiring, revocable authority tokens chained to the human delegation-of-authority matrix; every agent action traces to a named human grant. OAuth for agents."

**One-liner:** OAuth-style scoped, expiring, revocable tokens bound to a registered active agent; mint checked against a DOA roster when FIELD_DOA_ROSTER is set; grantor name recorded, not authenticated.

**New:** OAuth-style scoped, expiring, revocable tokens bound to a registered, active agent. When FIELD_DOA_ROSTER is set, a mint is refused for an off-roster grantor, scope or lifetime (the delegation-of-authority roster is a YAML file, not a live matrix); grantor name recorded, not authenticated.

**Why reworded:** "OAuth for agents" becomes "OAuth-style": there is no OAuth flow. "chained to the human matrix" holds only with a roster file. "every agent action traces to a named human grant" is removed: tracing needs the agent to present a token, and the grantor is a string nobody authenticates. FIELD_DOA_ROSTER state: the committed compose/Fly config leaves it unset; the service README's table and `tools/topology_lint_allowlist.yaml` record a presence-only check on 2026-10-23 that found it set (the README's own later bullet said unset, now reconciled to that). This change did not re-verify the estates, so the roster gate on an estate is Declared.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/delegation-authority/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | a token binds to a registered agent | `services/delegation-authority/tests/test_delegation_authority.py::test_mint_refused_for_unregistered_agent` | `84c9c70` | `404` | Tokens bind to a registered |
| Enforced | a killed agent cannot mint authority | `services/delegation-authority/tests/test_delegation_authority.py::test_mint_refused_for_killed_agent` | `84c9c70` | `409` | Tokens bind to a registered |
| Enforced | expired tokens fail introspection | `services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_expired_token_fails_introspection` | `84c9c70` | `expire` | Expired tokens fail introspection |
| Enforced | revoked tokens fail introspection | `services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_revoked_token_fails_introspection` | `84c9c70` | `revoke` | Revoked tokens fail introspection |
| Enforced | every mint is a ledger event before it takes effect (ledger down: no token) | `services/delegation-authority/tests/test_delegation_authority.py::test_adversarial_ledger_down_mint_fails_closed` | `84c9c70` | `ledger` | Every mint/revoke is a ledger event |
| Enforced | when FIELD_DOA_ROSTER is set, an off-roster grantor is refused (403 D.grantor) | `services/delegation-authority/tests/test_doa_roster.py::test_grantor_off_roster_is_403_d_grantor` | `9e5b642` | `D.grantor` | Mint refuses off-roster grantors |
| Enforced | when FIELD_DOA_ROSTER is set, a scope beyond the grantor's allowed scope is refused | `services/delegation-authority/tests/test_doa_roster.py::test_scope_beyond_grantor_allowed_scope_is_403_d_grantor` | `9e5b642` | `scope` | Mint refuses off-roster grantors |
| Declared | the caller is the named grantor | `granted_by` is a string checked for membership in a roster list; nothing authenticates the person | — | — | The caller **is** the named grantor |
| Declared | the DOA roster gate applies on an estate | set at runtime per a 2026-10-23 presence-only check recorded in the README and the topology allowlist; committed config leaves it unset; roster contents and arming (step A3) not verified here | — | — | — |
| Declared | agents actually present tokens when acting | that check is the sentinel's, and only for actions the agent routes through it | — | — | Agents actually *present* tokens when acting |

### 4 — Kill-Switch Command Plane

**Old (verbatim):** "resolvable kill endpoints and heartbeats for every registered agent; one-command domain shutdown and drill mode. (FIELD-E · CEO/CISO)"

**One-liner:** One-command kill, domain kill and drill mode; kill endpoints allowlisted, best-effort (one shipped manifest declares an agent-side endpoint); heartbeats for agents that check in (none do on either estate today).

**New:** One command flips an agent to killed in the registry (act-first: it succeeds with the ledger down), one command kills a domain, and drill mode kills, verifies and restores. Kill endpoints are allowlisted, best-effort calls; one shipped manifest (canary-gb10) declares an agent-side endpoint and both estates ledger endpoint_skipped until the allowlist is set. Heartbeats for agents that check in; none do on either estate today.

**Why reworded:** "resolvable kill endpoints ... for every registered agent" and "heartbeats for every registered agent" are removed: the endpoint call is opt-in per host allowlist, and a heartbeat exists only for an agent that POSTs check-ins. A killed process is not stopped by this service (Declared). The plan text says no shipped manifest declares an agent-side endpoint; the kill-switch README records one (canary-gb10 -> canary-agent, profile x3), so that sentence is corrected here, not repeated.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/kill-switch/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | one command kills; registry status flips and is ledgered | `services/kill-switch/tests/test_kill_switch.py::test_kill_agent_flips_registry_and_logs` | `557c7d9` | `killed` | One command kills |
| Enforced | a kill succeeds with the ledger down | `services/kill-switch/tests/test_kill_switch.py::test_kill_survives_ledger_outage` | `557c7d9` | `ledger` | Kill succeeds even during a ledger outage |
| Enforced | a domain kill kills only that domain | `services/kill-switch/tests/test_kill_switch.py::test_kill_domain_kills_only_that_domain` | `557c7d9` | `domain` | A domain kill survives one broken agent |
| Enforced | a drill kills, verifies and restores prior status | `services/kill-switch/tests/test_kill_switch.py::test_drill_kills_verifies_and_restores` | `557c7d9` | `restore` | Drill restores prior status |
| Enforced | a drill that could not restore is a 500, never a 2xx | `services/kill-switch/tests/test_c19_kill_switch.py::test_a_drill_that_could_not_restore_is_500_with_the_report` | `24453a2` | `500` | Drill restores prior status |
| Enforced | kill endpoints are allowlisted: a metadata-IP endpoint is skipped | `services/kill-switch/tests/test_endpoint_and_liveness.py::test_adversarial_metadata_endpoint_skipped_with_allowlist_unset` | `f195168` | `skipped` | The endpoint call cannot be steered off the allowlist |
| Enforced | unknown agents are told to halt | `services/kill-switch/tests/test_kill_switch.py::test_adversarial_unknown_agent_heartbeat_says_stop` | `557c7d9` | `stop` | Unknown agents are told to halt |
| Enforced | heartbeats (for agents that check in): server-side liveness on a frozen clock | `services/kill-switch/tests/test_endpoint_and_liveness.py::test_liveness_stale_window_on_a_frozen_clock` | `f195168` | `stale` | Heartbeats: server-side liveness |
| Declared | a killed agent's in-flight process stops | no process supervisor: the agent stops at its next check or heartbeat; the one exception is the canary's own loop, which proves the signal path, not that a business agent complies | — | — | A killed agent's *in-flight* process stops |
| Declared | operator authorization on guarded writes | Declared everywhere it is not armed: FIELD_OPERATOR_REQUIRE is not armed on any estate (Phase G) | — | — | Operator is authorized |

### 5 — Sealed Ledger Service

**Old (verbatim):** "managed, cryptographically chained append-only record of agent actions with auditor read-only export and retention policies. (FIELD-L · CFO/audit committee)"

**One-liner:** Hash-chained, Ed25519-anchored append-only record with offline-verifiable export; estate-level retention by segment rotation (mechanism; no estate rotates today, key custody undecided); per-event ledger-signed when the key is set, caller authorship Declared.

**New:** A hash-chained, Ed25519-anchored, append-only event record with offline-verifiable auditor export (signed only via the CLI; the served export is unsigned) and estate-level retention by segment rotation (mechanism; no estate rotates today — key custody undecided). Per-event ledger-signed when FIELD_LEDGER_SIGN_KEY is loaded; caller authorship Declared (verified only where a caller keyring is configured; not on Fly).

**Why reworded:** "managed" is removed (a file on a volume, one writer). "append-only" is a convention a filesystem writer defeats, so rewrites are detectable (anchors), not impossible. "retention policies" is estate-level only: there is no per-agent purge. The rotation statement (no estate rotates today) is the plan's and STATE.md's, not re-checked against a live estate by this change.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/sealed-ledger/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | every event is hash-linked to its predecessor | `services/sealed-ledger/tests/test_sealed_ledger.py::test_append_links_chain` | `04cf52f` | `link` | Every event is hash-linked |
| Enforced | an on-disk mutation of a mid-chain record is detected | `services/sealed-ledger/tests/test_sealed_ledger.py::test_adversarial_on_disk_mutation_detected` | `04cf52f` | `verify` | A naive on-disk mutation |
| Enforced | a deleted record is detected | `services/sealed-ledger/tests/test_sealed_ledger.py::test_adversarial_deleted_line_detected` | `04cf52f` | `verify` | A naive on-disk mutation |
| Enforced | a self-consistent full rewrite passes plain verify but fails the Ed25519-anchored check | `services/sealed-ledger/tests/test_sealed_ledger.py::test_adversarial_full_history_rewrite_beats_verify_but_not_anchors` | `2e001e0` | `anchor` | Full-history rewrites are detectable against anchors |
| Enforced | a signed anchor is tamper-evident | `services/sealed-ledger/tests/test_sealed_ledger.py::test_signed_anchor_tamper_detected` | `2e001e0` | `signed` | Full-history rewrites are detectable against anchors |
| Enforced | retention by segment rotation keeps one chain across segments (mechanism) | `services/sealed-ledger/tests/test_ledger_rotation.py::test_rotate_twice_verify_ok_across_three_segments` | `700301d` | `rotate` | A rotated ledger is still one chain |
| Declared | nobody can rewrite history undetectably | plain verify is blind to a self-consistent full rewrite; detection needs an off-box anchor, a deployment responsibility | — | — | Nobody can rewrite history *undetectably* |
| Declared | nobody can rewrite history at all | filesystem write access defeats append-only-ness; WORM storage is deployment responsibility | — | — | Nobody can rewrite history *at all* |
| Declared | caller authorship on Fly | a single container: every process can read every key, so a per-service key proves nothing there; not deployed on Fly | — | — | Caller authorship on Fly |
| Declared | retention periods in manifests are enforced per agent | not possible by design: retention is estate-level, one shared chain; the check only reports | — | — | Retention periods in manifests are enforced per agent |

### 6 — Incident Replay Agent

**Old (verbatim):** "reconstructs from the ledger who authorized an agent, what it did, and which manifest clause failed; outputs the RACI-ready post-mortem. (FIELD-L · CISO)"

**One-liner:** Reconstructs who authorized an agent, what it did and which clause failed from ledger, registry, delegation and manifest after verifying the chain; RACI R/A/C/I from registry, grant and manifest with labeled defaults.

**New:** Deterministic reconstruction from the ledger, registry, delegation tokens and manifest of who authorized an agent, what it did and which clause failed first, after the ledger chain is verified; the post-mortem's RACI R/A/C/I come from registry, grant and manifest with labeled defaults.

**Why reworded:** "RACI-ready" implied a finished accountability assignment; the roles are derived from data with labeled defaults when a manifest or grant is missing. "Agent" is dropped: there is no LLM in the report path. Completeness of the trail is the sentinel's job and is Declared here.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/incident-replay/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | a tampered ledger cannot produce a clean report | `services/incident-replay/tests/test_incident_replay.py::test_adversarial_tampered_ledger_flagged_loudly` | `a88efb3` | `FAILED` | Tampered ledgers cannot produce a clean report |
| Enforced | a busy ledger is reported INTEGRITY NOT VERIFIED, never CHAIN BROKEN, never OK | `services/incident-replay/tests/test_raci_from_data.py::test_busy_ledger_is_unverified_never_a_broken_chain_and_never_ok` | `e96dc89` | `busy` | A busy ledger |
| Enforced | RACI Responsible = the registry owner, labeled | `services/incident-replay/tests/test_raci_from_data.py::test_responsible_is_registry_owner_labeled` | `e96dc89` | `owner` | RACI Responsible = registry owner |
| Enforced | RACI Accountable = the grantor of the earliest covering grant in force at the failure | `services/incident-replay/tests/test_raci_from_data.py::test_covering_grant_beats_earlier_non_covering_grant` | `e96dc89` | `grant` | RACI Accountable = the grantor |
| Enforced | RACI labeled defaults when the manifest does not resolve; no crash | `services/incident-replay/tests/test_raci_from_data.py::test_unresolvable_manifest_defaults_labeled_no_crash` | `e96dc89` | `default` | No / missing / unparseable |
| Declared | the trail is complete (nothing acted without logging) | completeness is the sentinel's fail-closed job; replay reports what the ledger holds | — | — | The trail is *complete* |

### 7 — Compliance Crosswalk Engine

**Old (verbatim):** "Maps every FIELD manifest to OSFI E-23, EU AI Act, ISO 42001, and NIST AI RMF control requirements, and generates the evidence pack on demand."

**One-liner:** Maps platform controls to cited clauses of OSFI E-23, EU AI Act, ISO/IEC 42001 (pending text purchase) and NIST AI RMF; evidence pack on demand with a named signer; Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI).

**New:** Maps the platform's controls to cited clauses of OSFI E-23, the EU AI Act, ISO/IEC 42001 (pending text purchase) and NIST AI RMF, and generates an evidence pack on demand from real artifacts, with a named signer and a hard stop while the corpus is flagged stale. Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI). Evidence, not a compliance or certification claim.

**Why reworded:** "every FIELD manifest" is wrong: it maps controls, and the mapping's correctness is for expert review (Declared). "Continuous" is content-change detection on a schedule over cited sources, not monitoring of the law. "ISO 42001" gains "(pending text purchase)". An evidence pack is evidence, never a statement that anyone complies or is certified.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/compliance-crosswalk/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | no pack ships without a named signer | `services/compliance-crosswalk/tests/test_evidence_pack.py::test_signer_required_empty_and_whitespace` | `806d8c0` | `signer` | No pack ships without a named signer |
| Enforced | a stale corpus blocks packs until a named re-review (no override) | `services/compliance-crosswalk/tests/test_evidence_pack.py::test_stale_flags_block_generation_hard` | `806d8c0` | `stale` | Stale corpus blocks packs |
| Enforced | the pack never says 'compliant' outside its disclaimer | `services/compliance-crosswalk/tests/test_evidence_pack.py::test_word_discipline_complian_only_in_disclaimer` | `806d8c0` | `complian` | Every pack claim carries a three-part citation |
| Enforced | content-change detection: stale flags can be set over HTTP, never cleared | `services/compliance-crosswalk/tests/test_regwatch_api.py::test_no_http_route_can_clear_staleness` | `4b8b352` | `clear` | Stale flags can be SET over authenticated HTTP |
| Enforced | regwatch checks never fetch in parallel | `services/compliance-crosswalk/tests/test_regwatch.py::test_single_flight_a_second_check_fetches_nothing_until_the_first_returns` | `4b8b352` | `single` | Regwatch checks never fetch in parallel |
| Enforced | the interval scheduler runs a check after the interval | `services/compliance-crosswalk/tests/test_regwatch.py::test_served_scheduler_runs_a_check_after_the_interval` | `4b8b352` | `interval` | The interval scheduler fires |
| Declared | a pack is cryptographically signed, or the signer is who they say | the signer is a recorded name: nothing verifies it and nothing signs the bytes | — | — | A pack is cryptographically signed |
| Declared | the mapping table is correct against each framework | correctness is what expert review must establish | — | — | The mapping table is *correct* |
| Declared | controls are sufficient for any framework | coverage of our controls is not compliance with a regulation | — | — | Controls are *sufficient* |
| Declared | the real regulator hosts answer from CI / GB10 / Fly | depends on network reachability outside the repo; the live read was proven manually only (CROSSWALK_LIVE_FETCH=1) | — | — | The real hosts answer httpx |
| Declared | the daily cadence actually ran on the estate | proven only by GET /staleness last_check with trigger scheduler on that estate | — | — | The daily cadence actually ran on the estate |

### 8 — Federation Broker

**Old (verbatim):** "trust gateway for agents crossing org boundaries; validates counterparty manifests, enforces data-scope borders, records inter-org contract semantics. (FIELD-F · CIO/GC)"

**One-liner:** Crossing-decision service: validates counterparty manifests and checks contract scope and data-class allowlists on the request envelope; inbound needs a keyed, signed contract; it decides and does not carry the traffic.

**New:** A crossing-decision service: it answers allow or block for an agent crossing an org boundary by validating the counterparty manifest, checking the contract's scope and data-class allowlists on the request envelope, and ledgering each crossing with its direction. An inbound crossing needs a contract key and a valid Ed25519 signature. It decides; it does not carry the traffic.

**Why reworded:** "trust gateway" implies the broker is in the data path; it is advisory (an agent that crosses without asking is invisible to it). "enforces data-scope borders" is narrowed to the request envelope; payload content is not inspected. "records inter-org contract semantics" is narrowed to a stored contract reference: it does not verify that both parties signed.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/federation-broker/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | an invalid counterparty manifest never crosses | `services/federation-broker/tests/test_federation_broker.py::test_adversarial_invalid_manifest_blocked` | `4ead650` | `manifest` | Invalid counterparty manifests never cross |
| Enforced | an isolated counterparty never crosses | `services/federation-broker/tests/test_federation_broker.py::test_isolated_counterparty_blocked` | `4ead650` | `isolated` | Isolated counterparties never cross |
| Enforced | no contract, or an out-of-contract scope, blocks | `services/federation-broker/tests/test_federation_broker.py::test_out_of_contract_scope_blocked` | `4ead650` | `scope` | No contract / out-of-contract scope |
| Enforced | an out-of-contract data class blocks (envelope only) | `services/federation-broker/tests/test_federation_broker.py::test_out_of_contract_data_class_blocked` | `4ead650` | `data` | No contract / out-of-contract scope |
| Enforced | a tampered signed manifest never crosses inbound | `services/federation-broker/tests/test_federation_broker.py::test_adversarial_tampered_manifest_after_signing_blocked` | `ab55dd1` | `tamper` | Keyed contracts: unsigned or tampered |
| Enforced | a keyless contract blocks an inbound crossing | `services/federation-broker/tests/test_federation_broker.py::test_keyless_contract_blocks_an_inbound_crossing` | `aa73df5` | `key` | The manifest is *their real one* |
| Declared | a signed manifest is fresh and the presenter is its owner | no replay protection: a captured signed manifest verifies again, and the ALLOW is advisory | — | — | A signed manifest is fresh |
| Declared | the contract was actually signed by both GCs | `contract_ref` points at the instrument; the broker records it and verifies nothing | — | — | The contract was actually signed by both GCs |
| Declared | traffic content stays inside the declared data class | the broker gates the request envelope, not a payload inspection | — | — | Traffic *content* stays inside |
| Declared | outbound: an agent asks before it crosses | cooperative: an agent that crosses without asking is invisible to the broker | — | — | Outbound: an agent asks before it crosses |

### 9 — Spend & Resource Governor

**Old (verbatim):** "real-time metering of every agent's token, compute, and action spend against manifest caps; throttles at thresholds, escalates to a human before the budget event. (FIELD-E · CFO/CTO)"

**One-liner:** Platform-metered actions and tokens against manifest caps; throttle (per-action windows over action counts; `session` Declared); escalates to a human before the cap; compute has no observer (dropped, reason stated).

**New:** Platform-metered actions (at the sentinel's /check) and tokens (at the gateway egress) against manifest caps; self-reported spend is the cooperative path. Throttle (per-action windows over self-reported or sentinel-metered action counts; governor-parseable periods; `session` Declared); an escalation to a human opens before the cap is reached. Compute has no observer (dropped, reason stated: the platform never executes agent code).

**Why reworded:** "every agent" is narrowed to agents that pass through the sentinel or the gateway; the rest is self-reported and Declared. "compute" is dropped: a compute figure could only be a self-report, exactly what the v1.2 reword removes (F3). "real-time" is removed. Metering at the egress needs the gateway as the mandatory egress, which is not the case on either estate.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/spend-governor/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | an escalation opens before the cap is reached | `services/spend-governor/tests/test_spend_governor.py::test_threshold_escalates_before_cap` | `0769024` | `escalat` | Threshold escalation fires **before** the cap |
| Enforced | at or over the cap the status is BLOCK | `services/spend-governor/tests/test_spend_governor.py::test_hard_cap_blocks` | `0769024` | `BLOCK` | At/over cap |
| Enforced | integer arithmetic: no float drift at the boundary | `services/spend-governor/tests/test_spend_governor.py::test_adversarial_integer_threshold_no_float_drift` | `0769024` | `float` | Integer arithmetic |
| Enforced | spend with no configured cap is refused | `services/spend-governor/tests/test_spend_governor.py::test_spend_without_cap_refused` | `0769024` | `cap` | Spend without a configured cap is refused |
| Enforced | throttle: N actions allowed, N+1 THROTTLED, clear when the period passes | `services/spend-governor/tests/test_throttle.py::test_action_window_n_allowed_then_throttled_until_the_period_passes` | `4b8b352` | `THROTTLED` | Status is THROTTLED after N counted actions |
| Enforced | `session` rate limits are Declared-unenforced, ledgered, never lock out | `services/spend-governor/tests/test_throttle.py::test_session_entry_is_declared_unenforced_ledgered_and_never_locks_out` | `4b8b352` | `declared_unenforced` | — |
| Enforced | platform-metered actions: one ALLOW at the sentinel is metered exactly once | `services/conformance-sentinel/tests/test_throttle_metering.py::test_one_allow_meters_exactly_one_and_self_stays_zero` | `4b8b352` | `metered` | Spend is platform-metered |
| Enforced | platform-metered tokens at the gateway egress for the header's agent | `services/force-gateway/tests/test_f1_enforce.py::test_allowed_call_is_forwarded_injected_and_metered_for_the_header_agent` | `5ae3600` | `usage` | Spend is platform-metered |
| Declared | self-reported /spend is truthful | the cooperative path for agents outside both the sentinel and the gateway; compute (CPU/GPU seconds) has no observer and is dropped | — | — | Self-reported `/spend` is truthful |
| Declared | BLOCK actually stops the agent | enforcement is the sentinel's /check; this service only reports state | — | — | BLOCK actually stops the agent |
| Declared | `session` rate limits are enforced | stored as declared_unenforced; only the Claude Code Enforcement Gate counts a session | — | — | `session` rate limits are enforced |

### 10 — FORCE Gateway

**Old (verbatim):** "An LLM-traffic proxy that injects FORCE runtime constraints on outbound model calls and dashboards hygiene telemetry. Governs what the AI says while FIELD governs what it is."

**One-liner:** LLM-traffic proxy that injects the FORCE block and records hygiene telemetry (counters, not content); org-wide when deployed as the LLM egress proxy (not deployed as such on either estate); sycophancy drift (mechanism; judge off on both estates today).

**New:** An LLM-traffic proxy that injects the FORCE block into proxied model calls and records hygiene telemetry (counters and scores, not content). Org-wide when deployed as the LLM egress proxy (not deployed as such on either estate; platform judge traffic deliberately passthrough — excluded from hygiene telemetry). Hygiene telemetry rates + sycophancy drift (mechanism; judge off on both estates today).

**Why reworded:** "Governs what the AI says" is removed: injection is not obedience, and telemetry measures surface markers, so the model obeying the FORCE block is Declared. "dashboards" is narrowed to a telemetry endpoint. "org-wide" holds only when the gateway is the mandatory egress, which no estate has.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/force-gateway/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | every proxied call carries the preset's FORCE block | `services/force-gateway/tests/test_force_gateway.py::test_proxy_roundtrip_records_telemetry` | `b6f3a7d` | `FORCE` | Every proxied call carries the preset's FORCE block |
| Enforced | the caller's own system prompt survives injection | `services/force-gateway/tests/test_force_gateway.py::test_inject_preserves_string_system` | `b6f3a7d` | `system` | The caller's own system prompt survives injection |
| Enforced | flattery in a response is flagged by the deterministic telemetry | `services/force-gateway/tests/test_force_gateway.py::test_adversarial_flattery_is_flagged` | `b6f3a7d` | `flatter` | Telemetry figures are deterministic |
| Enforced | the gateway fails open: an instrumentation fault never blocks traffic | `services/force-gateway/tests/test_gateway_delta.py::test_instrumentation_fault_bypasses_without_failing_traffic` | `a92bbe4` | `bypass` | The Gateway fails OPEN |
| Enforced | drift alerts fire only on two consecutive out-of-band windows (mechanism) | `services/force-gateway/tests/test_gateway_delta.py::test_drift_alert_fires_on_two_consecutive_bad_windows_only_once` | `a92bbe4` | `consecutive` | Drift alerts fire only on two consecutive |
| Enforced | a telemetry-store fault never fails traffic | `services/force-gateway/tests/test_d2_store.py::test_corrupt_store_serves_200_and_bypasses_visibly` | `4b8b352` | `200` | A telemetry-store fault never fails traffic |
| Declared | the model obeys the FORCE block | injection is not compliance; telemetry measures surface markers, it cannot force behavior | — | — | The model *obeys* the FORCE block |
| Declared | agents route their LLM calls through the gateway | cooperative perimeter, same caveat as the sentinel | — | — | Agents route their LLM calls through the gateway |
| Declared | a sycophancy drift signal exists on the estates | the hygiene judge is OFF on both estates; no judgments, no series | — | — | A sycophancy drift signal exists on the estates |
| Declared | the estates route platform judge calls through the gateway | needs FORCE_GATEWAY_URL in the estate config and a deploy; the judges are off, so there is no such traffic today | — | — | The estates route platform judge calls |

### 11 — Agent Lifecycle Manager

**Old (verbatim):** "provisioning-to-decommission: authority expiry, re-attestation cadences, orphan detection for agents whose human owner left. (FIELD-I/D · CIO/CHRO)"

**One-liner:** Provision to decommission with named re-attestation (name recorded, not authenticated); expiry and orphan sweep against an owner roster file (unset on both estates).

**New:** Provision → decommission, named re-attestation (name recorded, not authenticated). A sweep reports expiring or stale authority, stale re-attestation and orphans against an owner roster file; auto-kill needs an explicit flag. The sweep is only as current as the roster, which is unset on both estates until arming step A1.

**Why reworded:** "orphan detection for agents whose human owner left" depends on a roster CSV an HR system must export; nothing here knows who left. "re-attestation cadences" reports staleness; a human must still attest, and the attester's name is not authenticated. Scheduled sweeps record a skip until the roster exists.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/lifecycle-manager/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | the provisioned spend cap equals the manifest's cents (29 cents for 0.29, not 28) | `services/lifecycle-manager/tests/test_transitions.py::test_provision_cents_use_round_not_truncation` | `017a10f` | `29` | The provisioned cap equals the manifest's cents |
| Enforced | a partial provision is reported as partial | `services/lifecycle-manager/tests/test_transitions.py::test_provision_reports_a_mid_sequence_failure_step_by_step` | `017a10f` | `step` | A partial provision is reported as partial |
| Enforced | decommission revokes, kills, retires and records | `services/lifecycle-manager/tests/test_transitions.py::test_decommission_revokes_kills_retires_and_records` | `017a10f` | `retire` | A decommission survives a revoke failure |
| Enforced | a decommissioned agent cannot be killed or revived again | `services/lifecycle-manager/tests/test_transitions.py::test_decommissioned_agent_cannot_be_killed_or_revived` | `017a10f` | `revive` | A retire cannot be undone |
| Enforced | auto-kill never happens without the explicit flag | `services/lifecycle-manager/tests/test_lifecycle_manager.py::test_adversarial_auto_kill_requires_flag` | `7ce20b5` | `flag` | Auto-kill NEVER happens without the explicit flag |
| Enforced | sweeps are idempotent: no duplicate kills on re-run | `services/lifecycle-manager/tests/test_lifecycle_manager.py::test_sweep_idempotent_no_duplicate_kills` | `7ce20b5` | `kill` | Sweeps are idempotent |
| Enforced | stale re-attestation is detected | `services/lifecycle-manager/tests/test_lifecycle_manager.py::test_reattestation_detected_for_stale_records` | `7ce20b5` | `stale` | Re-attestation staleness cannot be hidden |
| Declared | `attested_by` is the human who attested | a recorded string, not an authenticated identity | — | — | `attested_by` is the human who attested |
| Declared | the roster is current and complete | the sweep is as good as the CSV HR exports | — | — | The roster is current and complete |
| Declared | re-attestation actually happens after the flag | the sweep reports staleness; a human must call registry attest and the platform records the claim without verifying the review | — | — | Re-attestation actually happens after the flag |
| Declared | the sweep is actually running on the estate | FIELD_LIFECYCLE_ROSTER is unset on both estates until arming step A1, so each scheduled tick is a recorded skip | — | — | The sweep is actually running on the estate |

### 12 — Executive Attestation Reporter

**Old (verbatim):** "board-level rollup: agents in production, conformance percentage, incidents and replays, expiring authorities; generates the quarterly AI-governance attestation the CEO signs. (all letters · CEO/board)"

**One-liner:** Quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs are unsigned drafts unless the signer and key are set).

**New:** Quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs are unsigned drafts unless FIELD_ATTEST_SIGNER and a signing key are set, which is the custodian's standing attestation, not a per-pack human act). Every number prints its source query; an unreachable service shows as unavailable, never zero.

**Why reworded:** "the attestation the CEO signs" is removed: a signature proves a key signed, not that the named person reviewed or approved the pack. "agents in production" and "conformance percentage" are what the platform governs, not everything the org runs. A log-only estate cannot read 100% conformant.

**Estate status:** Declared — not live-verified: this change ran no live catalogue check and touched no estate, so no row is shown to hold on a deployed estate; Phase G arming (REQUIRE) is not live on either estate. Keyless rows (the LLM judge, gateway egress calls) are not live-verified and need ANTHROPIC_API_KEY.

README: `services/attestation-reporter/README.md` (Enforced vs. Declared table)

| Status | Word | Test (path::test_name) | Commit | Asserts | README row |
|---|---|---|---|---|---|
| Enforced | every number carries its literal source query | `services/attestation-reporter/tests/test_attestation_reporter.py::test_every_number_has_a_source` | `655b63d` | `source` | Every number carries its literal source query |
| Enforced | an unreachable service is unavailable, never zero | `services/attestation-reporter/tests/test_attestation_reporter.py::test_adversarial_unavailable_service_never_fabricates_zero` | `655b63d` | `unavailable` | Unreachable services show as unavailable |
| Enforced | a tampered ledger surfaces as BROKEN in the pack | `services/attestation-reporter/tests/test_attestation_reporter.py::test_broken_ledger_shows_in_pack` | `655b63d` | `BROKEN` | A tampered ledger surfaces as BROKEN |
| Enforced | quarterly: --period is a strict UTC quarter | `services/attestation-reporter/tests/test_c4_window_and_signature.py::test_parse_period_is_strict` | `135330a` | `period` | `--period` is a strict UTC quarter |
| Enforced | a signed pack's signature covers every field of board-pack.json | `services/attestation-reporter/tests/test_c4_window_and_signature.py::test_every_field_of_a_signed_pack_is_inside_the_signature` | `135330a` | `signature` | A signed pack's signature covers every field |
| Enforced | served packs are unsigned drafts unless the signer and key are set | `services/attestation-reporter/tests/test_f4_served_signing.py::test_unset_env_serves_the_unsigned_draft_with_no_signed_via_key` | `b648118` | `signed_via` | Without both variables the served pack |
| Enforced | with the signer and key set, the served pack is signed and verifies | `services/attestation-reporter/tests/test_f4_served_signing.py::test_served_pack_is_signed_by_the_estate_key_and_verifies_with_attest_verify` | `b648118` | `estate-key` | Served pack signing |
| Declared | a valid signature means the named person approved the pack | it proves a private key signed the bytes; who holds the key and whether the signer string is that person is custody outside this service | — | — | A valid signature means the named person approved |
| Declared | an estate-key signature means the custodian reviewed this served pack | a standing attestation, not a per-pack review: every request is signed afresh | — | — | An estate-key signature means the custodian reviewed |
| Declared | the pack covers everything the org runs | it covers what the platform governs; ungoverned agents appear only through discovery or lifecycle findings | — | — | The pack covers *everything the org runs* |
