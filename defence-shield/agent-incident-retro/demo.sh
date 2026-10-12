#!/usr/bin/env bash
# Agent Incident Retro demo — <60s, offline, no estate.
# Generates a synthetic log, scans it, prints the summary, and VERIFIES the
# signed evidence pack — including re-hashing every cited source line. Then it
# proves tamper-evidence by editing one cited line and showing verify FAIL.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

# Prefer the field-platform venv; fall back to whatever `retro` is on PATH.
RETRO="retro"
for cand in "$HOME/.venvs/field-platform/Scripts" "$HOME/.venvs/field-platform/bin"; do
  if [ -x "$cand/retro" ] || [ -x "$cand/retro.exe" ]; then PATH="$cand:$PATH"; fi
done
command -v "$RETRO" >/dev/null 2>&1 || { echo "retro not found; pip install -e $HERE"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "== 1. keys + synthetic log (no real traffic) =="
retro keygen --out air.key --pub air.pub >/dev/null
retro synth  --out synth.log
echo "   $(wc -l < synth.log) log lines"

echo "== 2. scan =="
set +e
retro scan synth.log --out out --key air.key
scan_rc=$?
set -e
echo "   scan exit=$scan_rc (2 == ESCALATE present)"

echo "== 3. verify the signed pack (chain, signatures, report + every cited line) =="
retro verify out/evidence-pack.json --pub air.pub --report out/report.md --sources synth.log

echo "== 4. tamper proof: flip one cited line, verify must FAIL =="
cited_line="$(python - <<'PY'
import json
pack=json.load(open("out/evidence-pack.json"))
for e in pack["events"]:
    if e["event_type"]=="retro.session.flagged" and e["payload"]["evidence_lines"]:
        print(e["payload"]["evidence_lines"][0]["line"]); break
PY
)"
awk -v n="$cited_line" 'NR==n{$0=$0 " TAMPERED"} {print}' synth.log > synth.tampered.log
set +e
tamper_out="$(retro verify out/evidence-pack.json --pub air.pub --sources synth.tampered.log 2>&1)"
tamper_rc=$?
set -e
# require BOTH exit 1 AND the explicit failure banner, so a crash (also nonzero)
# cannot masquerade as a caught tamper.
if [ "$tamper_rc" -eq 1 ] && printf '%s' "$tamper_out" | grep -q "VERIFICATION FAILED"; then
  echo "   tampered log rejected (exit 1, VERIFICATION FAILED) — correct"
else
  echo "   FAIL: tamper not caught as expected"; printf '%s\n' "$tamper_out"; exit 1
fi

echo "== done =="
