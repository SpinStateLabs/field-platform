# C-174 reviewer report: third remote-branch delete list (script `20261029-2700-reviewer-c174-delete-branches-3.sh`, main 7b4d6f7)

DELIVERED: 38 `del` lines, DRY-RUN by default, not run by the reviewer. Don approves; the coordinator runs it.

OBJECTIONS FIRST
1. Deleting a closed-superseded branch is safe only if its content really is in main; "closed PR plus a merged -r2" is a name pattern, so each B line names its successor and the report states what evidence I have.
2. The branch list is a snapshot: heads move; the script re-checks every tip.
3. I could not run the script's shell in this environment (WSL bash cannot use the Windows worktree); I verified `bash -n` and re-implemented the tip check in PowerShell.

ASSUMPTIONS
1. `git fetch --prune` at main 7b4d6f7533fe94fd42cea1f79149a4ed1a863ff5; 45 remote refs, 93 PRs from `gh pr list --state all`. [HIGH]

REASONING
1. Selection: every remote head except `main`, `comms` and the live set (`feat/kr-r4a-rotator-core` #57 open, `fix/renew-token-signed`, `fix/operators-loader-c178` #93 open at listing time, `fix/registry-retired-store-guard-c167` #92 open at listing time) and the pseudo-ref `origin`. [HIGH]
2. A. 18 heads whose tip IS an ancestor of main (`git merge-base --is-ancestor`): batch/2026-10-29-a and -b, the merged `-r2` heads (docs/crosswalk-readme-c139-r2, feat/alerts-ntfy-r2, fix/breakglass-alias-squat-r2, fix/gateway-followups-r2, fix/observer-witness-content-edit-r2, fix/refused-record-drop-counted-r2, fix/registry-retired-terminal-c161-r2, test/*-r2 x6), the merged originals fix/breakglass-alias-format1, fix/breakglass-must-be-sealed, and feat/machine-verifier-identity-r3 (no PR). Nothing on them is missing from main. [HIGH]
3. B. 19 heads with a CLOSED PR, not ancestors of main, each superseded by a merged successor named in the script comment: 11 have a merged `-r2` PR; 8 are content merged through batch A or B (#55 -> 7 patch-identical commits in #73, C-110; #71, #67, #68, #69, #72 by patch-ids in C-107 and C-114). The `-r2` merges are the rebased same patches (range-diff `=` or patch-id equal in my C-120/C-123/C-131/C-134/C-140/C-154/C-158 reports). [HIGH for the ones I reviewed; the successor PR is merged for all 19, from `gh`]
4. C. 1 head, no PR, not an ancestor: `test/observer-deadline-primitives-r2` (dc06e22): its one commit adds the same 81-line file as main's 0b44dee (added-line text compared equal). [HIGH]
5. Verification just now: all 38 recorded tips equal `git ls-remote --heads origin` (0 moved, 0 absent); none is protected; none has an open PR (open heads at this moment: `fix/operators-loader-c178-r2`, `feat/kr-r4a-rotator-core`); `bash -n` clean. The script also refuses any branch with an open PR when `gh` is present (new safety rule) and keeps the C-63/C-74 rules (sha check, protected list, DRY=1 default). [HIGH]
6. Recovery: `git push origin <sha>:refs/heads/<branch>` (shas in the file); every merged and closed PR head also stays available as `refs/pull/<n>/head`. [HIGH]

CONCLUSION
Safe to run after Don's approval. Later candidates (not in this list): `fix/registry-retired-store-guard-c167` (PR 92 merged), `fix/operators-loader-c178` (PR 93 closed, rebased as PR 94) once PR 94 merges.
