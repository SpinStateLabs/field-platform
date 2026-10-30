#!/bin/sh
# usage: run.sh <path to compose_resolved_check.py>   (made-up inputs only)
T=$1; d=$(mktemp -d); cd "$d"; mkdir repo
printf '\377\376\000bad' > badutf.yml
printf 'services:\n  a: {volumes: [{type: bind, source: 5, target: /x}]}\n' > srcint.yml
printf 'services: 5\n' > svc5.yml
for f in badutf srcint svc5; do python3 "$T" --repo-root "$d/repo" $f.yml >o.txt 2>e.txt; echo "$f rc=$? traceback=$(grep -c Traceback e.txt) $(head -1 o.txt | cut -c1-80)"; done
PYTHONSAFEPATH=1 python3 "$T" --repo-root "$d/repo" svc5.yml >o.txt 2>e.txt; echo "safepath rc=$? traceback=$(grep -c Traceback e.txt)"
