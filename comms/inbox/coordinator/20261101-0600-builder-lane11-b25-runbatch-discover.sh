#!/bin/bash
# B-25: discovery version of runbatch.sh. usage: runbatch-discover.sh NAME [--list]
# Same inputs and outputs as runbatch.sh: worktree ~/ff-work/wt-NAME, log ~/ff-work/NAME-all.log with one "== <suite>"
# line and then the pytest summary line per suite, ~/ff-work/NAME-all.done at the end.
# Suites, in this order: core+sealed-ledger, tools, field-agent (the three names kept as before), then every other
# packages/*/tests and services/*/tests alphabetically, then (only when RUNBATCH_DEFENCE=1) every defence-shield/*/tests.
# Loud failures (the line contains "ERROR", which a done check greps like "failed"): a tests directory with no
# test_*.py file, a packages/* or services/* directory with src but no tests directory, a pytest exit code other than 0 or 1.
# --list prints the suites it would run (and each one's paths) and runs nothing.
N=$1; MODE=$2; W=~/ff-work/wt-$N; V=~/ff-work/venv-fp/bin; LOG=~/ff-work/$N-all.log
cd "$W" || { echo "no worktree $W" >&2; exit 2; }

suites=()   # "name|paths|cwd|extra PYTHONPATH"
suites+=("core+sealed-ledger|packages/field-core/tests services/sealed-ledger/tests|.|")
suites+=("tools|tools/tests|.|")
suites+=("field-agent|tests|packages/field-agent|")
for d in packages/*/ services/*/; do
  d=${d%/}; n=${d##*/}
  case "$n" in field-core|field-agent|sealed-ledger) continue ;; esac
  if [ -d "$d/tests" ]; then suites+=("$n|tests|$d|")
  elif [ -d "$d/src" ]; then suites+=("$n|MISSING|$d|"); fi
done
if [ "$RUNBATCH_DEFENCE" = 1 ]; then
  for d in defence-shield/*/; do
    d=${d%/}; n=${d##*/}
    if [ -d "$d/tests" ]; then suites+=("$n|tests|$d|$W/$d/src:")
    elif [ -d "$d/src" ]; then suites+=("$n|MISSING|$d|"); fi
  done
fi

if [ "$MODE" = "--list" ]; then
  for s in "${suites[@]}"; do IFS='|' read -r name paths cwd extra <<< "$s"; echo "== $name  ($paths in $cwd)"; done
  exit 0
fi

rm -f ~/ff-work/$N-all.done; : > "$LOG"
export CI=true PYTHONPATH=$W/packages/field-core/src:$(ls -d $W/services/*/src | tr '\n' ':')$W/packages/field-agent/src
for s in "${suites[@]}"; do
  IFS='|' read -r name paths cwd extra <<< "$s"
  echo "== $name" >> "$LOG"
  if [ "$paths" = MISSING ]; then echo "ERROR: $cwd has src but no tests directory" >> "$LOG"; continue; fi
  nfiles=$(cd "$cwd" && find $paths -name 'test_*.py' | wc -l)
  if [ "$nfiles" = 0 ]; then echo "ERROR: no test_*.py under $paths ($cwd)" >> "$LOG"; continue; fi
  out=$(cd "$cwd" && PYTHONPATH="$extra$PYTHONPATH" $V/python -m pytest -q $paths 2>&1); rc=$?
  printf '%s\n' "$out" | tail -1 >> "$LOG"
  case $rc in 0|1) ;; *) echo "ERROR: pytest exit code $rc" >> "$LOG" ;; esac
done
echo DONE > ~/ff-work/$N-all.done
