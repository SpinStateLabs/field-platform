# R-09 reviewer report: services/federation-broker read and mutants (main 9292246)

VERDICT: the decision clauses are well pinned (54 of 55 engine mutants killed), but the inbound path has no caller authentication when a contract carries no key, and there is no replay protection at all. Both are design properties, not coding slips.

OBJECTIONS FIRST
1. The broker's own docstring says it "trusts nothing about the counterparty except what it can check"; for a keyless contract it can check nothing about the caller.
2. "Replay window" in the backlog item presupposes one exists; I looked for it and it is not in the source.
3. My mutator generates only `if`/comparison mutants: 65 of 66 killed is not a coverage figure.

ASSUMPTIONS
1. Main 9292246; engine.py (547 lines) read in full; api.py (94) and cli.py (212) mutated, api.py not read in full. Suite: 92 tests, 2.3 s. [HIGH]

REASONING
1. Mutants: engine.py 55 (54 killed, 1 survived), api.py 4 (3 killed), cli.py 7 (6 killed). [HIGH]
2. MEDIUM, F-R09-1: inbound `_decide_inbound` (engine.py:407-488): `req.counterparty_org` is a request field; the manifest is self-declared; the only authentication is step 4, which runs only `if contract.counterparty_pubkey_pem is not None` (:457). A keyless contract (the field defaults to None, :143-149) therefore ALLOWs any caller that names the org, presents any valid manifest with `federated.isolated: false` and our org in `allowed_peers`, and asks for a scope and data class inside the contract. The peer listing is trivially self-asserted. [HIGH, read; not live-probed]
3. MEDIUM, F-R09-2: no replay protection (not in source). `verify_manifest(manifest, signature, key)` (:476) signs the manifest only: no nonce, timestamp, expiry, request or caller binding appears in `CrossingRequest`'s clauses 1-5. A captured (manifest, signature) pair authenticates the manifest, not the presenter, and is valid forever. The broker returns a decision and carries no traffic, so the impact depends on what the caller does with ALLOW; I do not know the downstream use. [HIGH on the absence, LOW on impact]
4. LOW, F-R09-3: `_lists_org` (engine.py:340-348) is a case-insensitive SUBSTRING rule. Probe: peer `Not Spin State Labs Ltd` lists `Spin State Labs`: True; peer `Acme Corporation Holdings` lists `Acme`: True; `Spin State Labs-evil`: True. It is documented ("lenient") and pinned by `test_outbound_peer_rule_is_the_lenient_substring_rule`, so it is a decision, but `for_org` (SQL equality, case-sensitive) is stricter than the peer rule: two different org-matching semantics. Outbound the manifest listing is OUR own, so the risk is limited to a mislisted peer. [HIGH]
5. LOW, F-R09-4: a failed crossing ledger append is swallowed (`except Exception: pass`, engine.py:~392-394) with the comment "the audit gap is visible"; engine.py has no counter or log at that site. I did not read api.py fully, so a visible signal elsewhere is not excluded. [MEDIUM]
6. Survivors (all LOW, F-R09-5): engine.py:343 `not isinstance(peers, list)` -> False (a non-list `allowed_peers` is untested; manifest validation likely rejects it first, not probed); api.py:82 `contract.contract_id != contract_id` (path/body mismatch 422, the same class as F-R08-4); cli.py:105 `status_code != 200` flip (the CLI error branch). [HIGH]
7. Pinned and sound: pubkey handling (`_ed25519_public_pem`: exact single Ed25519 public PEM, private-key text refused, canonicalised, non-whitespace extras refused; unusable stored row fails the crossing closed, :459-466), signature required when a key is held (:470-475), invalid signature BLOCK (:476-486), scope and data class inside the contract (both directions), outbound skips the signature step by design. [HIGH on mutants]

CONCLUSION
No coding defect found in the decision clauses. Two design findings for Don: (1) a keyless contract authenticates nobody: require a key for any contract that allows inbound, or label keyless contracts outbound-only; (2) add a nonce/timestamp to the signed material if the ALLOW is ever used to authorise a real action. Not done: full read of api.py/cli.py, arithmetic/argument mutants, a live crossing.
