S5-8 agent-registry request-model bounds. PR #684 (draft). 43 tests, 8 mutants killed, 354 registry tests pass, 3 lint tests + anchors pass.
Decisions for Don: manifest_ref not stripped (test_d3b); no domain pattern (uppercase domains used); AgentRecord lenient for legacy rows; limits 200/200/64/512/200 are card suggestions.
