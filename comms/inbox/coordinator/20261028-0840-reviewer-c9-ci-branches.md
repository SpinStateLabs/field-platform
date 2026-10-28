# C-9: reviewer verdict (teammate-don-reviewer, 2026-10-28) - READ-ONLY, UNVERIFIED on GX10 (no tests run; config review)

Heads confirmed: ci/harden-workflows-2026-10-23 = 4331864, ci/topology-lint-2026-10-23 = fd59807 (git rev-parse on origin).

## Verdict: both PASS-as-content, but BOTH ARE ALREADY MERGED - do not rebase or merge the branches (HIGH)
- ci/harden-workflows-2026-10-23 -> squash-merged as PR #16 (2026-10-23T05:57:25Z). Behind main by 38, ahead by 1 (the pre-squash commit).
- ci/topology-lint-2026-10-23 -> squash-merged as PR #18 (2026-10-23T12:41:17Z, main 40f2a58). Behind 36, ahead 14 (pre-squash commits). Main has since moved (#38 ETXTBSY fix; tools/topology_lint.py exists on main). `git diff --stat origin/main origin/ci/topology-lint-2026-10-23 -- tools/topology_lint.py .github` shows the branch would REMOVE 261 lines from ci.yml and rewrite topology_lint.py: rebasing it would regress main. Treat as abandoned (merged-by-squash).

## Content check of the harden change (the CI security part), against origin/main .github/workflows/ci.yml - HIGH
- Top-level `permissions: contents: read` present on main.
- `persist-credentials: false` on every checkout; main's `uses:` lines are only the two SHA-pinned ones.
- Pins verified against the GitHub API: actions/checkout 11d5960a... is tagged v4 and v4.4.0; actions/setup-python a26af69b... is tagged v5 and v5.6.0 (the pinned commits really are those tags).
- ci.yml is the only workflow; triggers are push to main and pull_request (not pull_request_target), so fork PRs get a read-only token.

## Residual (LOW/MEDIUM, on main, not caused by these branches)
- LOW: `pip install fastapi uvicorn httpx pytest` in ci.yml is unpinned (supply-chain drift; also explains the httpx2 deprecation warning). Pin or use a constraints file.
- LOW: `pip install --upgrade pip` unpinned in the same step.
- I do not know whether branch protection requires the CI checks or independent review on main (not visible in the repo).
