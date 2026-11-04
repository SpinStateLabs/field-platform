S5-6 field-core ConformanceVerdict clause rule. PR 682 draft, head 8d9d7baa.
Step 1 evidence: static scan (committed) + dynamic observer (not committed): sentinel 366, broker 39, field-core 4 constructions, 0 violations. Only field-core/sentinel/broker import the model. D.manifest_expired is raised via delegation-authority's own 422 helper, not a ConformanceVerdict.
Step 2: model_validator(mode=after): ALLOW+clause, BLOCK/ESCALATE without clause, clause not in CLAUSES -> ValueError.
Tests: test_conformance_verdict_clause.py 78 (34 red before). 9 mutants (5 validator, 4 producer-side) all caught. field-core 1622 passed; sentinel 263, broker 191, gateway 448, approver 315 passed; lint 225; anchors 0 wrong. No service source edited.
Decision for Don: a producer typo now raises at construction (sentinel /check -> 500, callers fail closed) instead of an unreplayable verdict; new clause ids must be registered with their first producer.
