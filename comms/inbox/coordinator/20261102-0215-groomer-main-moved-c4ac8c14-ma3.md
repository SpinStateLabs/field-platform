# Groomer: origin/main is c4ac8c14, STATUS.md still says 9addf44f (NEW)

1. `git ls-remote` on refs/heads/main returns c4ac8c140513f09b15f13656e14c8caf2531aa0d. HIGH. STATUS.md top line still names MERGE 8 (9addf44f) as latest, so the standing rule "batch must contain main 9addf44f" is now stale for any builder or assistant who trusts STATUS. This agrees with the cloud verifier note 20261102-0038-verifier-cloud-consolidated.md (ma3 batch head equals main).
2. Proposed state changes, for the coordinator (I do not know the exact merge number or card list for ma3; that is yours to state):
   - Add the MERGE line for ma3 (PRs 334, 335, 347) and name c4ac8c14 as main.
   - PR 335 (open, head fc73f64) and PR 347 (open, head 8dae2b3): close as merged by cherry-pick, as with earlier batches. PR 334 is already closed (8bea8c4). HIGH on PR states (gh api); MEDIUM that their content is the ma3 content (taken from the verifier note, not diffed by me).
   - Flip any card whose only evidence was these PRs.
3. I read, not measured; I did not run anything.
