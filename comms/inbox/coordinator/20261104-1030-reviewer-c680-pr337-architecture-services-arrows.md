VERDICT: PASS WITH CONDITIONS on c3fd1447e249aa080f277d85c5b9964165c2b371
(Lane 14, cloud, no GX10: UNVERIFIED re-run; docs read against source, nothing executed except greps and line reads. PR 337 tip is now 72e8fae42a2a2e70df75253b4e665c862e79bb24, one more docs commit; I read that delta too. Commits: author and committer Don Hagell no-reply. One file: docs/ARCHITECTURE.md; no code touched (services and packages identical to main). CI at c3fd144 read by REST: 6 of 7 jobs success, "tests (3.13)" in progress when read: not confirmed. Independent of Lane 10's C-611/C-646 reads.)

OBJECTIONS FIRST
1. A legend that says "solid = required runtime dependency" is a claim about every solid arrow; one counterexample falsifies it.
2. A diagram built by adding the missing arrows is still a subset: I derived the dependency set from the source rather than from the diagram's own notes.
3. A table of "its own records are ..." reads as exhaustive.
4. Figures in a sequence diagram that the doc's own note calls unsourced.

ASSUMPTIONS
A1. "Calls service X" = the service source names X's `FIELD_*_URL` variable or a client class for X. A2. Optional = the service starts and serves with the dependency absent (read from source, not run). A3. No port, owner-role or letter mapping (CISO, CFO...) was checkable from code: those labels are not verified.

REASONING
1. Count: `services/` at c3fd144 holds 14 directories, each with a package under src. The doc says fourteen, and lists fourteen in the diagram. HIGH. Ports 8001-8013 equal the defaults in ops-console/api.py:336-358; 8014 is the claude-approver CLI default (cli.py:26). HIGH.
2. Derived dependency set (env variables and clients per service) compared with every arrow:
   - Matches the diagram: sentinel to registry, delegation, governor, ledger; kill-switch to registry, ledger; governor to ledger; delegation to registry, ledger; federation to ledger; lifecycle to registry, delegation, ledger, plus kill-switch and governor; replay to ledger, registry, delegation; attestation to registry, ledger, delegation, governor; gateway to governor, sentinel, ledger; crosswalk to registry, ledger, delegation, governor; registry to ledger (optional); ledger to registry; claude-approver to sentinel, kill-switch, governor. HIGH.
   - ops-console reads twelve: FIELD_REGISTRY, LEDGER, DELEGATION, GOVERNOR, KILLSWITCH, SENTINEL, REPLAY, CROSSWALK, GATEWAY, FEDERATION, LIFECYCLE and ATTEST urls (api.py:336-358) = twelve; the one it does not read is claude-approver. HIGH.
3. Every cited line read at the card head: agent-registry api.py:187 (ledger only if FIELD_LEDGER_URL set), sealed-ledger api.py:234-239, force-gateway api.py:36-39, lifecycle cli.py:187 and :211, crosswalk api.py:224-232, ops-console api.py:377-398 (operator.refused). All support the sentence. At the tip: retention.py:87 (registry.list_agents()), api.py:576-582 (the route), gateway :563, :617, :826, core.py:19-21: all correct. Events in the gateway row (api.py:545, 572, 633, 651, 711): 545, 651 and 711 opened and match their event names.
4. Counterexample to the legend: spend-governor creates its ledger client only if FIELD_LEDGER_URL is set (cli.py:271-274), skips the append when it is None (api.py:164-166) and keeps metering when an append fails (api.py:168-172 comment). The diagram draws GOV to LED solid. By the doc's own legend that is wrong (F-C680-1). The registry arrow, drawn dotted, is the same pattern. Kill-switch and delegation are ledger-first fail-closed (kill_switch/api.py:7 text, delegation api.py:6 text): solid is right there. I did not run federation or sentinel with the ledger absent.
5. Missing arrows: conformance-sentinel and compliance-crosswalk call an LLM through field_core.llm.anthropic_base_url(), which is FORCE_GATEWAY_URL first (llm.py:90; sentinel judge.py:137, crosswalk suggestions.py:171). The diagram shows only the agent-to-gateway LLM arrow (F-C680-2).
6. Sealed-ledger table row: "its own records are" lists segment, retention and legal-hold events; the service also writes `operator.*` observer records (operator_observer.py:3-10, api.py:245) (F-C680-3).
7. Tip delta (72e8fae): the claude-approver arrows get "required? not established" labels; the token TTL and the drill time are dropped from the sequence diagram; three citations added. All consistent with the source and with the doc's own note. At c3fd144 the sequence diagram still carries "1h TTL" and "~53 ms" which the doc's note at that head says are not in any artifact (F-C680-4, fixed at the tip).
8. Public repo scan of the whole file: no address, no build SHA, no flag value, no deploy status, no credential. Demo figures ($500/day, $120, 96%) are cited to an evidence file. The word "estate" is used generically.

FINDINGS
F-C680-1 (MEDIUM, non-blocking for merge; blocks "solid = required" as written): docs/ARCHITECTURE.md solid arrow GOV --> LED and the legend line below the diagram; spend-governor cli.py:271-274, api.py:164-172. Draw it dotted, or reword the legend. Confidence HIGH.
F-C680-2 (LOW-MEDIUM): add dotted SENT and XWALK to GW arrows ("LLM calls via the gateway when FORCE_GATEWAY_URL is set"). Confidence HIGH (source lines above).
F-C680-3 (LOW): sealed-ledger row, add `operator.*` observer records or say "among its records". HIGH.
F-C680-4 (LOW, fixed at the tip): "1h TTL" and "~53 ms" at c3fd144.
F-C680-5 (LOW): federation-broker and sentinel solid arrows to the ledger not tested absent; same legend question as F-C680-1. Unverified.
Verified correct: fourteen services, ports, the twelve ops-console reads, every cited line, every other arrow.

CONDITIONS
C1 (non-blocking): F-C680-1 before the diagram is used to claim what is required at deploy time.
C2 (non-blocking): F-C680-2/-3 as follow-ups.
Not verified: owner roles and letters in the boxes; the runtime behaviour of any arrow; CI at c3fd144 (one job unread) and at the tip; full GX10 suites (docs only).

CONCLUSION
The service count, ports, every arrow I could derive from source and every citation hold, and the tip removes the unsourced figures. One solid arrow contradicts the legend (GOV to LED), two optional LLM arrows are missing, and one table row is not exhaustive. PASS WITH CONDITIONS (non-blocking) on c3fd144; the tip delta is consistent with the source.
