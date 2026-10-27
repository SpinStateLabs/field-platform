#!/bin/bash
# FIELD Platform — single-container supervisor for the Fly.io sandbox estate.
#
# Mirrors integration/demo/docker-compose.yml (the ground truth for service
# commands and ports): same thirteen-service estate, same `<cli> serve` commands,
# but every service binds 127.0.0.1 inside this one container. Caddy (:8080,
# /etc/caddy/Caddyfile) is the only 0.0.0.0 listener. Keep the commands below
# in sync with the compose file.
#
# This is the PRODUCT estate: sentinel defaults to ENFORCE. (The GB10 also runs
# enforce since the 2026-09-08 cutover, set in docker-compose.gb10.yml.)
set -eu

export FIELD_DATA_DIR="${FIELD_DATA_DIR:-/data}"
mkdir -p "$FIELD_DATA_DIR"

# Fly stops a Machine by sending SIGTERM to PID 1. A bash PID 1 with no trap
# IGNORES SIGTERM (kernel rule: init gets no default-action signals), so
# without this every stop/deploy would hang for kill_timeout and end in
# SIGKILL of every child — including the ledger mid-write. Trap it: forward
# TERM to all children (from PID 1, `kill -1` signals everyone else in the
# PID namespace), let uvicorn/caddy shut down, then exit 0 — a commanded
# stop is not a crash and must not read as one.
shutdown() {
    echo "entrypoint: stop signal received — terminating the estate" >&2
    kill -s TERM -- -1 2>/dev/null || true
    wait || true
    exit 0
}
trap shutdown TERM INT

# Compose points these at service DNS names; here everything is loopback.
# These exports are BEHAVIOR, not decoration: e.g. `forcegw serve` only wires
# its governor and ledger clients when FIELD_GOVERNOR_URL / FIELD_LEDGER_URL
# are set (services/force-gateway/src/force_gateway/cli.py), and the sentinel
# reaches its peers through these URLs.
export FIELD_REGISTRY_URL="${FIELD_REGISTRY_URL:-http://127.0.0.1:8001}"
export FIELD_LEDGER_URL="${FIELD_LEDGER_URL:-http://127.0.0.1:8002}"
export FIELD_DELEGATION_URL="${FIELD_DELEGATION_URL:-http://127.0.0.1:8003}"
export FIELD_SENTINEL_URL="${FIELD_SENTINEL_URL:-http://127.0.0.1:8004}"
export FIELD_KILLSWITCH_URL="${FIELD_KILLSWITCH_URL:-http://127.0.0.1:8005}"
export FIELD_GOVERNOR_URL="${FIELD_GOVERNOR_URL:-http://127.0.0.1:8006}"
export FIELD_REPLAY_URL="${FIELD_REPLAY_URL:-http://127.0.0.1:8007}"
export FIELD_CROSSWALK_URL="${FIELD_CROSSWALK_URL:-http://127.0.0.1:8008}"
export FIELD_GATEWAY_URL="${FIELD_GATEWAY_URL:-http://127.0.0.1:8009}"
# v1.2 D2e: the platform's own LLM calls (sentinel judge, crosswalk suggester, gateway
# hygiene judge) go through forcegw as x-force-passthrough: judge. FIELD_GATEWAY_URL above
# is the forcegw CLI target; the gateway's own upstream never reads FORCE_GATEWAY_URL.
export FORCE_GATEWAY_URL="${FORCE_GATEWAY_URL:-http://127.0.0.1:8009}"
export FIELD_FEDERATION_URL="${FIELD_FEDERATION_URL:-http://127.0.0.1:8010}"
export FIELD_LIFECYCLE_URL="${FIELD_LIFECYCLE_URL:-http://127.0.0.1:8012}"
export FIELD_ATTEST_URL="${FIELD_ATTEST_URL:-http://127.0.0.1:8013}"

# Operator passthroughs — same names and defaults as the compose x-service
# env (v1.2 A0). Blank/default unless set via `fly secrets set` or [env].
# FIELD_LIFECYCLE_EVERY arms the lifecycle scheduler daily here too; with no
# roster file a tick is recorded as skipped (last_tick.json, never over
# last_sweep.json). FIELD_CROSSWALK_EVERY is read by `crosswalk serve` (--every):
# a live https regwatch check of the cited regulatory pages every N seconds
# (default daily; 0 = off). Daily egress from this estate was decided by Don
# Hagell on 2026-09-13 (D4), so the default stays 86400.
export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-}"
export FIELD_LIFECYCLE_ROSTER="${FIELD_LIFECYCLE_ROSTER:-}"
export FIELD_LIFECYCLE_EVERY="${FIELD_LIFECYCLE_EVERY:-86400}"
export FIELD_CROSSWALK_EVERY="${FIELD_CROSSWALK_EVERY:-86400}"
export FIELD_KILL_ENDPOINT_ALLOWLIST="${FIELD_KILL_ENDPOINT_ALLOWLIST:-}"
export FIELD_LEDGER_RETENTION_DAYS="${FIELD_LEDGER_RETENTION_DAYS:-2555}"
# C2: the rotation signing key (PEM path under /data) stays unset until A4
# places it (POST /rotate answers 503 until then); a blank archive dir means
# $FIELD_DATA_DIR/ledger-archive.
export FIELD_LEDGER_ANCHOR_KEY="${FIELD_LEDGER_ANCHOR_KEY:-}"
# F2: the per-event signing key (a SEPARATE PEM path under /data,
# /data/keys/ledger-sign.pem at A7) and the fail-closed flag (A9). Unset / 0
# = unsigned appends and /ledger/health signing: off — the pre-F2 behaviour.
export FIELD_LEDGER_SIGN_KEY="${FIELD_LEDGER_SIGN_KEY:-}"
export FIELD_LEDGER_REQUIRE_SIGNING="${FIELD_LEDGER_REQUIRE_SIGNING:-0}"
# F2b caller authorship is NOT deployed on this estate (one container: every
# process can read every key, so a per-service key proves nothing — the (b)
# row). Blank / 0 = off; the names exist so an operator cannot arm it by accident.
export FIELD_LEDGER_CALLER_KEYRING="${FIELD_LEDGER_CALLER_KEYRING:-}"
export FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE="${FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE:-0}"
export FIELD_LEDGER_ARCHIVE_DIR="${FIELD_LEDGER_ARCHIVE_DIR:-}"
# F4 (A8): served attestation signing — the D10 signer name and the PEM path of
# the attest-sign key (/data/keys/attest-sign.pem here: one container, so every
# process in it can read the key — attestation-reporter README LIMITS). Both
# unset until A8 => served packs are UNSIGNED drafts; only `attest serve` reads them.
export FIELD_ATTEST_SIGNER="${FIELD_ATTEST_SIGNER:-}"
export FIELD_ATTEST_SIGN_KEY="${FIELD_ATTEST_SIGN_KEY:-}"
export FIELD_MANIFEST_DIR="${FIELD_MANIFEST_DIR:-/data/manifests}"
export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-}"
# Phase G operator authentication. Both OFF unless a `fly secrets set` places them
# (never fly.toml [env]): FIELD_OPERATOR_REGISTRY=/data/operators/operators.json
# (LOG-ONLY), FIELD_OPERATOR_REQUIRE=1 (ENFORCE). Blank is the same as unset to
# field_core.operator_auth.mode(). Runbook section 7. Per-process identities: C-5 below.
export FIELD_OPERATOR_REGISTRY="${FIELD_OPERATOR_REGISTRY:-}"
export FIELD_OPERATOR_REQUIRE="${FIELD_OPERATOR_REQUIRE:-}"
# force-gateway telemetry (v1.2 D2): count-based last_N rate window and rows kept.
export FORCE_TELEMETRY_WINDOW="${FORCE_TELEMETRY_WINDOW:-50}"
export FORCE_TELEMETRY_RETAIN="${FORCE_TELEMETRY_RETAIN:-10000}"
# F1 egress posture (A10/A11). Default 0 = observer. Self-agent token ids come from
# `fly secrets set FIELD_SENTINEL_SELF_TOKEN=... FIELD_GATEWAY_SELF_TOKEN=... FIELD_CROSSWALK_SELF_TOKEN=...`
# and are set PER PROCESS below (one container, three identities — never exported estate-wide).
# The sentinel timeout must exceed the sentinel's per-check budget (22 s structural;
# a judge-on sentinel needs 60 — the A12 precondition).
export FORCE_GATEWAY_ENFORCE="${FORCE_GATEWAY_ENFORCE:-0}"
export FORCE_GATEWAY_TOOL_CHECK="${FORCE_GATEWAY_TOOL_CHECK:-0}"
export FORCE_GATEWAY_SENTINEL_TIMEOUT="${FORCE_GATEWAY_SENTINEL_TIMEOUT:-30}"

# Product estate enforces; respect an explicit override from the environment.
export FIELD_SENTINEL_MODE="${FIELD_SENTINEL_MODE:-enforce}"

# Phase G C-5: per-PROCESS operator identity (REQUIRE design v0.4 section 2.5 "Fly",
# D-M). One machine has one environment, so an identity exported here would be
# presented by all thirteen processes, the console included. Instead:
# * FIELD_OPERATOR, FIELD_OPERATOR_KEY and FIELD_OPERATOR_KEY_FILE must NOT be set
#   machine-wide (a Fly secret or [env]): the estate refuses to start if one is.
# * The four identity-bearing daemons (design 2.2.1: svc-killswitch, svc-registry,
#   svc-delegation, svc-lifecycle) get their key from their OWN Fly secret,
#   FIELD_OPERATOR_KEY_KILLSWITCH / _REGISTRY / _DELEGATION / _LIFECYCLE. Each key is
#   written to $fly_key_dir/svc-<name>.key, created 0600 (umask 077) in a directory
#   created 0700, never on the volume, and only that daemon's launch block below
#   gets FIELD_OPERATOR=svc-<name> and FIELD_OPERATOR_KEY_FILE=<that path>. Paths
#   only: no key reaches any argv (printf is a builtin), log line or service
#   environment (each secret is blanked once every file is written).
# * All four secrets or none. None (today): no file, no directory, no new
#   environment variable, the same command lines and output; the one difference is
#   the four launch blocks' waiting subshells (each daemon becomes a grandchild of
#   the entrypoint, and TERM reaches it through fly_wait_service). A partial set, or a secret
#   that is empty or not a single key token, stops the estate BEFORE any service
#   starts and before any file is written, naming the secret and never its value:
#   a daemon that silently started unidentified would turn every kill into a 502
#   under REQUIRE (and the supervisor below takes the machine down for any one
#   service anyway).
# * An existing key file (a container restarted with its filesystem) is truncated
#   and rewritten, so it keeps the 0600 it was created with; the entrypoint never
#   creates it any other way. tools/fly_identity_check.py verifies 0600/0700 in the
#   running machine.
# FIELD_FLY_KEY_DIR moves the directory for tests only; nothing on Fly sets it.
fly_key_dir="${FIELD_FLY_KEY_DIR:-/run/field/keys}"
fly_refuse() {
    echo "entrypoint: REFUSING TO START (Phase G C-5): $1" >&2
    exit 1
}
fly_machine_wide() {  # NAME VALUE
    case "$2" in
        *[![:space:]]*) fly_refuse "$1 is set machine-wide; an operator identity is per process on Fly (FIELD_OPERATOR_KEY_<SVC> secrets). Run: fly secrets unset $1" ;;
    esac
}
fly_machine_wide FIELD_OPERATOR "${FIELD_OPERATOR-}"
fly_machine_wide FIELD_OPERATOR_KEY "${FIELD_OPERATOR_KEY-}"
fly_machine_wide FIELD_OPERATOR_KEY_FILE "${FIELD_OPERATOR_KEY_FILE-}"
fly_ids_missing=""
fly_ids_set=0
if [ -n "${FIELD_OPERATOR_KEY_KILLSWITCH+set}" ]; then fly_ids_set=$((fly_ids_set + 1)); else fly_ids_missing="$fly_ids_missing FIELD_OPERATOR_KEY_KILLSWITCH"; fi
if [ -n "${FIELD_OPERATOR_KEY_REGISTRY+set}" ]; then fly_ids_set=$((fly_ids_set + 1)); else fly_ids_missing="$fly_ids_missing FIELD_OPERATOR_KEY_REGISTRY"; fi
if [ -n "${FIELD_OPERATOR_KEY_DELEGATION+set}" ]; then fly_ids_set=$((fly_ids_set + 1)); else fly_ids_missing="$fly_ids_missing FIELD_OPERATOR_KEY_DELEGATION"; fi
if [ -n "${FIELD_OPERATOR_KEY_LIFECYCLE+set}" ]; then fly_ids_set=$((fly_ids_set + 1)); else fly_ids_missing="$fly_ids_missing FIELD_OPERATOR_KEY_LIFECYCLE"; fi
if [ "$fly_ids_set" -ne 0 ] && [ "$fly_ids_set" -ne 4 ]; then
    fly_refuse "only $fly_ids_set of the four per-process identity secrets are set (missing:$fly_ids_missing); set all four or none"
fi
fly_key_check() {  # SECRET_NAME VALUE : the same rule as field_core's key-file reader; never prints VALUE
    [ -n "$2" ] || fly_refuse "$1 is set but empty"
    case "$2" in
        *[!A-Za-z0-9._~+/=-]*) fly_refuse "$1 is not a single key token (whitespace or a character outside A-Za-z0-9._~+/=-)" ;;
    esac
    [ "${#2}" -le 256 ] || fly_refuse "$1 is longer than 256 characters"
}
fly_key_write() {  # OPERATOR_ID SECRET_NAME VALUE : writes the key file, created 0600; never prints VALUE
    ( umask 077 && printf '%s\n' "$3" > "$fly_key_dir/$1.key" ) || fly_refuse "cannot write $fly_key_dir/$1.key for $2"
    [ -s "$fly_key_dir/$1.key" ] || fly_refuse "$fly_key_dir/$1.key for $2 is empty after writing"
}
# Run inside a launch block's own subshell: gives THAT process its identity (paths only).
fly_identity_env() {  # OPERATOR_ID KEY_FILE ; an empty KEY_FILE (no identity secrets) does nothing
    if [ -n "$2" ]; then
        export FIELD_OPERATOR="$1" FIELD_OPERATOR_KEY_FILE="$2"
    fi
}
# The rest of a launch block's subshell: wait for its one service and pass on its
# exit. On TERM/INT (shutdown() signals every process) keep waiting, so PID 1's
# `wait` still lasts until that service has shut down, as it did before C-5.
fly_wait_service() {  # PID
    fly_service_pid="$1"
    trap 'wait "$fly_service_pid"; exit $?' TERM INT
    wait "$fly_service_pid"
}
fly_kf_killswitch=""
fly_kf_registry=""
fly_kf_delegation=""
fly_kf_lifecycle=""
if [ "$fly_ids_set" -eq 4 ]; then
    fly_key_check FIELD_OPERATOR_KEY_KILLSWITCH "$FIELD_OPERATOR_KEY_KILLSWITCH"
    fly_key_check FIELD_OPERATOR_KEY_REGISTRY "$FIELD_OPERATOR_KEY_REGISTRY"
    fly_key_check FIELD_OPERATOR_KEY_DELEGATION "$FIELD_OPERATOR_KEY_DELEGATION"
    fly_key_check FIELD_OPERATOR_KEY_LIFECYCLE "$FIELD_OPERATOR_KEY_LIFECYCLE"
    ( umask 077 && mkdir -p "$fly_key_dir" ) || fly_refuse "cannot create $fly_key_dir"
    fly_key_write svc-killswitch FIELD_OPERATOR_KEY_KILLSWITCH "$FIELD_OPERATOR_KEY_KILLSWITCH"
    fly_key_write svc-registry FIELD_OPERATOR_KEY_REGISTRY "$FIELD_OPERATOR_KEY_REGISTRY"
    fly_key_write svc-delegation FIELD_OPERATOR_KEY_DELEGATION "$FIELD_OPERATOR_KEY_DELEGATION"
    fly_key_write svc-lifecycle FIELD_OPERATOR_KEY_LIFECYCLE "$FIELD_OPERATOR_KEY_LIFECYCLE"
    fly_kf_killswitch="$fly_key_dir/svc-killswitch.key"
    fly_kf_registry="$fly_key_dir/svc-registry.key"
    fly_kf_delegation="$fly_key_dir/svc-delegation.key"
    fly_kf_lifecycle="$fly_key_dir/svc-lifecycle.key"
    # Blank the shell variables so no service's environment carries a key (each
    # daemon gets only its path). This does NOT erase them from this entrypoint's
    # own initial environment block: they stay readable as root in
    # /proc/<entrypoint pid>/environ and the four launch subshells' environ (and in
    # every `fly ssh console` session), as readable as the 0600 files themselves:
    # the declared Fly (b) row, not a secret boundary inside the machine.
    FIELD_OPERATOR_KEY_KILLSWITCH=""
    FIELD_OPERATOR_KEY_REGISTRY=""
    FIELD_OPERATOR_KEY_DELEGATION=""
    FIELD_OPERATOR_KEY_LIFECYCLE=""
    echo "entrypoint: Phase G C-5: per-process identities svc-killswitch, svc-registry, svc-delegation, svc-lifecycle (key files under $fly_key_dir)" >&2
fi
# The operators file on Fly lives in a DIRECTORY on the volume (/data/operators/,
# 0700; file 0600), edited only by writing a temp file in that directory and
# `mv -f` onto operators.json: the services open the path on every request, so the
# rename is seen at once and no request reads a half-written file. Absent file:
# the services start anyway (a refused start would stop the kill-switch too);
# LOG-ONLY records registry_unavailable, ENFORCE answers 503 on every guarded
# write, and /health shows last_registry_error. Said here once, loudly.
if [ -n "${FIELD_OPERATOR_REGISTRY// /}" ] && [ ! -f "$FIELD_OPERATOR_REGISTRY" ]; then
    echo "entrypoint: WARNING (Phase G): FIELD_OPERATOR_REGISTRY names $FIELD_OPERATOR_REGISTRY, which is not a file; guarded writes are unattributed (LOG-ONLY) or refused with 503 (ENFORCE) until it is installed" >&2
fi

# C-5 launch blocks (registry, delegation, killswitch, lifecycle): the subshell takes
# the identity (or nothing, with no identity secrets) and starts the UNCHANGED
# `<service> serve` line, then waits for that one service (fly_wait_service), so the
# supervisor's `wait -n` still sees the service exit, `kill -1` still reaches it, and
# shutdown() still waits for it.
( fly_identity_env svc-registry "$fly_kf_registry"
registry serve --host 127.0.0.1 --port 8001 &
fly_wait_service "$!" ) &
# Phase G C-6: the ledger's own operator observer, set for the ledger process only.
# One tick reads its own /health operator block in process, then one header-less
# GET /health (in turn, each capped at 64 KiB and one 3 s deadline for the whole exchange)
# of the seven other services that report an operator block, and appends
# operator.mode_changed / operator.registry_changed only at the first observation and on
# a change. A tick takes about 3 s per target at most, about 21 s for the seven; 60 s
# (same reasoning as the compose ledger service). Not an operator flag; "0" (a fly secret) turns the observer off.
FIELD_LEDGER_OBSERVE_EVERY="${FIELD_LEDGER_OBSERVE_EVERY:-60}" FIELD_LEDGER_OBSERVE_HEALTH=agent-registry=http://127.0.0.1:8001,delegation-authority=http://127.0.0.1:8003,kill-switch=http://127.0.0.1:8005,spend-governor=http://127.0.0.1:8006,federation-broker=http://127.0.0.1:8010,ops-console=http://127.0.0.1:8011,lifecycle-manager=http://127.0.0.1:8012 ledger serve --host 127.0.0.1 --port 8002 &
( fly_identity_env svc-delegation "$fly_kf_delegation"
delegation serve --host 127.0.0.1 --port 8003 &
fly_wait_service "$!" ) &
FIELD_SELF_AGENT_ID=conformance-sentinel FIELD_SELF_TOKEN_ID="${FIELD_SENTINEL_SELF_TOKEN:-}" sentinel serve --host 127.0.0.1 --port 8004 &
( fly_identity_env svc-killswitch "$fly_kf_killswitch"
killswitch serve --host 127.0.0.1 --port 8005 &
fly_wait_service "$!" ) &
governor serve --host 127.0.0.1 --port 8006 &
replay serve --host 127.0.0.1 --port 8007 &
# No --mock: since v1.2 D2 neither estate passes it (compose dropped it too);
# the only mock switch is FORCE_GATEWAY_MOCK=1, and a product estate must not
# fake the upstream. Verified against force_gateway/cli.py + api.py: without --mock,
# serve uses real_upstream — /health and /presets need no key, and only
# POST /v1/messages requires ANTHROPIC_API_KEY (returns an honest 502 naming
# the env var when unset). The hygiene judge is resolved from
# FORCE_HYGIENE_JUDGE (default: off), so with no key the judge stays off —
# which is the default anyway. Set ANTHROPIC_API_KEY via `fly secrets set`
# to light up real proxying; until that secret is placed, POST
# /gateway/v1/messages answers 502 here. The mock is asked for only with
# FORCE_GATEWAY_MOCK=1 (exactly 1; `forcegw serve --mock` sets the same
# variable), never on this estate; telemetry persists at
# $FIELD_DATA_DIR/gateway/telemetry.sqlite3.
FIELD_SELF_AGENT_ID=force-gateway FIELD_SELF_TOKEN_ID="${FIELD_GATEWAY_SELF_TOKEN:-}" forcegw serve --host 127.0.0.1 --port 8009 &
# FIELD_ORG_NAME is scoped to fedbroker only, matching its compose env block.
FIELD_ORG_NAME="Spin State Labs" fedbroker serve --host 127.0.0.1 --port 8010 &
console serve --host 127.0.0.1 --port 8011 &
FIELD_SELF_AGENT_ID=compliance-crosswalk FIELD_SELF_TOKEN_ID="${FIELD_CROSSWALK_SELF_TOKEN:-}" crosswalk serve --host 127.0.0.1 --port 8008 &
( fly_identity_env svc-lifecycle "$fly_kf_lifecycle"
lifecycle serve --host 127.0.0.1 --port 8012 &
fly_wait_service "$!" ) &
attest serve --host 127.0.0.1 --port 8013 &

caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &

# Supervisor: `wait -n` blocks until the FIRST child exits, for any reason.
# A partially-alive estate is worse than a dead one (health checks would pass
# for surviving services while others 502), so any child death — even a
# "clean" exit 0, which no long-running server should ever do — brings the
# whole machine down non-zero. Fly's restart policy then replaces the
# machine. No extra supervisor process is installed by design.
wait -n || true
echo "entrypoint: a service exited — taking the machine down for Fly to restart" >&2
exit 1
