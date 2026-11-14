#!/bin/sh
# ff-harden — kernel hardening for the Fly sandbox estate (field-platform issues 1067 F3, 1068 F4; G1 battery 2026-11-13).
#
# Measured on the Fly kernel 6.12.116-fly by the G1 battery: fs.protected_hardlinks=0, fs.protected_symlinks=0,
# fs.protected_regular=0 and user.max_user_namespaces=745, so a non-root uid could hardlink root/broker-owned files it
# cannot write and create user namespaces. Nothing on this estate needs either (every service runs as root in one
# container; no service creates user namespaces).
#
# Runs as root. Called by entrypoint.sh ONLY when FIELD_HARDEN_SYSCTLS=1 (default off: merging this changes nothing
# at run time until an operator arms it). Each setting is written and READ BACK; the script prints one line per
# setting and exits 0 when all four hold, 1 otherwise (the entrypoint logs a failure and continues, so a platform
# that refuses a sysctl cannot take the estate down). FF_HARDEN_DRY_RUN=1 prints what it would write.
set -u
rc=0
set_one() {   # set_one NAME VALUE  (NAME in sysctl dot form)
    path="/proc/sys/$(printf '%s' "$1" | tr . /)"
    if [ "${FF_HARDEN_DRY_RUN:-0}" = 1 ]; then
        echo "ff-harden: DRY RUN would set $1=$2 (now $(cat "$path" 2>/dev/null || echo unreadable))"
        return 0
    fi
    if ! printf '%s\n' "$2" > "$path" 2>/dev/null; then
        echo "ff-harden: FAIL $1: write refused (now $(cat "$path" 2>/dev/null || echo unreadable))"
        rc=1
        return 0
    fi
    now=$(cat "$path" 2>/dev/null || echo unreadable)
    if [ "$now" = "$2" ]; then echo "ff-harden: ok $1=$now"; else echo "ff-harden: FAIL $1: wrote $2, reads $now"; rc=1; fi
}
set_one fs.protected_hardlinks 1
set_one fs.protected_symlinks 1
set_one fs.protected_regular 2
set_one user.max_user_namespaces 0
exit $rc
