#!/usr/bin/env bash
# Sandbox-side client of the outbox. A Managed Agent session on the GB10 sandbox has NO GitHub credential and NO
# route to the host; it asks a trusted pusher (outside the sandbox) to act. The pusher validates every request, forces
# the Don Hagell noreply identity checks, and answers through /workspace/outbox/responses. Nothing here pushes.
#   outbox.sh next <role>                      claim the next unclaimed WORKLIST item (same as dispatch.sh next)
#   outbox.sh level                            unclaimed counts per role
#   outbox.sh done <role> <target> <note>      mark an item done
#   outbox.sh release <role> <target> <why>    give an item back
#   outbox.sh report <slug> <file>             publish <file> as inbox/coordinator/<UTC>-<you>-<slug>.md
#   outbox.sh push_branch <branch>             publish the branch of your clone at /workspace/repo (no force, never main/comms)
#   outbox.sh open_pr <branch> <title> <file>  open a DRAFT pull request against main, body from <file>
# Env: OUTBOX_WHO (your session name; default ANTHROPIC_SESSION_ID), OUTBOX_TIMEOUT seconds (default 600).
# Exit codes: the pusher's; 75 = no answer in time (the pusher may be down; the request stays queued).
set -euo pipefail
OB="${OUTBOX_DIR:-/workspace/outbox}"; WHO="${OUTBOX_WHO:-${ANTHROPIC_SESSION_ID:-unknown}}"; TIMEOUT="${OUTBOX_TIMEOUT:-600}"
mkdir -p "$OB/requests" "$OB/responses" "$OB/files"
op="${1:?op: next|level|done|release|report|push_branch|open_pr}"; shift || true
id="$(date -u +%Y%m%dT%H%M%S)-$$-$RANDOM"
python3 - "$OB" "$id" "$WHO" "$op" "$@" <<'PY'
import json, os, shutil, sys
ob, id_, who, op, *args = sys.argv[1:]
files = []
fidx = {"report": 1, "open_pr": 2}.get(op)
if fidx is not None and len(args) > fidx and os.path.isfile(args[fidx]):
    dst = f"{ob}/files/{id_}.0"
    shutil.copyfile(args[fidx], dst)
    files.append(dst)
    args[fidx] = dst
tmp = f"{ob}/requests/.{id_}.tmp"
with open(tmp, "w") as f:
    json.dump({"id": id_, "who": who, "op": op, "args": args, "files": files}, f)
os.rename(tmp, f"{ob}/requests/{id_}.json")
PY
end=$(( $(date +%s) + TIMEOUT ))
while [ "$(date +%s)" -lt "$end" ]; do
  if [ -f "$OB/responses/$id.json" ]; then
    python3 - "$OB/responses/$id.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
sys.stdout.write(r.get("stdout", ""))
sys.stderr.write(r.get("stderr", ""))
sys.exit(int(r.get("exit", 1)))
PY
    exit $?
  fi
  sleep 3
done
echo "outbox: no answer within ${TIMEOUT}s (the pusher may be down); request $id stays queued" >&2
exit 75
