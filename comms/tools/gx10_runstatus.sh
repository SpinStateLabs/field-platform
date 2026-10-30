#!/bin/bash
# One line per ~/ff-work/<name>-all.log: how many suites have started, how many summary lines report a failure,
# whether the runner process is still alive, and the state, so a stuck run is visible in one call (B-09).
#
#   gx10_runstatus.sh [dir] [expected_suites]      default dir ~/ff-work, default 16 suites
#
# State: DONE (done marker present), RUNNING (runner alive), STUCK (no done marker, no runner, log not finished:
# the runner died or was killed), IDLE-LOG (a log with no suite line yet and no runner). The pgrep pattern has its
# first letter bracketed so this script never matches its own command line.
D=${1:-$HOME/ff-work}
EXPECT=${2:-16}
now=$(date +%s)
printf '%-12s %7s %6s %-6s %-9s %s\n' name suites failed alive state age
for log in "$D"/*-all.log; do
    [ -e "$log" ] || continue
    n=$(basename "$log" -all.log)
    suites=$(grep -c '^== ' "$log")
    failed=$(grep -Ec '[0-9]+ (failed|error)' "$log")
    if pgrep -f "[r]unbatch.sh $n( |\$)" >/dev/null; then alive=yes; else alive=no; fi
    if [ -f "$D/$n-all.done" ]; then state=DONE
    elif [ "$alive" = yes ]; then state=RUNNING
    elif [ "$suites" -eq 0 ]; then state=IDLE-LOG
    else state=STUCK
    fi
    age=$(( now - $(stat -c %Y "$log") ))
    note=""
    if [ "$state" = DONE ] && [ "$suites" -ne "$EXPECT" ]; then note=" (suites != $EXPECT)"; fi
    if [ "$state" = DONE ] && [ "$failed" -ne 0 ]; then note="$note (FAILURES)"; fi
    printf '%-12s %7s %6s %-6s %-9s %ss%s\n' "$n" "$suites" "$failed" "$alive" "$state" "$age" "$note"
done
