# B-S2-2-controller-driver-args: PR 855 opened (stacked on PR 840), head 3dfd699ca28c

https://github.com/SpinStateLabs/field-platform/pull/855, base fix/stage-controller-defaults (PR 840, still open: Stage.services and build_sha_required are not on main). Retarget to main when 840 merges. plan --services (empty or unknown refused, default stage list, printed), --go-sentence needs --build-sha (build_sha_required, exit 2), runbook paragraph. 173 controller tests (154 before); 9 of 9 mutants killed; 210 passed with docs tests (PYTHONUTF8=1).
Deviation from "existing tests unchanged": four CLI tests that passed a go sentence without a sha now pass one, as the new rule requires (the other tests are untouched). Merge main into 840's head had two conflicts, both-sides kept.
Open: CI, GX10 on this head, review; merge order after 840. Not done (deployer-only): wiring the pg-run scripts. No estate touched.
