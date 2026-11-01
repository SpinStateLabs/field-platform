# Builder Lane 16: PR 414 GX10 full set on 2e066b77 (vulture on PYTHONPATH), plus one incident to report

## GX10 full run, PR 414 head 2e066b77e63181b5700f39d3f8c56a1935c298f1 (answers Q-68 condition C1, with the caveat below)
Method: the PR head fetched as refs/pull/414/head and checked equal to the PR head before the run; CI-order runner (copy of the C-774 batch script), CI=true, the usual venv, and vulture 2.16 made importable by putting a separate venv's site-packages on PYTHONPATH. The shared GX10 test venv itself was NOT changed, so the coordinator's ruling on vulture in ~/ff-work/venv-fp (F-Q66-3) is still needed for a plain verifier run.

| Suite | Result |
|---|---|
| core + sealed-ledger | 1924 passed, 4 skipped |
| tools | 3279 passed, 4 skipped (includes the 24 vulture gate tests, which fail closed under CI=true if vulture is missing) |
| field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353 (5 skipped); conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242 | all passed, 0 failed |
| field-mcp | not applicable: this head has no services/field-mcp (the batch script printed a heading and no line) |

HIGH confidence for the numbers (read from the run log). Not covered: Python 3.11, 3.12, 3.14 on the GX10 (CI is 7/7 on this head), PR 421's rebase (F-Q66-4), the PR description wording (Lane 1).

## Incident: I deleted GX10 verifier B's worktree by mistake
While setting up this run I ran `rm -rf ~/ff-work/wt-pr414b` assuming the name was free; it was verifier B's worktree for its earlier PR 414 run (branch pr414b, with pr414b.start and pr414b-tools-rerun.log beside it). My `git fetch` into that branch had already refused ("checked out at"); I read it after the delete. I recreated a clean checkout of branch pr414b at the same commit (38bc0f6) and messaged verifier B. Lost: anything uncommitted or untracked inside that worktree (unknown what). Not touched: its logs and its report. My run used its own names (wt-l16pr414, l16-pr414-head, l16-runbatch-pr414.sh) and I have saved a rule to use l16-prefixed names and check ownership before any delete on the shared GX10.
