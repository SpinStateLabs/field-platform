VERDICT: PASS WITH CONDITIONS on c3fd1447e249aa080f277d85c5b9964165c2b371 (UNVERIFIED: cloud reviewer, docs read against source at that head; no suite run, CI not read)

Head matches the card. Two commits on main 5808a5c (99888f8, c3fd144); author and committer of both are the no-reply identity. One file: docs/ARCHITECTURE.md, +55 -5.

OBJECTIONS FIRST
1. The sequence diagram still carries unsourced figures ("1h TTL" at ARCHITECTURE.md:204 and "~53 ms" at :216). The PR adds a note saying they are demo figures and that two of them are not in any artifact, rather than removing or correcting them. A reader who stops at the diagram gets the numbers without the caveat (the caveat is only a "Note over" line and a paragraph below).
2. Several citations point at docstrings or signatures rather than the line that does the thing: ledger-to-registry is cited to sealed_ledger/api.py:234-239 (the create_app signature and its docstring); the constructor call that builds a RegistryClient per request is at api.py:323. Gateway claims cite the module docstring (force_gateway/api.py:25-39) for enforce behaviour, not the handler. A docstring can drift from code.
3. Completeness: the diagram draws no individual arrow for ops-console (twelve services read), only prose. That is stated, but "the missing arrows" are therefore still missing for the largest client.
4. "Whether the claude-approver arrows are required is not established here" is honest but leaves three dotted arrows of unknown status in the main diagram.
5. Estate wording remains in a changed row: "(secretless estates only ...)" for gateway.passthrough. It describes a posture, not a deployment, but the card asks for deploy status; it states none.

ASSUMPTIONS
A1 Source of truth: the repository at the PR head. A2 "Arrow" = a runtime call made by source in services/<name>/src, found by reading the client classes each service imports and the FIELD_*_URL variables it reads. A3 No run of any service.

REASONING
1. Service count: ls services at the head lists 14 directories (agent-registry, attestation-reporter, claude-approver, compliance-crosswalk, conformance-sentinel, delegation-authority, federation-broker, force-gateway, incident-replay, kill-switch, lifecycle-manager, ops-console, sealed-ledger, spend-governor); packages/ holds field-agent and field-core. The "fourteen services" claim and the "field-core + field-agent + fourteen services" sentence hold. HIGH.
2. Ports: ops-console 8011 (ops_console/cli.py:26) and claude-approver 8014 (claude_approver/cli.py:26) match the new diagram nodes. HIGH.
3. ops-console "reads twelve": api.py:336-358 read twelve FIELD_*_URL variables (registry, ledger, delegation, sentinel, killswitch, governor, replay, crosswalk, gateway, federation, lifecycle, attest); the only service it does not read is claude-approver (12 of 13). HIGH. "No SQLite in its source": a case-insensitive search finds nothing. HIGH. operator.refused over the console's ledger client: api.py:383-402; the cited 377-398 matches. No other ledger append found. HIGH.
4. Registry to ledger only with FIELD_LEDGER_URL set: agent_registry/api.py:187. HIGH. Ledger to registry per request: sealed_ledger/api.py:238-239 docstring and :323 construction. HIGH.
5. Crosswalk to delegation and governor: compliance_crosswalk/api.py:224-226 define the bases, 214-219 the read (a non-200 or any exception returns None, so "a failed read yields none" holds). HIGH.
6. Lifecycle to governor, CLI only: lifecycle_manager/cli.py:187 (table entry) and :211 (client in the estate clients); the served API file has no governor client. HIGH for the CLI; the negative for the served API rests on a search, MEDIUM.
7. Gateway: events set found in api.py is exactly bypass, drift_alert, passthrough, refused, shadowed, tool_refused; the doc lists all six with lines 651, 711, 545, 572, 633 (each line is the _ledger_event call for that type); passthrough has no line cite. Enforce-only sentinel arrow and "503 without it, no upstream call": docstring api.py:36-37 and code at the enforce handler. HIGH.
8. Claude-approver: reads FIELD_SENTINEL_URL, FIELD_KILLSWITCH_URL, FIELD_GOVERNOR_URL (claude_approver/config.py:90, 94, 98) and keeps its cursor at $FIELD_DATA_DIR/claude-approver/usage-cursor.json (core.py:19-21; the doc cites 20-22: off by one line). HIGH.
9. Cross-check of drawn arrows against imports: kill-switch uses ledger and registry clients (arrows present); spend-governor ledger only (present); federation-broker ledger only (present); incident-replay registry client plus ledger/delegation by URL (present); sealed-ledger registry client (new arrow present). I found no service-to-service call in these files that the diagram lacks, beyond ops-console (drawn in prose). MEDIUM (client-class and variable search, not a full call-graph).
10. Demo figures note: docs/capstone-evidence/field-agent.md:14-18 shows $120 and the $500/day cap and the 96% meter; field-agent-run.log:33 shows kill confirmed 43.6 ms and total 56.3 ms; the diagram's 53 ms and 1h appear nowhere in those files. The note's statements hold. HIGH.
11. Diff scan: no address, SHA, credential, flag value, or deploy statement added. HIGH.

CONCLUSION
PASS WITH CONDITIONS. Count, ports and every arrow I could trace match code; the PR leans on honest caveats where it could not source a figure. Conditions, none blocking:
- C1 F-C656-1 either remove or source "1h TTL" and "~53 ms" in the diagram itself.
- C2 F-C656-2 cite the call sites (sealed_ledger/api.py:323, the gateway handler) next to the docstring cites.
- C3 F-C656-3 decide the claude-approver arrows (required or optional) from code in a follow-up; they are drawn dotted.

FINDINGS
F-C656-1 LOW, docs/ARCHITECTURE.md:204 and :216 (unsourced demo figures kept in the diagram). HIGH.
F-C656-2 LOW, docs/ARCHITECTURE.md (the ledger-to-registry cite; gateway cites to docstring lines 25-39). HIGH.
F-C656-3 LOW, docs/ARCHITECTURE.md (the three claude-approver arrows, "not established here"). HIGH.
F-C656-4 INFO, cursor path cite 20-22 should be 19-21 (core.py). HIGH.
F-C656-5 INFO, no arrow-level drawing for ops-console. HIGH.

NOT VERIFIED: a full call graph (client-class and URL-variable search only); behaviour at runtime; CI; the rendered diagram; the lifecycle served API's absence of a governor call beyond a search.
Process note: I extracted the PR into a scratch directory (git archive, no worktree); it was deleted; nothing in any PR tree was modified or committed.
