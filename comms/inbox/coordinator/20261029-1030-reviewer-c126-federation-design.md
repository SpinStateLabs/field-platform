# C-126 reviewer report (design, for Don, D-19): federation-broker F-R09-1 / F-R09-2 / F-R09-3 on main 444e49b

VERDICT: today the broker's ALLOW is advisory, so both MEDIUM findings have LOW present impact; they become real the day an ALLOW gates a real transfer or credential. Smallest controls below; no code written.

OBJECTIONS FIRST
1. "Advisory today" is true of the code I found, not of every deployment: I cannot see which contracts exist on a live estate.
2. A control that blocks keyless inbound crossings breaks the shipped demo and any live keyless contract.
3. Adding replay protection now builds a protocol (signed nonce/time, a seen-set) for a decision nothing enforces.

ASSUMPTIONS
1. Main 444e49b, `git grep` over services, tools, packages, docs, integration. Live estates not touched. [HIGH]

REASONING
1. Downstream use of ALLOW: the only consumer of `POST /crossing` is the field-agent SDK (`packages/field-agent/src/field_agent/federation.py`, `FederationClient.cross`, `FieldAgent.cross`, `fieldagent cross`). Its docstring: "The SDK asks; it never relays ... An agent that never calls this is not federation-gated (cooperative perimeter)". No service, tool or compose file consumes a verdict; the broker issues no token or credential and carries no traffic. `/crossing` is declared unguarded (kill-switch README: federation `/crossing`), `PUT /contracts` needs scope `federation`. [HIGH]
2. What a keyless contract is for: the README documents `--pubkey` as optional (`fedbroker add-contract ... [--pubkey their-public.pem]`) and states "re-registering without `--pubkey` makes it keyless again"; `services/federation-broker/demo.sh:79` registers `FED-2026-001` keyless. Purpose in source: demo and a counterparty that has not yet supplied a key; the README table says "Keyed contracts: unsigned or tampered manifests never cross INBOUND", so keyless inbound is by design unauthenticated. [HIGH]
3. Is any shipped contract keyless: the repo ships no contract data (contracts are runtime rows in the broker's sqlite store); the only keyless contract in the repo is the demo's. Whether a live estate holds one: I do not know (not in source; reading `GET /contracts` on a live estate is outside my remit). [HIGH on the repo, unknown for live]
4. Smallest control for F-R09-1 (keyless authenticates nobody): in `_decide_inbound`, when `contract.counterparty_pubkey_pem is None` return BLOCK `F.peer` "inbound crossings require a contract key"; keyless contracts stay valid for OUTBOUND (the key is not used there). About 6 lines plus the tests that pin keyless inbound ALLOW; the demo gains a keygen/sign step. Alternative with the same size: an explicit contract field `allow_unsigned_inbound` (default False), so keyless inbound is a recorded, GC-chosen exception. Either way a keyless contract that is live today starts BLOCKing inbound after the change (fail closed). Recommend the first, with the demo updated. Don's call. [MEDIUM: design judgement]
5. Smallest control for F-R09-2 (no replay protection): none in code now. Add one row to the README "Enforced vs Declared" table: the signature proves the manifest's origin, not freshness or the presenter; record it as Declared. Build signed `{manifest, request nonce, issued_at}` plus a seen-nonce table only when an ALLOW starts gating a real action or credential. A pure-code alternative to reduce exposure now: none cheaper than the doc row. [MEDIUM]
6. F-R09-3 (substring peer rule): keep. The peer listing is a manifest self-declaration, so an exact match adds no security (a forger lists the exact org), and a test (`test_outbound_peer_rule_is_the_lenient_substring_rule`) pins the leniency for real manifests with suffixes such as "(Canada)". The authoritative org identity is the exact `for_org` contract lookup. Downgrade to INFO. [HIGH]

CONCLUSION
For D-19: (1) refuse keyless inbound (recommended, small, fail-closed upgrade effect on any live keyless contract); (2) document replay as Declared now, build it with the first ALLOW that gates something real; (3) accept the lenient peer rule. Not known: whether a live estate holds a keyless contract.
