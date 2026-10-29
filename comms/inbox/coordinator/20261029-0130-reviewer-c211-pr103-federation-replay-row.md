# C-211 reviewer report (Lane 5): PR 103 docs/federation-broker-replay-c129 @2f5383160a6b0f796cf21493dada1b218402956f

VERDICT: PASS on the exact head 2f5383160a6b0f796cf21493dada1b218402956f. The new Declared row says exactly what the code does and no more: the signature is checked, nothing about freshness or the presenter is, and I reproduced both. Full gx10_verify is green on the head (based on current main 7b54f26).

OBJECTIONS FIRST
1. A Declared row is a statement of what is NOT enforced; the risk in writing one is claiming too little or too much. The row lists "no nonce, timestamp or window" and "a captured signed manifest verifies again"; it does not say that the manifest itself carries no expiry the broker could read, which is the stronger form of the same fact (it is implied). [HIGH]
2. The LIMITS section of the same README (line 113) still reads "Manifest signing ... provides *authenticity* only when the contract carries the counterparty's public key" with no mention of freshness; a reader of LIMITS alone gets a rosier picture than the table. LOW. [HIGH]
3. I tested the in-process broker (the repo's own stack fixture), not a deployed one with the field-agent SDK in front; the "SDK asks first" half of the row I verified by reading. [HIGH]

ASSUMPTIONS
1. Head is one commit on current main 7b54f26 (merge-base equals main), author and committer Don Hagell noreply, one file services/federation-broker/README.md, one insertion. [HIGH]

REASONING
1. The row (README.md:107): "A signed manifest is fresh, and the presenter is its owner (replay) | Declared only | the signature proves the manifest's origin, not its freshness or who presents it: there is no replay protection (no nonce, timestamp or window is checked; a captured signed manifest verifies again), and the ALLOW is advisory, since the broker decides and does not carry the traffic (the field-agent SDK's `cross` asks first, a cooperative perimeter)". It sits in the Declared table beside the other cooperative rows (lines 104-105, 108). [HIGH]
2. No replay protection in the code: `grep -i -E "replay|nonce|fresh|timestamp|expir|valid_until|issued_at|seen"` over services/federation-broker (excluding tests) finds nothing except the new README row. The inbound decision path (engine.py:407-488) verifies the Ed25519 signature of the presented manifest against the contract key and the other contract rules; no state of past crossings is read. [HIGH on the grep, MEDIUM on my reading of :407-488: I read the structure and the verify call, not every branch]
3. Reproduced "a captured signed manifest verifies again": in-process probe using the repo's fixtures (a keyed contract, one signed counterparty manifest): the same manifest and signature posted five times to `/crossing` gave `['ALLOW', 'ALLOW', 'ALLOW', 'ALLOW', 'ALLOW']`. [HIGH, run]
4. Reproduced "or who presents it": the same signed manifest and signature sent with a different `counterparty_agent_id` ("some-other-agent") gave ALLOW with the reason "crossing within contract FED-2026-001": the broker does not bind the signature to the presenting agent id. [HIGH, run]
5. "The ALLOW is advisory": the broker returns a decision and ledgers it; it does not proxy traffic (the service description, api.py:42: "decides inbound and outbound crossings; it does not carry the traffic") and the field-agent SDK's `cross` asks it first (packages/field-agent cli.py:151, "exit 0 ALLOW / 1 BLOCK or broker unreachable (fail closed)"); an agent that crosses without asking is invisible to it (existing row, line 105). [HIGH]
6. Consistency with the rest of the README: the Enforced row (line 98) claims only that unsigned or tampered manifests never cross inbound on a keyed contract (verified by tests for a missing signature, a tampered manifest, a wrong key); it does not claim freshness. The LIMITS note (objection 2) is the one place that could be read as more. No other file under services/federation-broker, docs/ or STATE.md claims replay protection (grep of the federation docs and the field-agent federation module for replay, nonce, window: none for the broker). [HIGH]
7. Full CI-equivalent run on the exact head (gx10_verify.sh, no --quick, name lane5pr103; code equals main 7b54f26): core_services 2209 passed 4 skipped; tools 1925 passed 3 skipped; agent-registry 238; sentinel 111; incident-replay 74; crosswalk 162 (1 skipped); gateway 210; lifecycle 185; attestation 66; ops-console 171; approver 101; field-agent 118; topology_lint OK. VERDICT CI-EQUIVALENT STEPS GREEN. The differences from the b1872ee baseline (core +28, sentinel +2, crosswalk +2, gateway +2) are the tests PR 96 added. [HIGH]
8. Public-repo hygiene: the row has no address, SHA, flag value or secret. [HIGH]

CONCLUSION
PASS on 2f53831. Optional: one clause in LIMITS line 113, "authenticity, not freshness or presenter identity", so the two places agree; card C-175 (inbound keyless contracts) is separate and unaffected.

What I did NOT do: read engine.py:407-488 line by line for every branch; test with the SDK in front; read any live estate.
