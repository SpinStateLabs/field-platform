S8-15 -> https://github.com/SpinStateLabs/field-platform/pull/786
HIGH: red first (5 of 11 failed on main); empty/all-null PATCH -> 422; callers audited. NEEDS DON: 3 existing expectations changed (retired empty PATCH 200->422; two AgentUpdate() constructions use model_construct). 316 registry tests pass minus the slow race file.
