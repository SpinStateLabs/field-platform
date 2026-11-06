# B-COND-PR512-756e5c4: no push; the conditions are CI and GX10

Head stays 756e5c4f. C1 (CI 7/7 on the head) and C2 (GX10 16/16 on a head containing main) are verification, not builder code; 35 of 37 mutants killed. Optional, new PR after the freeze: card B-FU-PR512-tokens-pins (tests only, compliance-crosswalk): a tokens reply `[ {}, "x" ]` and `[1]` so weakening the `all(isinstance(t, dict) ...)` guard fails (T1); F-512-2 (an empty agent id builds `?agent_id=` with no filter) belongs with the PR 496 empty-filter decision, not here.
