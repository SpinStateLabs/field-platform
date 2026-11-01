From verifier (cloud). Closes the PR 358 contradiction (my note 20261101-0757 against "PR 358 conflicts with main in docs/ENVIRONMENT.md"). Both statements are true; they measure different operations. Measured against main 7de2a064 and PR 358 head 07bd6d63, scratch tree, nothing pushed:

- A. Merge the head as a whole into main: CLEAN. The head is itself a merge of main that already resolved docs/ENVIRONMENT.md. This is what the cloud verifier gate does, so GREEN holds for a plain merge of the PR.
- B. Replay the PR's non-merge commits one by one onto main (cherry-pick, which is what a rebase or a patch-id batch does): CONFLICT at commit 961132a3, file docs/ENVIRONMENT.md. This matches the rebase builder's note 20261101-1215 and the coordinator's input.

So a batch built by cherry-picking PR 358's commits needs the one-hunk resolution described in the rebase builder note; a squash or merge of the PR head does not. The cloud gate cannot see B because it merges heads; heads that are merges of main (as 358's is) can look clean there and still conflict when replayed commit by commit. Cloud run, not a GX10 run.
