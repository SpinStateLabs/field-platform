"""C-332 (reviewer C-331 F-C331-1): the CI "Container health" step must not pass while a container is dead.

The step's real `run:` script is taken from .github/workflows/ci.yml (compose-smoke) and executed with
`bash -eo pipefail` (the shell GitHub runs it with) against a fake `docker` and a no-op `sleep`, so each
state a compose project can be in is exercised without docker: all healthy passes; a container still
starting, unhealthy, exited, absent from `ps -a`, with no health at all, or an empty listing fails.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
SERVICES = ["registry", "ledger", "approver"]

FAKE_DOCKER = """#!/bin/sh
d="$FAKE_DIR"
case " $* " in
  *" config --services "*) cat "$d/services" ;;
  *" ps "*)
    n=$(cat "$d/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$d/n"
    if [ -f "$d/ps.$n" ]; then cat "$d/ps.$n"; else cat "$d/ps"; fi ;;
  *) exit 0 ;;
esac
"""


def _bash() -> str | None:
    candidates = [shutil.which("bash"), r"D:\Apps\Git\usr\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"]
    for exe in candidates:
        if not exe or not Path(exe).exists():
            continue
        try:
            out = subprocess.run([exe, "-c", "uname -s"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        # on Windows only Git bash (MINGW/MSYS) sees the Windows paths of the fake docker; WSL does not
        if out.startswith(("MINGW", "MSYS")) or (sys.platform != "win32" and out.startswith("Linux")):
            return exe
    return None


BASH = _bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="no usable bash")


def step_script(text: str | None = None) -> str:
    doc = yaml.safe_load(text if text is not None else CI.read_text(encoding="utf-8"))
    for step in doc["jobs"]["compose-smoke"]["steps"]:
        if str(step.get("name", "")).startswith("Container health"):
            return step["run"]
    raise AssertionError("no Container health step in compose-smoke")


def run_step(tmp_path: Path, ps: str | list[str], services=SERVICES, script: str | None = None) -> subprocess.CompletedProcess:
    (tmp_path / "docker").write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    (tmp_path / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    # three polls instead of 45: the loop's logic is what is under test, not its length (and each poll
    # forks several processes, which is slow under Windows bash)
    (tmp_path / "seq").write_text("#!/bin/sh\necho 1\necho 2\necho 3\n", encoding="utf-8", newline="\n")
    (tmp_path / "services").write_text("".join(s + "\n" for s in services), encoding="utf-8", newline="\n")
    frames = [ps] if isinstance(ps, str) else ps
    for i, frame in enumerate(frames):
        name = "ps" if i == len(frames) - 1 else f"ps.{i + 1}"
        (tmp_path / name).write_text(frame, encoding="utf-8", newline="\n")
    env = dict(os.environ, FAKE_DIR=str(tmp_path), PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    return subprocess.run([BASH, "-eo", "pipefail", "-c", script or step_script()], env=env, cwd=tmp_path,
                          capture_output=True, text=True, timeout=120)


def healthy(names=SERVICES) -> str:
    return "".join(f"{n} running healthy\n" for n in names)


def test_all_services_running_and_healthy_passes(tmp_path):
    r = run_step(tmp_path, healthy())
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_service_that_is_starting_and_then_healthy_passes(tmp_path):
    starting = "registry running starting\nledger running healthy\napprover running healthy\n"
    assert run_step(tmp_path, [starting, starting, healthy()]).returncode == 0


@pytest.mark.parametrize("name,ps", [
    ("stays starting", "registry running starting\nledger running healthy\napprover running healthy\n"),
    ("unhealthy", "registry running healthy\nledger running healthy\napprover running unhealthy\n"),
    ("the approver exited", "registry running healthy\nledger running healthy\napprover exited \n"),
    ("the approver is absent from ps -a", "registry running healthy\nledger running healthy\n"),
    ("a service has no health at all", "registry running healthy\nledger running healthy\napprover running \n"),
    ("a service is restarting", "registry running healthy\nledger running healthy\napprover restarting \n"),
    ("ps prints nothing", ""),
])
def test_a_dead_or_unhealthy_or_missing_container_fails(tmp_path, name, ps):
    r = run_step(tmp_path, ps)
    assert r.returncode != 0, f"{name}: the step passed\n" + r.stdout + r.stderr


def test_an_empty_service_list_fails(tmp_path):
    r = run_step(tmp_path, healthy(), services=[])
    assert r.returncode != 0, r.stdout + r.stderr


def test_the_step_in_ci_lists_with_ps_a_and_compares_against_config_services():
    script = step_script()
    assert "ps -a" in script and "config --services" in script


def test_mutant_the_old_ps_without_a_would_pass_an_exited_approver(tmp_path):
    """The pre-C-332 script (running containers only, no expected list) passes with the approver gone: the finding."""
    old = (
        "docker compose --profile approver up -d --no-deps --build approver\n"
        "for i in $(seq 1 45); do\n"
        "  bad=$(docker compose --profile approver ps --format '{{.Service}} {{.Health}}' | grep -v ' healthy$' || true)\n"
        "  test -z \"$bad\" && break\n  sleep 2\ndone\n"
        "test -z \"$bad\" || { echo bad; exit 1; }\n")
    r = run_step(tmp_path, "registry running healthy\nledger running healthy\n", script=old)
    assert r.returncode == 0, "the old script no longer reproduces the finding"
