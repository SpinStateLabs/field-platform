# Lane 12: PR 425 against the new base 9addf44f; it carries the HELD PR 344

- PR 425 `fix/lifecycle-cli-cacert-c1098` head 186998a7 (built on 9468b184) merges clean into main 9addf44f (`git merge-tree`, no conflict; 3 commits behind). Not rebased and not pushed: the head-freeze rule stands and the note names batch and rebase branches, not PR branches; say so if you want 425 rebuilt on 9addf44f and I will do it as a new head with CI re-run.
- Your note says PR 344 is HELD by Don. PR 425 contains PR 344's four commits (rebased) plus the two --cacert commits, so if the hold is on 344's content, 425 inherits it; if the hold is only on landing 344 as its own PR, 425 is unaffected. Lane 1 chose 425 as the vehicle (20261101-2100). Your call; nothing moves from this lane until you say.
