# Reviewer report: PR 662 (federation-broker bounds on contract and crossing text, whitespace-only refused), reviewer ssl-ff-reviewer-5

**Head reviewed: af3af8b3c1c8ef5cd886e8346f86294078587a10** (1 commit on current main b963407a; services/federation-broker/src/federation_broker/engine.py +39/-13 net, tests/test_org_normalise_c483.py 1 line, new tests/test_text_bounds.py +108). Run UNVERIFIED (cloud, no GX10). Not run: other services' suites, CI. I did not find a note naming this PR's builder; taken on Don's instruction after `dispatch.sh next` returned it.

**VERDICT: PASS WITH CONDITIONS** (29 of 32 mutants killed; 3 survivors, all LOW or LOW-MEDIUM, 2 shown real by probe; no conflict; identity clean).

## Objections first
1. Whitespace-only is refused but padded text is KEPT AS GIVEN (`" Acme "` is accepted and stored padded, probed on the unmutated head). That is the stated design ("never stripped: scope and data class are compared exactly") but it means two contracts that differ by a space are two contracts, and an operator who pastes a padded name creates a counterparty that no crossing request will match unless it pads the same way. The counterparty_org normalisation elsewhere (test_org_normalise_c483.py, touched by one line here) may cover it for the org; I did not read that path. MEDIUM-LOW.
2. The 256-character name cap and 100-item list cap are chosen values; both are pinned at the boundary on the 257/255 and 101/99 sides (n1 to n4 killed). The signature cap (512) is pinned only above (n5 killed, n6 survives).
3. Some text fields stay unbounded: `manifest` and the `dict` payloads, and `counterparty_pubkey_pem` (an existing validator checks it is an Ed25519 key). Not part of this PR's claim. LOW.

## Identity and base
Author and committer = Don Hagell <13129187+dhagell@users.noreply.github.com>. `git merge-tree` against main b963407a: no conflict. HIGH.

## Mutants (real lines; scratch worktree detached at the head; relative PYTHONPATH). Stage 1 = the new file (baseline 0 failed, 20 passed); a survivor goes to stage 2 = the whole federation-broker suite (baseline 0 failed, 211 passed)
Groups (killed / applied): constants n1 to n6 5/6 (survivor n6); field bounds w1 to w16 (name max, list item and list count caps for both lists, contract_ref, counterparty_agent_id, agent_id, manifest_signature, scope, data_class, request_summary, crossing and contract counterparty_org, contract_id) 15/16 (survivor w2); blank refusal b1 to b10 (check off, whitespace passes, list entries not inspected, each of the six field registrations on the two validators dropped, text stripped on return) 9/10 (survivor b10).
Totals COUNTED FROM THE LOG: 6 + 16 + 10 = 32 mutants applied; 29 killed (all by the new file), 3 survived (n6, w2, b10); none failed to apply.

## Survivors (probed on the unmutated head and on each mutant)
- w2 (`Name` without `min_length=1`): REAL and shown: `FederationContract(contract_id="")` is refused on the head and ACCEPTED under the mutant (HIGH). `contract_id` is the one `Name` field that has no blank check, so `min_length` is its only guard against an empty id, and no test sends an empty `contract_id` (whole suite too). F-PR662-1 LOW-MEDIUM.
- b10 (the blank validator returning a stripped string): REAL and shown: `counterparty_org=" Acme "` is stored as `" Acme "` on the head and `"Acme"` under the mutant (HIGH). The "never stripped" rule is stated in the code but pinned nowhere. F-PR662-2 LOW-MEDIUM.
- n6 (signature cap 511): not shown by a probe (my first probe built a crossing request that was refused for another reason at both lengths, so it proved nothing and I discard it). By the plain semantics of `max_length`, a 512-character value is accepted at 512 and refused at 511; MEDIUM-HIGH confidence that it is non-equivalent. The tests do not send exactly 512. F-PR662-3 LOW.

## Conditions
None block. Coordinator: GX10 16/16 and CI on this exact head. F-PR662-1 to -3 go in a NEW PR after the freeze (one test file).
