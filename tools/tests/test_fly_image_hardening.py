"""G1 F3/F4 (field-platform issues 1067, 1068): static pins for the Fly image hardening.

Static only (no docker): the Dockerfile strips setuid/setgid bits after the last step that can add a binary and fails
the build if any remain; ff-harden sets and reads back the four sysctls; the entrypoint calls it only when
FIELD_HARDEN_SYSCTLS=1 and never lets a refused sysctl stop the estate. The live check (sysctls read back, no
setuid files, agent hardlink EPERM) is the G1 battery v2 run on a throwaway app, not this test.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLY = ROOT / "integration" / "fly"


def _text(name: str) -> str:
    return (FLY / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_dockerfile_strips_setuid_after_the_last_binary_step_and_fails_if_any_remain():
    lines = _text("Dockerfile").splitlines()
    strip = next(i for i, l in enumerate(lines) if "-perm /6000 -exec chmod a-s" in l)
    adds = [i for i, l in enumerate(lines) if re.match(r"^(COPY|RUN|ADD)\b", l) and "ff-harden" not in l and "/6000" not in l]
    assert max(adds) < strip, "a COPY/RUN/ADD after the setuid strip could reintroduce a setuid binary"
    block = "\n".join(lines[strip - 1:strip + 3])
    assert re.search(r"find / -xdev -type f -perm /6000 \| grep -q \.; then [^\n]*exit 1", block)
    assert "COPY integration/fly/ff-harden.sh /usr/local/sbin/ff-harden" in _text("Dockerfile")


def test_ff_harden_sets_and_reads_back_the_four_settings():
    text = _text("ff-harden.sh")
    for name, value in (("fs.protected_hardlinks", "1"), ("fs.protected_symlinks", "1"),
                        ("fs.protected_regular", "2"), ("user.max_user_namespaces", "0")):
        assert re.search(r"^set_one %s %s$" % (re.escape(name), value), text, re.M), name
    assert 'if [ "$now" = "$2" ]' in text and "exit $rc" in text


def test_entrypoint_runs_ff_harden_only_when_armed_and_never_fails_on_it():
    entry = _text("entrypoint.sh")
    m = re.search(r'if \[ "\$\{FIELD_HARDEN_SYSCTLS:-0\}" = 1 \]; then\n\s+/usr/local/sbin/ff-harden >&2 \|\| echo [^\n]+\nfi', entry)
    assert m, "ff-harden must be gated by FIELD_HARDEN_SYSCTLS=1 and its failure must be non-fatal (|| echo)"
    assert entry.count("ff-harden") == m.group(0).count("ff-harden") + entry[:m.start()].count("ff-harden") + entry[m.end():].count("ff-harden")
    assert entry.index("set -eu") < m.start() < entry.index("trap shutdown TERM INT")


@pytest.mark.skipif(shutil.which("sh") is None, reason="no POSIX sh on this host")
def test_ff_harden_dry_run_writes_nothing_and_names_every_setting():
    p = subprocess.run(["sh", str(FLY / "ff-harden.sh")], env={"FF_HARDEN_DRY_RUN": "1", "PATH": "/usr/bin:/bin"},
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stdout + p.stderr
    for name in ("fs.protected_hardlinks", "fs.protected_symlinks", "fs.protected_regular", "user.max_user_namespaces"):
        assert "DRY RUN would set %s=" % name in p.stdout
