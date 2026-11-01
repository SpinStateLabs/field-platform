# Builder Lane 16: Q-52 conditions closed on PR 421 (B-21); old head a1491046, new head 849fdaef

PR 421 `ci/tools-tests-two-shards-b21`: old head a14910463f36ac3152ad5484699853308abf05ea (Lane 7's reviewed head; re-fetched before the push, unmoved), new head 849fdaef68a9166c151fc095f24a2965622aa562, two commits, fast-forward, author and committer Don Hagell, both trailers. PR body updated.

| Finding | Result | Commit |
|---|---|---|
| F-Q52-1 MEDIUM-LOW | The guard requires the matrix to be exactly python-version and shard (no include, no exclude), the version list 3.11 to 3.14, and no continue-on-error on the job or any step. Lane 7's M21, M24, M26 are now red. | d7977ee |
| F-Q52-4 LOW | The topology-lint step must exist once on shard 2 and run `python tools/topology_lint.py` (M20 red). | d7977ee |
| F-Q52-2 LOW | Shard 2 computes its list first and exits 1 with a message when it is empty; `xargs -r`. Three behaviour probes run the extracted step under bash with a recording pytest shim: shard 1 receives the literal six; shard 2 receives exactly the other modules present; an empty shard 2 and an unknown shard each exit 1 without calling pytest. The empty-shard probe and the regex pin are red on the previous workflow. The probes skip only when bash is not on PATH (GX10 under Git Bash has it). | 849fdae |
| F-Q52-3 INFO | Not changed: a name with a space fails closed (pytest exit 4); HEAVY admits `\w` names only. | |
| F-Q52-5 INFO | Correction accepted: my note's "jobs started 00:34 to 00:53" mixed a start and a completion; the starts were 00:34 to 00:44, the waits 22 to 32 minutes. | |
| F-Q52-6 INFO | Not changed: duplicate keys are test_yaml_duplicate_keys's. | |

Mutants in the guard file now 14 text mutants red (the earlier 7 plus exclude, include, a dropped version, continue-on-error on the job, on the step, the lint step gutted, the empty-shard refusal dropped). Checks on 849fdae: guard 19 passed; test_ci_pip_pins_c23, test_yaml_duplicate_keys, test_workflow_security_lint, test_ci_external_ref_guard_c101, test_ci_pytest_module_names, the caller-signed CI guard: green. One environmental note: test_ci_pytest_module_names went red here only because I had installed federation-broker from the 48acfa6 tree for the C-493 count; reinstalled from this tree, green.

Measured on PR 421's own run 41284958954 (HIGH, public jobs API, read at 07:5x): tests (3.12, 1) 8m41, (3.12, 2) 8m48, (3.13, 1) 7m52, (3.14, 2) 11m44; the remaining four shard jobs were still running at my read; smoke jobs green. Lane 7's O1 stands: the queue, not the step time, decides the wall clock; the first main run after merge measures it. CI on 849fdae: a new run, not yet read.

For the coordinator: C1 (11 of 11 on the exact head), C2 (the gate count is 11 after merge; no branch-protection rule exists per Lane 7's API read), C4 (PR 414 conflicts in ci.yml; whoever lands second keeps the vulture step on a real shard; the guard would refuse a shard that does not exist). Reviewer delta on 849fdae needed. Decision for Don: none.
