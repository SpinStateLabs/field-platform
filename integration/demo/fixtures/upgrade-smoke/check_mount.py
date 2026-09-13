"""Run INSIDE a platform container, fed on stdin by CI's compose-upgrade-smoke:

    docker compose ... exec -T SERVICE python - PATH ro|absent < check_mount.py

`ro`: PATH must be a mount point whose options include `ro`, AND a write
there must fail with EROFS (both, so neither a mis-parsed /proc/mounts nor a
permission error passes for a read-only mount). `absent`: PATH must not be a
mount point in this container (field-keys is mounted into the ledger only).
Exit 0 pass, 1 fail. Stdlib only; prints one line.
"""
import errno
import os
import sys

path, want = sys.argv[1], sys.argv[2]
host = os.environ.get("HOSTNAME", "?")
with open("/proc/mounts") as fh:
    options = [line.split()[3].split(",") for line in fh if len(line.split()) > 3 and line.split()[1] == path]

if want == "absent":
    print(f"{host}: {path} {'not a mount point' if not options else 'IS MOUNTED'} (want absent)")
    sys.exit(0 if not options else 1)

if not options or "ro" not in options[-1]:
    print(f"{host}: {path} mount options {options[-1] if options else None} (want ro)")
    sys.exit(1)
probe = os.path.join(path, ".ci-write-probe")
try:
    open(probe, "w").close()
except OSError as exc:
    print(f"{host}: {path} mounted ro, write refused with {errno.errorcode.get(exc.errno, exc.errno)}")
    sys.exit(0 if exc.errno == errno.EROFS else 1)
os.unlink(probe)
print(f"{host}: {path} is WRITABLE despite ro options")
sys.exit(1)
