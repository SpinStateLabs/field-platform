#!/bin/bash
# FIELD Platform — single-container supervisor for the Fly.io sandbox estate.
#
# Mirrors integration/demo/docker-compose.yml (the ground truth for service
# commands and ports): same thirteen-service estate, same `<cli> serve` commands,
# but every service binds 127.0.0.1 inside this one container. Caddy (:8080,
# /etc/caddy/Caddyfile) is the only 0.0.0.0 listener. Keep the commands below
# in sync with the compose file.
#
# This is the PRODUCT estate: sentinel defaults to ENFORCE. The GB10 burn-in
# estate runs log_only — never copy this default there.
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
export FIELD_FEDERATION_URL="${FIELD_FEDERATION_URL:-http://127.0.0.1:8010}"
export FIELD_LIFECYCLE_URL="${FIELD_LIFECYCLE_URL:-http://127.0.0.1:8012}"
export FIELD_ATTEST_URL="${FIELD_ATTEST_URL:-http://127.0.0.1:8013}"

# Operator passthroughs — same names and defaults as the compose x-service
# env (v1.2 A0). Blank/default unless set via `fly secrets set` or [env].
# The 86400 tick defaults mean the lifecycle/crosswalk schedulers fire daily
# here too; with no roster file a lifecycle tick is logged as skipped.
export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-}"
export FIELD_LIFECYCLE_ROSTER="${FIELD_LIFECYCLE_ROSTER:-}"
export FIELD_LIFECYCLE_EVERY="${FIELD_LIFECYCLE_EVERY:-86400}"
export FIELD_CROSSWALK_EVERY="${FIELD_CROSSWALK_EVERY:-86400}"
export FIELD_KILL_ENDPOINT_ALLOWLIST="${FIELD_KILL_ENDPOINT_ALLOWLIST:-}"
export FIELD_LEDGER_RETENTION_DAYS="${FIELD_LEDGER_RETENTION_DAYS:-2555}"
export FIELD_MANIFEST_DIR="${FIELD_MANIFEST_DIR:-/data/manifests}"
export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-}"

# Product estate enforces; respect an explicit override from the environment.
export FIELD_SENTINEL_MODE="${FIELD_SENTINEL_MODE:-enforce}"

registry serve --host 127.0.0.1 --port 8001 &
ledger serve --host 127.0.0.1 --port 8002 &
delegation serve --host 127.0.0.1 --port 8003 &
sentinel serve --host 127.0.0.1 --port 8004 &
killswitch serve --host 127.0.0.1 --port 8005 &
governor serve --host 127.0.0.1 --port 8006 &
replay serve --host 127.0.0.1 --port 8007 &
# No --mock, unlike the compose demo: the product estate must not fake the
# upstream. Verified against force_gateway/cli.py + api.py: without --mock,
# serve uses real_upstream — /health and /presets need no key, and only
# POST /v1/messages requires ANTHROPIC_API_KEY (returns an honest 502 naming
# the env var when unset). The hygiene judge is resolved from
# FORCE_HYGIENE_JUDGE (default: off), so with no key the judge stays off —
# which is the default anyway. Set ANTHROPIC_API_KEY via `fly secrets set`
# to light up real proxying.
forcegw serve --host 127.0.0.1 --port 8009 &
# FIELD_ORG_NAME is scoped to fedbroker only, matching its compose env block.
FIELD_ORG_NAME="Spin State Labs" fedbroker serve --host 127.0.0.1 --port 8010 &
console serve --host 127.0.0.1 --port 8011 &
crosswalk serve --host 127.0.0.1 --port 8008 &
lifecycle serve --host 127.0.0.1 --port 8012 &
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
