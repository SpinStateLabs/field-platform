# C-611: read of PR 337 (ARCHITECTURE.md: fourteen services, missing arrows), Lane 10

Read: PR 337 head 99888f8 (docs/ARCHITECTURE.md only, +51 -5). Read-only; UNVERIFIED on any estate. Method: counted the services, derived every service-to-service edge from the source (`FIELD_*_URL` reads in each service's `src`, plus field-core client use), compared with the diagram's 37 edges, checked each cited file:line.

VERDICT: PASS with one missing arrow (F-C611-1) and one style point. Every number and line citation I checked is right; no estate address, flag value, build SHA or deploy status in the added lines. Confidence HIGH (run).

## ASSUMPTIONS
1. "Fourteen services" means the directories under `services/`; `field-core` and `field-agent` are packages; `defence-shield/agent-incident-retro` is outside `services/`.
2. An edge is real if the caller reads a `FIELD_<TARGET>_URL` in its source or builds a field-core `LedgerClient`/`RegistryClient`.

## Objections first
1. The diagram can still be incomplete in the direction nobody drew: I found one edge in the code that the diagram lacks (below), after the PR claims to add the missing ones.
2. Prose arrows are not arrows: `ops-console` reads twelve services but has no drawn edge to any (the text says so under the diagram); a reader of the picture alone sees a floating node. Deliberate, stated, LOW.
3. First-person voice in a public reference doc: three sentences read "I did not judge...", "I did not find...", "I do not know where ~53 ms comes from" (diff lines at the claude-approver arrow note, the sequence-diagram note). Honest, but a reference document should state the gap, not the author. LOW.
Steelman: the PR marks each new dotted arrow with the condition and file:line it rests on, and says what it could not verify.

## Results
- Service count: `ls services` = 14 (agent-registry, attestation-reporter, claude-approver, compliance-crosswalk, conformance-sentinel, delegation-authority, federation-broker, force-gateway, incident-replay, kill-switch, lifecycle-manager, ops-console, sealed-ledger, spend-governor); packages = field-agent, field-core. "field-core, the field-agent SDK and fourteen services" is correct. Ports `:8011` (ops-console) and `:8014` (claude-approver) match their CLI defaults.
- ops-console "reads twelve of the other thirteen": its `api.py` reads exactly 12 `FIELD_*_URL` variables (attest, crosswalk, delegation, federation, gateway, governor, killswitch, ledger, lifecycle, registry, replay, sentinel); the thirteenth, claude-approver, is not read. No `sqlite` in its source (0 hits). The `operator.refused` ledger write is at `ops_console/api.py:377-398`.
- New arrows, each checked: registry to ledger only when `FIELD_LEDGER_URL` is set (agent_registry/api.py:185-188; the PR cites :187: correct); gateway to sentinel in enforce mode, 503 and no upstream call on an unreachable or non-200 sentinel (force_gateway/api.py:36-37), events best-effort (:38-39); lifecycle-manager to governor is the CLI only (cli.py service table, `_service_client("governor", ...)`; the served `api.py` has no governor reference); crosswalk to delegation and governor evidence reads (compliance_crosswalk/api.py:224-232); claude-approver reads exactly `FIELD_GOVERNOR_URL`, `FIELD_KILLSWITCH_URL`, `FIELD_SENTINEL_URL`.
- Gateway events table: `gateway.bypass` (api.py:651), `gateway.drift_alert` (:711), `gateway.refused` (:545), `gateway.shadowed` (:572) and `gateway.tool_refused`, `gateway.passthrough` (docstring lines 22 and 47) all exist.
- Perimeter row: "refuses with 401, 403 or 503 and makes no upstream call" matches force_gateway/api.py:25-37 (401 for a missing agent id or token, 403 for BLOCK/ESCALATE, 503 for an unreachable sentinel).
- Figures: `$500/day`, `$120` and `96%` are at docs/capstone-evidence/field-agent.md:14-18; the run log line 33 says kill confirmed 43.6 ms, total 56.3 ms, as the PR states; the PR's "I did not find the 1 h token lifetime" is an honest gap.
- Public-safety scan of the 51 added lines (IPv4, long hashes, URLs, `enforce=`, "deployed", "live", "cutover", dates): no hit.
- Derived edges: 13 edges exist in code and not in the diagram: 12 are ops-console (the deliberate prose edges) and ONE is real and missing: sealed-ledger to agent-registry (`sealed_ledger/api.py:234-245, 290`: `create_app` builds a `RegistryClient()` per request from the environment for `/retention/check`, and the CLI reads `FIELD_REGISTRY_URL`). That makes registry and ledger depend on each other (registry to ledger is drawn, ledger to registry is not). 11 diagram edges have no `FIELD_*_URL` read in the caller's source; all are via field-core clients or the agent SDK (kill-switch, delegation-authority, federation-broker, crosswalk, replay to registry or ledger; invoicing-agent to four services), consistent with the diagram.

## Findings
F-C611-1 MEDIUM-LOW: add `LED -.->|"retention check reads the registry"| REG` (sealed-ledger api.py:234-245) and say in the text that registry and ledger call each other, each only when its URL is set or per request.
F-C611-2 LOW: draw ops-console as one edge to a "twelve services" note, or leave, and reword the three first-person sentences to the gap itself ("the 1 h token lifetime is not in an artifact").

## What I did NOT do
Did not render the mermaid or check the sequence diagram's participant order. Did not check edges for services outside `FIELD_*_URL` naming (the witness URL of the ledger). Did not read the PR's table rows beyond the ones cited. Did not edit the PR.
