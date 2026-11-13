"""G1 F3/F4 (field-platform issues 1067, 1068): static pins for the Fly image hardening.

Static only (no docker): the Dockerfile strips setuid/setgid bits after the last step that can add a binary and fails
the build if any remain; tools/ff-harden.sh (installed as /usr/local/sbin/ff-harden) sets and reads back the four
sysctls; the entrypoint writes the same four values with builtin `echo` only when FIELD_HARDEN_SYSCTLS=1 and never lets
a refused write stop the estate. ff-harden lives under tools/, not integration/, because every integration/**/*.sh is a
topology descriptor for tools/topology_lint.py, and the entrypoint launches nothing new (the lint refuses
path launches). The live check (sysctls read back, no setuid files, agent hardlink EPERM) is the G1 battery v2 run on
a throwaway app, not this test.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLY = ROOT / "integration" / "fly"
HARDEN = ROOT / "tools" / "ff-harden.sh"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_dockerfile_strips_setuid_after_the_last_binary_step_and_fails_if_any_remain():
    text = _text(FLY / "Dockerfile")
    lines = text.splitlines()
    strip = next(i for i, l in enumerate(lines) if "-perm /6000 -exec chmod a-s" in l)
    adds = [i for i, l in enumerate(lines) if re.match(r"^(COPY|RUN|ADD)\b", l) and "ff-harden" not in l and "/6000" not in l]
    assert max(adds) < strip, "a COPY/RUN/ADD after the setuid strip could reintroduce a setuid binary"
    assert lines[strip + 1].strip() == '&& test -z "$(find / -xdev -type f -perm /6000)"', "the build must fail if any remain"
    assert re.search(r"^COPY tools/ff-harden\.sh /usr/local/sbin/ff-harden$", text, re.M)


def test_topology_lint_admits_exactly_the_strip_commands_and_nothing_wider():
    import importlib.util

    spec = importlib.util.spec_from_file_location("topology_lint", ROOT / "tools" / "topology_lint.py")
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    ok = 'chmod 0755 /usr/local/sbin/ff-harden && find / -xdev -type f -perm /6000 -exec chmod a-s {} + && test -z "$(find / -xdev -type f -perm /6000)"'
    assert lint._run_is_known(ok)
    for bad in ('find / -xdev -type f -perm /6000 -exec rm {} +', 'test -z "$(curl x)"',
                'find / -xdev -type f -perm /6000 -exec chmod a-s {} + ; curl x', 'find / -perm /6000 -exec sh -c x {} +'):
        assert not lint._run_is_known(bad), bad


def test_ff_harden_sets_and_reads_back_the_four_settings():
    text = _text(HARDEN)
    for name, value in (("fs.protected_hardlinks", "1"), ("fs.protected_symlinks", "1"),
                        ("fs.protected_regular", "2"), ("user.max_user_namespaces", "0")):
        assert re.search(r"^set_one %s %s$" % (re.escape(name), value), text, re.M), name
    assert 'if [ "$now" = "$2" ]' in text and "exit $rc" in text


def test_entrypoint_hardens_only_when_armed_with_builtin_non_fatal_writes_matching_ff_harden():
    entry = _text(FLY / "entrypoint.sh")
    m = re.search(r'if \[ "\$\{FIELD_HARDEN_SYSCTLS:-0\}" = 1 \]; then\n(.*?)\nfi\n', entry, re.S)
    assert m, "the hardening block must be gated by FIELD_HARDEN_SYSCTLS=1"
    body = m.group(1).splitlines()
    writes = [re.fullmatch(r"\s+echo (\d) > /proc/sys/([\w/]+) 2>/dev/null \|\| echo [^\n]+ >&2", l) for l in body]
    writes = [w.groups() for w in writes if w]
    assert len(writes) == 4, body
    want = dict(re.findall(r"^set_one ([\w.]+) (\d)$", _text(HARDEN), re.M))
    assert {p.replace("/", "."): v for v, p in writes} == want, "entrypoint and ff-harden must set the same values"
    first_words = {l.split()[0] for l in body if l.strip()}
    assert first_words == {"echo"}, "only the echo builtin inside the block: no new launch (topology lint)"
    assert entry.index("trap shutdown TERM INT") < m.start() < entry.index("FIELD_REGISTRY_URL")


@pytest.mark.skipif(shutil.which("sh") is None, reason="no POSIX sh on this host")
def test_ff_harden_dry_run_writes_nothing_and_names_every_setting():
    p = subprocess.run(["sh", str(HARDEN)], env={"FF_HARDEN_DRY_RUN": "1", "PATH": "/usr/bin:/bin"},
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stdout + p.stderr
    for name in ("fs.protected_hardlinks", "fs.protected_symlinks", "fs.protected_regular", "user.max_user_namespaces"):
        assert "DRY RUN would set %s=" % name in p.stdout
