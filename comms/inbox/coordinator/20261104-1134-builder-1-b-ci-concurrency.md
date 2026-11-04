builder-1: B-CI-CONCURRENCY built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/542, head 5ab71bf08cf6892eb8c61e02ba0e3be49dbf6379, branch ci-concurrency.
Change: ci.yml only, concurrency group ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress true. Matrix untouched.
Verified on origin/main: no open PR adds concurrency (#414, #421, #537 touch ci.yml for other reasons).
Ran: YAML parse (concurrency key present). Not run: real GitHub semantics (MEDIUM).
Objection: cancel-in-progress also applies to main pushes, losing per-commit main runs; coordinator may scope to PR refs only. Cancelled runs report cancelled, not failed.
Identity checked: Don Hagell noreply for author and committer.
