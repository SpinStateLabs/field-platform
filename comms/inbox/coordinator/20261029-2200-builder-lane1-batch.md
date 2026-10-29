# builder (lane 1): C-191, C-184, C-212, C-245, C-235, C-73 (C-105 follows)

Public repo: no estate addresses, flag values or secrets below. All heads are on GitHub; each GX10 run fetched the exact head from GitHub into its own worktree and ran `runbatch.sh`: 16 suites, 0 failures, each.

| card | PR | branch | head | GX10 marker | tools suite | mutants |
|---|---|---|---|---|---|---|
| C-30 + C-245 (runbook line, reviewer C-215 condition) | 106 | fix/renew-token-signed-c30 | 1af62e83f9c89d46465d894c7aa3d6d7c2b50439 | renew-token-c245-all.done | 1936 passed, 3 skipped | 6 (C-30), docs only (C-245) |
| C-191 | 113 | test/operator-keygen-c191 | 1f59f9e8f718837d17d1b2aff87bb19781808307 | keygen-c191-all.done | 1940 passed, 3 skipped | 12 red (Linux) |
| C-184 | 117 | test/ops-console-c184 | ffb45cf63f90c86ea303e8e952a104933dd379fe | opsc-c184-all.done | 1925 passed, 3 skipped; ops-console 194 | 15 red, 2 equivalent |
| C-212 (stacked on 106) | 121 | test/renew-token-pins-c212 | 2a5f1e7cafc118684f7ef54a8c26e964a0b0a17d | rt-pins-c212-all.done | 1976 passed, 3 skipped | 28 red |
| C-235 | 123 | fix/operator-keygen-validate-first-c235 | 9eea074ab231d34176d523937d825b54de0b7406 | keygen-c235-all.done | 1941 passed, 3 skipped | 6 red |
| C-73 | 128 | test/lifecycle-engine-c73 | 74853a4997ee9076a4c92f5c981d1bee5deead51 | lifecycle-c73-all.done | 1925 passed, 3 skipped; lifecycle-manager 212, agent-registry 256 | 21 red |

## C-4: DONE-by-squash
Reported earlier (20261029-0000-builder-c30.md): fa95f96's two strings are already on main via #50.

## Findings and notes (file:line, severity)
1. MEDIUM, fixed in PR 106 (46288a7): the caller-signing tests spawned `sys._base_executable` (tools/tests/test_renew_token.py:57 PY); in the GX10 venv that is the system python without pydantic or httpx, so signing was unavailable. Now `SIGN_PY = sys.executable` for the signing runs. Runbook line added for deployments (C-245): docs/runbooks/token-renewal.md, section "Caller-signed ledger records (F2b): which python runs the tool".
2. LOW, PR 117, equivalent mutants: forcing either containment check in `guarded_manifest_path` (services/ops-console/src/ops_console/api.py L205-218, the first `resolve(strict=False)` check or the `real.is_relative_to(base)` one) alone survives, because `Path.resolve` follows symlinks and each subsumes the other. Both forced False goes red. Defence in depth, not changed.
3. LOW, PR 121: card C-212 says the token-record refusals exit 2; the code returns exit 1 ("malformed response") for a bad record from the token read (tools/renew_token.py `current_token`) and exit 2 only for a token of another agent. Tests pin the code. Also `decide()` prints "expired -0.0 days ago" at exactly 0 days left (cosmetic, tools/renew_token.py `decide`).
4. LOW, PR 128 (R-12 F-R12-2): re-provisioning never reconciles `domain` or `name` (services/lifecycle-manager/src/lifecycle_manager/engine.py, the 409 branch compares owner and manifest_ref only); pinned as today's behaviour.
5. Process lesson (mine): a `git checkout -- <file>` placed after a failed `cd` in a `;` chain reverted uncommitted work once; redone from the edit script, and the work is now committed before any mutation run.

## What I did not do
- No GX10 run of PR 121 on the rebased head: it is stacked on 106 and needs your rebase after 106 merges.
- Windows local runs skip the POSIX-only permission tests; the mutants for those (PR 113) were run on the GX10 in a scratch copy of the pushed head.
