#!/usr/bin/env bash
# Work dispatcher for the comms area (coordinator 2026-11-04, Don: no duplicates, no idle roles).
# One atomic lock per work target: a lock is a file on origin/comms, so two sessions that claim the same
# target write the SAME path and git rejects the second push. Nobody edits TASK-QUEUE.md to claim.
#   dispatch.sh next <role> <who>        claim the first unclaimed WORKLIST item for <role>; prints it; exit 3 = EMPTY
#   dispatch.sh done <role> <target> <note>   move the lock to comms/done/ (after the report is pushed)
#   dispatch.sh release <role> <target> <why> give the item back (deletes the lock; say why)
#   dispatch.sh report <who> <slug> <file>  push <file> as inbox/coordinator/<UTC>-<who>-<slug>.md (identity forced, retried on a rejected push)
#   dispatch.sh level                    unclaimed item count per role (RESTOCK when a role has fewer than LOW_WATER)
#   dispatch.sh identity                 print the identity this script commits with
# Roles: builder, reviewer, verifier.  WORKLIST.tsv columns: id TAB role TAB target TAB note.
# Lock key = <role>__<sanitised target>, so two items on one target can never both be taken.
# The script SETS the commit identity itself (it overrides a GIT_AUTHOR_NAME that the environment may carry; one
# such value leaked a personal address on public commits) and refuses to push unless all four fields match.
set -euo pipefail
export GIT_AUTHOR_NAME="Don Hagell" GIT_COMMITTER_NAME="Don Hagell"
export GIT_AUTHOR_EMAIL="13129187+dhagell@users.noreply.github.com" GIT_COMMITTER_EMAIL="13129187+dhagell@users.noreply.github.com"
REMOTE="${COMMS_REMOTE:-origin}"; LOW_WATER="${LOW_WATER:-6}"
REPO="$(git rev-parse --show-toplevel)"; WT="${COMMS_WT:-$REPO/../comms-wt-dispatch}"
cmd="${1:?next|done|release|report|level|identity}"; shift || true

REFN="refs/dispatch/$"   # a private ref per run: sessions share one repo, and fetching into the shared refs/remotes/origin/comms races ("incorrect old value")
trap 'git -C "$REPO" update-ref -d "$REFN" 2>/dev/null' EXIT
sync() {  # whole sequence retried: sessions share one repo and git ref/worktree locks collide under concurrency
  local i ok
  for i in 1 2 3 4 5 6 7 8; do
    ok=1
    git -C "$REPO" fetch -q "$REMOTE" "+refs/heads/comms:$REFN" </dev/null 2>/dev/null || ok=0
    [ "$ok" = 1 ] && { git -C "$REPO" rev-parse -q --verify "$REFN" >/dev/null || ok=0; }
    if [ "$ok" = 1 ] && [ ! -d "$WT" ]; then git -C "$REPO" worktree add -q --detach "$WT" "$REFN" </dev/null 2>/dev/null || ok=0; fi
    [ "$ok" = 1 ] && { git -C "$WT" checkout -q --detach "$REFN" </dev/null 2>/dev/null || ok=0; }
    [ "$ok" = 1 ] && break
    sleep $(( (RANDOM % 4) + 1 ))
  done
  [ "$ok" = 1 ] || { echo "could not sync comms after 8 tries (git lock contention); retry later" >&2; exit 2; }
  mkdir -p "$WT/comms/locks" "$WT/comms/done"
}
key() { printf '%s__%s' "$1" "$(printf '%s' "$2" | tr -c 'A-Za-z0-9._@#-' '_')"; }
taken() { [ -e "$WT/comms/locks/$1.lock" ] || [ -e "$WT/comms/done/$1.md" ]; }
push_retry() {  # after a local commit: retry a rejected push (fetch + rebase, jittered); exit 2 if it never lands, so a caller is never told "done" for an unpushed commit
  local i rc
  for i in 1 2 3 4 5 6 7 8 9 10; do
    push_ok; rc=$?
    [ "$rc" -eq 0 ] && return 0
    [ "$rc" -eq 2 ] && return 2
    sleep $(( (RANDOM % 4) + 1 ))
    git -C "$REPO" fetch -q "$REMOTE" "+refs/heads/comms:$REFN" </dev/null 2>/dev/null && git -C "$WT" rebase -q "$REFN" </dev/null 2>/dev/null || true
  done
  echo "push failed after retries: $1 is NOT recorded on $REMOTE/comms" >&2; return 2
}
push_ok() {
  local got want; got="$(git -C "$WT" log -1 --format='%an <%ae> | %cn <%ce>')"
  want="$GIT_AUTHOR_NAME <$GIT_AUTHOR_EMAIL> | $GIT_COMMITTER_NAME <$GIT_COMMITTER_EMAIL>"
  [ "$got" = "$want" ] || { echo "IDENTITY MISMATCH, not pushing: $got" >&2; return 2; }
  git -C "$WT" push -q "$REMOTE" HEAD:comms </dev/null 2>/dev/null
}

case "$cmd" in
  identity) echo "$GIT_AUTHOR_NAME <$GIT_AUTHOR_EMAIL>";;
  level)
    sync
    for r in builder reviewer verifier; do
      n=0
      while IFS=$'\t' read -r id role target note; do
        [ "$role" = "$r" ] || continue; taken "$(key "$role" "$target")" || n=$((n+1))
      done < <(grep -v '^#' "$WT/comms/WORKLIST.tsv" 2>/dev/null || true)
      s=OK; [ "$n" -lt "$LOW_WATER" ] && s="RESTOCK"
      echo "$r unclaimed=$n $s"
    done;;
  next)
    role="${1:?role}"; who="${2:?who}"
    for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
      [ "$attempt" -gt 1 ] && sleep $(( (RANDOM % 4) + 1 ))
      sync; got=""
      while IFS=$'\t' read -r id r target note; do
        [ "$r" = "$role" ] || continue
        k="$(key "$role" "$target")"; taken "$k" && continue
        printf 'Owner: %s\nItem: %s\nRole: %s\nTarget: %s\nClaimed: %s\n' "$who" "$id" "$role" "$target" "$(date -u +%Y-%m-%dT%H:%MZ)" > "$WT/comms/locks/$k.lock"
        git -C "$WT" add "comms/locks/$k.lock"
        git -C "$WT" commit -q -m "comms: $who claims $id ($role $target)" </dev/null
        if push_ok; then printf 'CLAIMED\t%s\t%s\t%s\t%s\n' "$id" "$role" "$target" "$note"; exit 0; fi
        got=retry; break
      done < <(grep -v '^#' "$WT/comms/WORKLIST.tsv" 2>/dev/null || true)
      [ "$got" = "retry" ] || { echo "EMPTY $role: no unclaimed item; run restock (see comms/ROLE-LOOP.md)"; exit 3; }
    done
    echo "could not claim after 12 tries (push contention); retry later" >&2; exit 2;;
  done)
    role="${1:?role}"; target="${2:?target}"; note="${3:-done}"; k="$(key "$role" "$target")"; sync
    [ -e "$WT/comms/locks/$k.lock" ] || { echo "no lock for $k" >&2; exit 1; }
    git -C "$WT" mv "comms/locks/$k.lock" "comms/done/$k.md"
    printf 'Done: %s\nNote: %s\n' "$(date -u +%Y-%m-%dT%H:%MZ)" "$note" >> "$WT/comms/done/$k.md"
    git -C "$WT" add -A comms; git -C "$WT" commit -q -m "comms: done $k" </dev/null; push_retry "done $k" && echo "done: $k";;
  report)
    who="${1:?who}"; slug="${2:?slug}"; src="${3:?file}"; [ -f "$src" ] || { echo "no file $src" >&2; exit 1; }
    for attempt in 1 2 3 4 5 6 7 8; do
      sync; dest="comms/inbox/coordinator/$(date -u +%Y%m%d-%H%M)-$who-$slug.md"; mkdir -p "$WT/comms/inbox/coordinator"; cp "$src" "$WT/$dest"
      git -C "$WT" add "$dest"; git -C "$WT" commit -q -m "comms: $who report $slug" </dev/null
      if push_ok; then echo "reported: $dest"; exit 0; fi; sleep $(( (RANDOM % 4) + 1 ))
    done; echo "could not push report" >&2; exit 2;;
  release)
    role="${1:?role}"; target="${2:?target}"; why="${3:?why}"; k="$(key "$role" "$target")"; sync
    git -C "$WT" rm -q "comms/locks/$k.lock"; git -C "$WT" commit -q -m "comms: release $k ($why)" </dev/null; push_retry "release $k" && echo "released: $k";;
  *) echo "usage: dispatch.sh next|done|release|level|identity" >&2; exit 64;;
esac
