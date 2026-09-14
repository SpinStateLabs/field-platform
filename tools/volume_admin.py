#!/usr/bin/env python3
"""volume_admin - the only writer of the GB10 manifests and keys volumes.

v1.2 Phase C. On the GB10 (integration/demo/docker-compose.gb10.yml) every
platform service mounts the named volume `field-manifests` READ-ONLY at
/data/manifests, and the ledger mounts `field-keys` READ-ONLY at /data/keys.
So no service container can write a FILE in /data/manifests, and the ledger
(the only reader of /data/keys) cannot write one in /data/keys. The other
twelve service containers have no field-keys mount: /data/keys there (if it
exists) is a plain directory on their read-write field-data volume, writable
by the container's user (root), but it is not the field-keys volume the
ledger reads its anchor key from. That is all the mounts give: a manifest_ref
is not confined to /data/manifests (an absolute path or `..` resolves
anywhere), and every service keeps field-data at /data read-write, so a
manifest written elsewhere under /data and registered by ref is still
honoured. This tool, run by two one-shot compose services, is the
writer:

  manifests seed      manifests-admin's default command, run by every `up`
                      before any platform service starts (depends_on
                      service_completed_successfully). The FIRST run copies
                      /data/manifests from the field-data volume (mounted
                      read-only at /estate) into the empty volume, byte for
                      byte, and writes a marker. Every later run sees the
                      marker and writes nothing. Registered manifest_refs
                      (/data/manifests/<id>.yaml) therefore resolve to the
                      same bytes before and after the upgrade. A seeded file
                      that is not a FIELD manifest (a roster, notes) is named
                      in a `note:` line: it is read-only from then on and
                      `install` cannot change it.
  manifests install   the operator's one command for a new or changed
                      manifest: `... run --rm manifests-admin install
                      NAME.yaml [...]` copies NAME from the repo checkout's
                      manifests/ (mounted read-only at /src). Every named file
                      must resolve with field-core's own manifest resolver
                      (the check every reader applies) before ANY is written;
                      each is replaced atomically and appended to an install
                      log in the volume.
  keys generate       `... run --rm keys-admin generate NAME`: a new Ed25519
                      key pair in /keys (field-keys), private key 0600 under
                      umask 077, never overwriting, printing only the paths
                      and the sha-256 fingerprint of the public key.
  keys export-public  `... run --rm -T keys-admin export-public NAME`: prints
                      NAME.pub.pem (public material only, after checking it
                      IS an Ed25519 public key) so it can be kept off-box.
                      Anchor and sidecar signatures verify only with the PEM,
                      never with the fingerprint, and field-keys is not in the
                      field-data backup.
  keys import-public  `... run --rm -T keys-admin import-public --dir
                      /keys/callers CALLER_ID < CALLER_ID.pub.pem` (v1.2 F2b):
                      reads ONE public PEM from stdin, checks it is an Ed25519
                      PUBLIC key (a private key is refused, exit 2, never
                      echoed), and writes /keys/callers/CALLER_ID.pub.pem
                      (0644, re-encoded from the parsed key, never
                      overwriting), printing the path and the fingerprint.
                      The ledger reads that directory as its caller keyring
                      (FIELD_LEDGER_CALLER_KEYRING=/data/keys/callers); each
                      service's PRIVATE key is generated on the host, outside
                      every volume, and bind-mounted into that service only.

ENFORCED here (tools/tests/test_volume_admin.py): seed never overwrites a
different file, never writes into a volume it did not seed (a foreign file ⇒
refused, nothing written), refuses an unreadable marker, and is a no-op once
seeded; install refuses an unseeded volume, a name that is not a plain
*.yaml/*.yml file name, and any file the resolver would not accept, writing
nothing; keys never overwrite and never print private key material;
import-public refuses anything but an Ed25519 public key and never overwrites.

DECLARED only: that nobody else writes the volumes. The :ro mounts are compose
configuration; root on the GB10 host can write any volume directly, and a
container started by hand with the volume mounted read-write is not stopped by
this tool.

Exit status: 0 done, 1 refused because of estate state (conflict, not seeded,
unreadable marker, key exists, public key missing or not Ed25519), 2 refused
because of the input (usage, bad name, invalid manifest).
Stdlib plus field-core (installed in the platform image). Output is ASCII.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MARKER = ".field-manifests-seeded.json"
INSTALL_LOG = ".field-manifests-installs.jsonl"
TMP_PREFIX = ".volume-admin-tmp-"
_MANIFEST_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.ya?ml$")
_KEY_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class Refused(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(dest: Path, data: bytes, mode: int | None = None) -> None:
    """Write beside ``dest`` and rename over it: a reader sees the old file or
    the new one, never a torn one, and a crash leaves only a TMP_PREFIX file."""
    tmp = dest.with_name(f"{TMP_PREFIX}{dest.name}")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, dest)


def _volume_entries(volume: Path) -> list[str]:
    """Relative paths of every file or symlink in the volume, ignoring this
    tool's own marker, log and interrupted temp files."""
    found = []
    for root, dirs, files in os.walk(volume, followlinks=False):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
            if name in (MARKER, INSTALL_LOG) or name.startswith(TMP_PREFIX):
                continue
            found.append(os.path.relpath(os.path.join(root, name), volume).replace(os.sep, "/"))
    return sorted(found)


# -- manifests seed ----------------------------------------------------------------


def seed(estate: Path, volume: Path) -> int:
    marker = volume / MARKER
    if marker.exists():
        try:
            info = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Refused(1, f"seed marker {marker} is unreadable; not touching the volume")
        print(f"manifests seed: already seeded at {info.get('seeded_at')} "
              f"({len(info.get('files', {}))} files) - nothing written")
        return 0
    if not volume.is_dir():
        raise Refused(2, f"volume {volume} is not a directory (is field-manifests mounted?)")
    if estate.exists() and not estate.is_dir():
        raise Refused(2, f"source {estate} exists but is not a directory")

    # Plan everything before writing anything.
    plan: list[tuple[str, Path, Path]] = []  # (rel, source, dest)
    conflicts: list[str] = []
    wanted = _volume_entries(estate) if estate.is_dir() else []
    for rel in wanted:
        src, dest = estate / rel, volume / rel
        if dest.is_symlink() or dest.exists():
            if src.is_symlink() != dest.is_symlink():
                conflicts.append(f"{rel}: symlink/file mismatch")
            elif src.is_symlink():
                if os.readlink(src) != os.readlink(dest):
                    conflicts.append(f"{rel}: different symlink target")
            elif dest.is_dir() or _sha256(src) != _sha256(dest):
                conflicts.append(f"{rel}: different content already in the volume")
            continue  # identical: an earlier interrupted seed copied it
        plan.append((rel, src, dest))
    for rel in _volume_entries(volume):
        if rel not in wanted:
            conflicts.append(f"{rel}: in the volume but not in {estate} (written by something other than seed)")
    if conflicts:
        for c in conflicts:
            print(f"REFUSED {c}")
        raise Refused(1, f"manifests seed: {len(conflicts)} conflict(s); nothing written, no marker")

    for rel, src, dest in plan:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            os.symlink(os.readlink(src), dest)
        else:
            _atomic_write(dest, src.read_bytes(), mode=src.stat().st_mode & 0o777)
    for stale in volume.rglob(f"{TMP_PREFIX}*"):
        stale.unlink()

    files = {}
    for rel in _volume_entries(volume):
        p = volume / rel
        files[rel] = ("symlink:" + os.readlink(p)) if p.is_symlink() else _sha256(p)
    _atomic_write(marker, (json.dumps({"seeded_at": _now(), "source": str(estate),
                                       "files": files}, indent=2, sort_keys=True) + "\n").encode())
    if not estate.is_dir():
        print(f"manifests seed: no {estate} on the data volume - seeded an EMPTY manifests volume")
    from field_core.clients import ManifestResolver  # the resolver every reader uses

    resolver = ManifestResolver(manifest_dir=volume)
    for rel, digest in files.items():
        print(f"seeded {rel} {digest[:16]}")
        if not (_MANIFEST_NAME.match(rel) and resolver.resolve_detail(rel)[0] is not None):
            print(f"note: {rel} is not a FIELD manifest; it is read-only in this volume from now on "
                  "and `install` cannot change it (keep rosters on field-data, e.g. /data/doa-roster.yaml)")
    print(f"manifests seed: {len(files)} file(s) seeded from {estate} ({len(plan)} copied now)")
    return 0


# -- manifests install -------------------------------------------------------------


def install(src: Path, volume: Path, names: list[str]) -> int:
    if not (volume / MARKER).exists():
        raise Refused(1, f"volume {volume} is not seeded; `docker compose up` runs "
                         "`manifests seed` first - refusing to write")
    from field_core.clients import ManifestResolver  # the resolver every reader uses

    resolver = ManifestResolver(manifest_dir=src)
    staged: list[tuple[str, bytes]] = []
    for name in names:
        if not _MANIFEST_NAME.match(name) or name in (MARKER, INSTALL_LOG):
            raise Refused(2, f"'{name}' is not a plain manifest file name (NAME.yaml / NAME.yml); "
                             "nothing written")
        path = src / name
        if not path.is_file():
            raise Refused(2, f"{path} is not a file; nothing written")
        manifest, reason = resolver.resolve_detail(name)
        if manifest is None:
            raise Refused(2, f"{name} would not resolve for a reader ({reason}); nothing written")
        staged.append((name, path.read_bytes()))

    with open(volume / INSTALL_LOG, "ab") as log:
        for name, data in staged:
            dest = volume / name
            before = _sha256(dest) if dest.is_file() else None
            after = hashlib.sha256(data).hexdigest()
            if before == after:
                print(f"unchanged {name} {after[:16]}")
                continue
            _atomic_write(dest, data, mode=0o644)
            log.write((json.dumps({"ts": _now(), "name": name, "sha256_before": before,
                                   "sha256_after": after}, sort_keys=True) + "\n").encode())
            log.flush()
            os.fsync(log.fileno())
            print(f"installed {name} {(before or 'new')[:16]} -> {after[:16]}")
    return 0


# -- keys generate -----------------------------------------------------------------


def generate_key(directory: Path, name: str) -> int:
    if not _KEY_NAME.match(name):
        raise Refused(2, f"key name '{name}' must match {_KEY_NAME.pattern}")
    from field_core.signing import generate_keypair, key_fingerprint

    private_path, public_path = directory / f"{name}.pem", directory / f"{name}.pub.pem"
    for p in (private_path, public_path):
        if p.exists() or p.is_symlink():
            raise Refused(1, f"{p} already exists; keys are never overwritten")
    old_umask = os.umask(0o077)
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        private_pem, public_pem = generate_keypair()
        for path, text, mode in ((private_path, private_pem, 0o600), (public_path, public_pem, 0o644)):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(path, mode)
        del private_pem
    finally:
        os.umask(old_umask)
    print(f"private key: {private_path} (0600; never printed)")
    print(f"public key:  {public_path}")
    print(f"fingerprint: {key_fingerprint(public_pem)}")
    return 0


def export_public(directory: Path, name: str) -> int:
    """Print NAME.pub.pem, and only if it is an Ed25519 PUBLIC key: a private
    key placed under the public name is refused, never echoed."""
    if not _KEY_NAME.match(name):
        raise Refused(2, f"key name '{name}' must match {_KEY_NAME.pattern}")
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from field_core.signing import key_fingerprint

    public_path = directory / f"{name}.pub.pem"
    if not public_path.is_file():
        raise Refused(1, f"{public_path} does not exist; run `keys generate {name}` first")
    try:
        text = public_path.read_text(encoding="ascii")
        public = serialization.load_pem_public_key(text.encode("ascii"))
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise Refused(1, f"{public_path} is not a public key PEM ({type(exc).__name__}); nothing printed")
    if not isinstance(public, Ed25519PublicKey):
        raise Refused(1, f"{public_path} is not an Ed25519 public key; nothing printed")
    # Re-encoded from the parsed public key, never the file text echoed.
    pem = public.public_bytes(serialization.Encoding.PEM,
                              serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    sys.stdout.write(pem)
    print(f"fingerprint: {key_fingerprint(pem)}", file=sys.stderr)
    return 0


def import_public(directory: Path, name: str) -> int:
    """F2b: write NAME.pub.pem into the caller keyring from ONE Ed25519 PUBLIC
    key PEM on stdin. A private key (or an EC key, garbage, nothing) is
    refused with exit 2 and never echoed; an existing file is never
    overwritten (exit 1). What is written is re-encoded from the parsed
    public key, so a trailing private block on stdin never reaches the file."""
    if not _KEY_NAME.match(name):
        raise Refused(2, f"caller id '{name}' must match {_KEY_NAME.pattern}")
    from cryptography.hazmat.primitives import serialization
    from field_core.signing import key_fingerprint, load_ed25519_public_key

    dest = directory / f"{name}.pub.pem"
    if dest.exists() or dest.is_symlink():
        raise Refused(1, f"{dest} already exists; keys are never overwritten")
    stdin = getattr(sys.stdin, "buffer", None)
    raw = stdin.read() if stdin is not None else sys.stdin.read().encode("utf-8", "replace")
    try:
        public = load_ed25519_public_key(raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        why = "not ASCII" if isinstance(exc, UnicodeDecodeError) else str(exc)
        raise Refused(2, f"stdin is not an Ed25519 public key PEM ({why}); nothing written")
    del raw
    pem = public.public_bytes(serialization.Encoding.PEM,
                              serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(pem)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(dest, 0o644)
    print(f"imported: {dest} (0644)")
    print(f"fingerprint: {key_fingerprint(pem)}")
    return 0


# -- CLI ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Writer of the GB10 manifests and keys volumes.")
    top = parser.add_subparsers(dest="area", required=True)

    m = top.add_parser("manifests").add_subparsers(dest="cmd", required=True)
    s = m.add_parser("seed", help="first run: copy the data volume's manifests in; later: no-op")
    s.add_argument("--estate", default="/estate/manifests")
    s.add_argument("--volume", default="/manifests")
    i = m.add_parser("install", help="install named manifests from the repo checkout")
    i.add_argument("--src", default="/src")
    i.add_argument("--volume", default="/manifests")
    i.add_argument("names", nargs="+")

    k = top.add_parser("keys").add_subparsers(dest="cmd", required=True)
    g = k.add_parser("generate", help="new Ed25519 key pair; never overwrites")
    g.add_argument("--dir", default="/keys")
    g.add_argument("name")
    e = k.add_parser("export-public", help="print NAME.pub.pem (public key only) to keep off-box")
    e.add_argument("--dir", default="/keys")
    e.add_argument("name")
    ip = k.add_parser("import-public",
                      help="F2b: write CALLER_ID.pub.pem into the caller keyring from ONE public PEM on stdin")
    ip.add_argument("--dir", default="/keys/callers")
    ip.add_argument("name", metavar="caller_id")

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        if args.area == "manifests" and args.cmd == "seed":
            return seed(Path(args.estate), Path(args.volume))
        if args.area == "manifests":
            return install(Path(args.src), Path(args.volume), args.names)
        if args.cmd == "export-public":
            return export_public(Path(args.dir), args.name)
        if args.cmd == "import-public":
            return import_public(Path(args.dir), args.name)
        return generate_key(Path(args.dir), args.name)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
