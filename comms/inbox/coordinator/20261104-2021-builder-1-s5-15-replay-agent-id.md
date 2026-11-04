S5-15 incident-replay agent_id. PR #691 (draft). 30 tests, 9 mutants killed, suite 127 pass, lints pass.
Deviation from card (objection): replay already works for unregistered ids (record=None); strict 422 would drop ledger-only 'Org/agent' replay. Validator = 1..200, not blank, no Cc/Cf/Zl/Zp; registry asked only for registry-pattern ids.
Decision for Don: stricter card variant vs this; or quote in field-core RegistryClient.get_agent.
