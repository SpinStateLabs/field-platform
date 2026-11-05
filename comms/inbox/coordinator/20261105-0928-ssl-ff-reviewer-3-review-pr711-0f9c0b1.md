# Review PR 711 @ 0f9c0b124f9f57e6f1ac0a39ee605560ed9a0c97 (federation-broker: refuse lone surrogates in contract and crossing text, S6-11) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 0f9c0b12. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head rebased on current main still required.

## Objections first
1. The claim is that pydantic already refuses a lone surrogate in a bounded plain `str` and misses it in list entries, optional strings and nested dicts. A walker that misses one container type (dict keys, tuples, deeper lists) leaves a 500. Probed per container (F3-F8).
2. The fix is a model-wide `after` validator over every field; a field added later is covered automatically, which is better than per-field annotations (compare PR 555).
3. `hide_input_in_errors=True` on `CrossingRequest` keeps a validation error from quoting the request; the contract model already had it.

## Facts (HIGH)
- Head fetched via refs/pull/711/head = 0f9c0b12; 1 commit; eight commits behind current main, with a clean `git merge-tree` against current main; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +148 -1: `federation_broker/engine.py` (`_first_unencodable`, `_refuse_unencodable`, a validator on `FederationContract` and on `CrossingRequest`, `hide_input_in_errors` on the crossing model), `tests/test_lone_surrogate.py` (+111, 19 cases).
- Baselines unmutated: new file 19 passed; whole federation-broker suite 210 passed.
- Completeness probe (my own script against the head; a lone surrogate as JSON `\ud800` in every text field): contract `contract_id`, `counterparty_org`, `contract_ref`, an entry of `allowed_scopes`, an entry of `allowed_data_classes`; crossing `counterparty_org`, `scope`, `data_class`, `counterparty_agent_id`, `request_summary`, `manifest_signature`, a value and a key inside `counterparty_manifest`: all 422, none a 500.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| the string check: never refuses, ascii instead of utf-8 (F1, F2) | 2 | 2 | 0 |
| containers: dict keys, dict values, dict recursion, list recursion, only the first list item, tuple recursion (F3-F8) | 6 | 5 | 1 (F7) |
| every field is walked, the refusal raises, the message holds no text and names the field (R1-R4) | 4 | 3 | 1 (R4) |
| both models carry the validator and it returns the model (V1-V3) | 3 | 3 | 0 |
Totals counted from the table: 2+6+4+3 = 15 rows; killed 13; survived 2 (F7, R4); 1 further edit (H1, `hide_input_in_errors`) did not anchor (its text occurs twice) and is not counted.

## Survivors (each also survives the whole suite)
- F7 EQUIVALENT: a tuple cannot come out of JSON; only a Python caller could pass one.
- F-R711-1 LOW (R4): the refusal message naming the offending FIELD is unpinned (the tests check the 422 and that the marker is absent, not the name).

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
