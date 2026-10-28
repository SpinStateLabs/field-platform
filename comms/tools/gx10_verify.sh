#!/usr/bin/env bash
# gx10_verify.sh - run the CI test set of SpinStateLabs/field-platform for ONE git ref on the GX10.
# Author: reviewer (R-21). Runs ON the GX10. Read-only toward ~/field-platform; never touches a DB port,
# Postgres, a running estate, or any secret. Everything lives in its own work tree.
#
# usage:
#   gx10_verify.sh --name NAME --bundle /tmp/x.bundle --ref REFNAME [--base SHA_OR_REF] [--quick] [--foreground]
#   gx10_verify.sh --name NAME --repo ~/ff-work/wt-fieldrev-67 --ref SHA       # fetch from a local clone
#
# --name NAME     work tree ~/ff-work/wt-NAME-verify, logs ~/ff-work/NAME-verify/*.log, marker NAME-verify/.done
# --bundle FILE   git bundle (made on the Windows side: git bundle create x.bundle BASE..REF) holding REF
# --repo DIR      alternative: an existing clone to fetch REF from
# --ref REF       branch or sha to test (in the bundle: the ref name the bundle carries)
# --base REF      a commit already in the seed clone (default: origin's main in the seed clone, ~/ff-work/wt-fieldrev-80b)
# --quick         skip tools/tests (8.5 min); field-core, services and field-agent still run
# --foreground    do not detach (default: detached with nohup, poll the .done marker)
#
# The set mirrors .github/workflows/ci.yml `tests` job (checked against main 444e49b):
#   1. pytest -q packages/field-core/tests services/sealed-ledger/tests services/delegation-authority/tests
#                services/spend-governor/tests services/kill-switch/tests services/federation-broker/tests   (one run, repo root)
#   2. pytest -q tools/tests
#   3. per service, cwd = service: agent-registry conformance-sentinel incident-replay compliance-crosswalk force-gateway
#                lifecycle-manager attestation-reporter ops-console claude-approver  (python -m pytest -q tests)
#   4. packages/field-agent: python -m pytest -q tests
#   5. python tools/topology_lint.py   (needs no docker)
# Not run here (CI-only, need docker/compose): compose-smoke, fly-image-smoke, compose-upgrade-smoke.
# defence-shield/agent-incident-retro is NOT in CI (F-C141-1); it runs here as an extra step 6 and its result is
# reported separately ("EXTRA") so it never hides in the CI-equivalent verdict.
set -u
ORIG_ARGS=("$@")
NAME=""; BUNDLE=""; REPO=""; REF=""; BASE=""; QUICK=0; FG=0
while [ $# -gt 0 ]; do case "$1" in
  --name) NAME=$2; shift 2;; --bundle) BUNDLE=$2; shift 2;; --repo) REPO=$2; shift 2;; --ref) REF=$2; shift 2;;
  --base) BASE=$2; shift 2;; --quick) QUICK=1; shift;; --foreground) FG=1; shift;;
  *) echo "unknown arg $1" >&2; exit 2;; esac; done
[ -n "$NAME" ] && [ -n "$REF" ] || { echo "need --name and --ref" >&2; exit 2; }
case "$NAME" in *[!A-Za-z0-9._-]*) echo "bad --name" >&2; exit 2;; esac
ROOT=$HOME/ff-work; WT=$ROOT/wt-$NAME-verify; OUT=$ROOT/$NAME-verify; SEED=${GX10_VERIFY_SEED:-$ROOT/wt-fieldrev-80b}
VENV=${GX10_VERIFY_VENV:-$ROOT/venv-fieldrev}
# refuse to touch anything outside ~/ff-work, never the live checkouts
case "$WT" in "$ROOT"/wt-*-verify) ;; *) echo "refusing work tree $WT" >&2; exit 2;; esac
mkdir -p "$OUT"
if [ "$FG" = 0 ] && [ -z "${GX10_VERIFY_CHILD:-}" ]; then
  rm -f "$OUT/.done" "$OUT/summary.txt"
  GX10_VERIFY_CHILD=1 nohup "$0" "${ORIG_ARGS[@]}" --foreground > "$OUT/driver.log" 2>&1 &
  echo "started pid $! ; logs $OUT ; poll: test -f $OUT/.done && cat $OUT/summary.txt"; exit 0
fi
rm -f "$OUT/.done" "$OUT/summary.txt"
log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$OUT/driver.log"; }
# ---- 1. work tree: fresh clone of the seed, then fetch the ref
rm -rf "$WT"; git clone -q "$SEED" "$WT" 2>>"$OUT/driver.log" || { log "seed clone failed ($SEED)"; echo "FAIL setup" > "$OUT/summary.txt"; touch "$OUT/.done"; exit 1; }
cd "$WT" || exit 1
if [ -n "$BUNDLE" ]; then git fetch -q "$BUNDLE" "$REF:verify-ref" 2>>"$OUT/driver.log" || { log "bundle fetch failed"; echo "FAIL setup" > "$OUT/summary.txt"; touch "$OUT/.done"; exit 1; }; TARGET=verify-ref
elif [ -n "$REPO" ]; then git fetch -q "$REPO" "$REF" 2>>"$OUT/driver.log" && TARGET=FETCH_HEAD || TARGET=$REF
else TARGET=$REF; fi
git checkout -q -f "$TARGET" 2>>"$OUT/driver.log" || { log "checkout $TARGET failed"; echo "FAIL setup" > "$OUT/summary.txt"; touch "$OUT/.done"; exit 1; }
HEAD_SHA=$(git rev-parse HEAD); log "head $HEAD_SHA ($NAME)"
[ -n "$BASE" ] && { log "merge-base with $BASE: $(git merge-base HEAD "$BASE" 2>/dev/null | cut -c1-12)"; log "files vs base: $(git diff --stat "$BASE" HEAD 2>/dev/null | tail -1)"; }
# ---- 2. environment (no secrets, no DB ports, no estate)
# shellcheck disable=SC1091
. "$VENV/bin/activate" || { log "venv $VENV missing"; echo "FAIL setup" > "$OUT/summary.txt"; touch "$OUT/.done"; exit 1; }
export CI=true; unset FIELD_SHARED_SECRET FIELD_OPERATOR_KEY FIELD_OPERATOR_REGISTRY FIELD_OPERATOR_REQUIRE ANTHROPIC_API_KEY
export PYTHONPATH=$WT/packages/field-core/src:$WT/packages/field-agent/src
for s in "$WT"/services/*/src; do PYTHONPATH=$PYTHONPATH:$s; done; export PYTHONPATH
# ---- 3. the steps
declare -A RES; ORDER=()
step() { local id=$1; shift; local lf=$OUT/$id.log; ORDER+=("$id"); log "RUN  $id"; ( "$@" ) > "$lf" 2>&1; local rc=$?; RES[$id]=$rc; local tail1; tail1=$(grep -E "passed|failed|error" "$lf" | tail -1); log "DONE $id rc=$rc  ${tail1}"; }
step core_services bash -c 'cd "$0" && pytest -q packages/field-core/tests services/sealed-ledger/tests services/delegation-authority/tests services/spend-governor/tests services/kill-switch/tests services/federation-broker/tests' "$WT"
[ "$QUICK" = 1 ] && log "SKIP tools (--quick)" || step tools bash -c 'cd "$0" && pytest -q tools/tests' "$WT"
for s in agent-registry conformance-sentinel incident-replay compliance-crosswalk force-gateway lifecycle-manager attestation-reporter ops-console claude-approver; do
  step "svc_$s" bash -c 'cd "$0/services/$1" && python -m pytest -q tests' "$WT" "$s"; done
step field_agent bash -c 'cd "$0/packages/field-agent" && python -m pytest -q tests' "$WT"
step topology_lint bash -c 'cd "$0" && python tools/topology_lint.py' "$WT"
step EXTRA_defence_shield bash -c 'cd "$0/defence-shield/agent-incident-retro" && PYTHONPATH="$0/defence-shield/agent-incident-retro/src:$PYTHONPATH" python -m pytest -q tests' "$WT"
# ---- 4. verdict: CI-equivalent steps decide; EXTRA is reported, not decisive
FAIL=0; { echo "head $HEAD_SHA name $NAME"; echo "date $(date -u +%FT%TZ)"; for id in "${ORDER[@]}"; do
  rc=${RES[$id]}; case "$id" in EXTRA_*) tag=EXTRA;; *) tag=CI;; esac
  last=$(grep -E "passed|failed|error|OK|FAIL" "$OUT/$id.log" | tail -1)
  echo "$tag $id rc=$rc  $last"; [ "$tag" = CI ] && [ "$rc" != 0 ] && FAIL=1; done
  [ "$QUICK" = 1 ] && echo "NOTE tools/tests skipped (--quick): not a full CI-equivalent run"
  [ $FAIL = 0 ] && echo "VERDICT CI-EQUIVALENT STEPS GREEN" || echo "VERDICT RED (see logs)"; } > "$OUT/summary.txt"
cat "$OUT/summary.txt" | tee -a "$OUT/driver.log"
touch "$OUT/.done"; exit $FAIL