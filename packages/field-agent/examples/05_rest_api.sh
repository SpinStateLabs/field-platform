#!/usr/bin/env bash
# Sample: the same three hooks over RAW REST — no SDK, any language.
#
# The SDK has no private channel: these endpoints ARE the interface, and
# every service serves interactive OpenAPI docs at http://127.0.0.1:<port>/docs
# (sentinel :8004, kill-switch :8005, governor :8006, registry :8001,
# ledger :8002, delegation :8003).
#
# Usage:  bash 05_rest_api.sh <token_id>     (after 04_bootstrap_operator.py)
# Auth:   when FIELD_SHARED_SECRET is set, add:  -H "x-field-auth: $FIELD_SHARED_SECRET"
set -euo pipefail

TOKEN="${1:?usage: 05_rest_api.sh <token_id>}"
AGENT=sample-agent
SENTINEL="${FIELD_SENTINEL_URL:-http://127.0.0.1:8004}"
GOVERNOR="${FIELD_GOVERNOR_URL:-http://127.0.0.1:8006}"
KILLSWITCH="${FIELD_KILLSWITCH_URL:-http://127.0.0.1:8005}"
AUTH=()
[ -n "${FIELD_SHARED_SECRET:-}" ] && AUTH=(-H "x-field-auth: $FIELD_SHARED_SECRET")

echo "-- hook 1: ACTIONS — POST /check (HTTP 200 either way; the verdict decides) --"
curl -sf "${AUTH[@]}" -X POST "$SENTINEL/check" -H 'content-type: application/json' \
  -d "{\"agent_id\":\"$AGENT\",\"action\":\"draft invoices\",\"token_id\":\"$TOKEN\"}"
echo

echo "-- hook 2: USAGE — POST /usage (201; 404 = no cap = refused) --"
curl -sf "${AUTH[@]}" -X POST "$GOVERNOR/usage" -H 'content-type: application/json' \
  -d "{\"agent_id\":\"$AGENT\",\"model\":\"claude-haiku-4-5\",\"input_tokens\":1000,\"output_tokens\":200,\"note\":\"rest sample\"}"
echo

echo "-- hook 3: LIVENESS — GET /heartbeat/{agent_id} (killed=true means STOP) --"
curl -sf "${AUTH[@]}" "$KILLSWITCH/heartbeat/$AGENT"
echo

echo "rest sample complete."
