#!/usr/bin/env bash
# C-74: SECOND delete-list for remote branches of SpinStateLabs/field-platform (the six heads the D-15 run left that are not live).
# AUTHOR: teammate-don-reviewer, 2026-10-28. NOT RUN by the author. For DON'S APPROVAL; the coordinator runs it, never the reviewer.
# Same safety rules as the C-63 script: dry-run by default (DRY=0 to execute); each branch is deleted only if its remote tip STILL equals the
# sha recorded here; main, comms and the live branches are refused. Excluded on purpose (live): feat/machine-verifier-identity (#55),
# feat/alerts-ntfy (#56), feat/kr-r4a-rotator-core (#57), fix/renew-token-signed.
# Recovery: git push origin <sha>:refs/heads/<branch> (shas below); for PR heads refs/pull/<n>/head also stays on GitHub.
set -euo pipefail
REMOTE="${REMOTE:-origin}"; DRY="${DRY:-1}"
PROTECTED="main comms feat/machine-verifier-identity feat/alerts-ntfy feat/kr-r4a-rotator-core fix/renew-token-signed"
deleted=0; skipped=0
del() {  # del <branch> <recorded-tip-sha>
  local b="$1" want="$2"
  for p in $PROTECTED; do [ "$b" = "$p" ] && { echo "REFUSE protected: $b"; return 1; }; done
  local got; got="$(git ls-remote --heads "$REMOTE" "refs/heads/$b" | cut -f1)"
  if [ -z "$got" ]; then echo "ABSENT  $b (already deleted)"; skipped=$((skipped+1)); return 0; fi
  if [ "$got" != "$want" ]; then echo "MOVED   $b tip is $got, recorded $want: SKIPPED"; skipped=$((skipped+1)); return 0; fi
  if [ "$DRY" = "0" ]; then git push "$REMOTE" --delete "$b" && deleted=$((deleted+1)); else echo "DRY     git push $REMOTE --delete $b   # tip $want"; fi
}

# #16 MERGED 2026-10-23, tip = PR head 4331864 (squash); C-9
del 'ci/harden-workflows-2026-10-23' 4331864a5dbc27cbf4bd27e673aa9db4a7ae5f17
# #18 MERGED 2026-10-23, tip = PR head fd59807 (squash); C-9; do NOT rebase (would regress main)
del 'ci/topology-lint-2026-10-23' fd5980785b6dd3752f8e561a8dfe30159759949c
# #28 MERGED 2026-10-25, tip = PR head fb80a31 (squash 1c14b52); C-39
del 'feat/phase-g-check-tool' fb80a317e0d86a1302d7bfba455769c9d250d6fb
# #35 MERGED 2026-10-26, tip = PR head 9f1f4ee (squash 8628814); C-59
del 'feat/claude-approver-v0' 9f1f4ee2b33eaf83a4c7a3927f655d3c08d8a9bc
# #1 MERGED 2026-09-12, tip = PR head bab3d91; tip is an ANCESTOR of main (git merge-base --is-ancestor true), 0 commits only on the branch; main commit 1727de0
del 'claude/field-gate-v1-1-integration-7u50hv' bab3d91ac082d6e2928b2b9bd946c0114d2c0c1c
# no PR; tip df774fe is an ANCESTOR of main (git merge-base --is-ancestor true), 0 commits only on the branch (138 behind / 0 ahead); docs(state) commit, content in main
del 'claude/state-field-gate-1-1-0' df774fee1e05486005752b9ca35abbfd584b044d

echo "done: deleted=$deleted skipped=$skipped (DRY=$DRY)"
