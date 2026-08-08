#!/usr/bin/env bash
# field-core demo — <60s. Requires the field-platform venv on PATH
# (see STATE.md: C:\Users\donal\.venvs\field-platform\Scripts).
set -euo pipefail

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "=== 1. The four shipped templates ==="
field templates

echo
echo "=== 2. Validate the default template (structurally valid, REPLACE-ME warnings) ==="
field templates --show default --out "$WORK/manifest.yaml"
field validate "$WORK/manifest.yaml" || true

echo
echo "=== 3. Break it: unseal the ledger -> INVALID (critical gap) ==="
python - "$WORK" <<'PY'
import sys, yaml, pathlib
work = pathlib.Path(sys.argv[1])
data = yaml.safe_load((work / "manifest.yaml").read_text(encoding="utf-8"))
data["ledger"]["cryptographic_seal"] = False
(work / "broken.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY
field validate "$WORK/broken.yaml" || echo "(exit code 1, as designed)"

echo
echo "=== 4. Hash chain: build 5 events, verify, tamper, verify again ==="
python - "$WORK" <<'PY'
import sys, json, pathlib
from field_core.ledger import GENESIS_HASH, make_event

work = pathlib.Path(sys.argv[1])
events, prev = [], GENESIS_HASH
for i in range(5):
    ev = make_event("action", {"seq": i, "amount": 100 + i}, prev_hash=prev,
                    agent_id="demo-agent")
    events.append(ev); prev = ev.hash

chain = work / "chain.jsonl"
chain.write_text("\n".join(e.model_dump_json() for e in events), encoding="utf-8")

# Tamper: change event 2's amount in place (classic quiet edit)
lines = chain.read_text(encoding="utf-8").splitlines()
rec = json.loads(lines[2]); rec["payload"]["amount"] = 999999
lines[2] = json.dumps(rec)
(work / "tampered.jsonl").write_text("\n".join(lines), encoding="utf-8")
PY
field verify-chain "$WORK/chain.jsonl"
field verify-chain "$WORK/tampered.jsonl" || echo "(tamper detected, exit 1 — this is the point)"

echo
echo "demo complete."
