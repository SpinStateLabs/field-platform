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
echo "$*" >> "$d/docker.calls"
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


def _fake(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def run_step(tmp_path: Path, ps: str | list[str], services=SERVICES, script: str | None = None, polls: bool = True,
             docker_text: str | None = None) -> subprocess.CompletedProcess:
    # every fake is executable (a Linux runner refuses a script without the bit and falls through to the real
    # command, which made the first version of these tests fail or pass for the wrong reason, C-344)
    _fake(tmp_path / "docker", docker_text if docker_text is not None else FAKE_DOCKER)
    _fake(tmp_path / "sleep", '#!/bin/sh\necho x >> "$FAKE_DIR/sleep.calls"\nexit 0\n')
    # three polls instead of 45: the loop's logic is what is under test, not its length (and each poll
    # forks several processes, which is slow under Windows bash)
    _fake(tmp_path / "seq", '#!/bin/sh\necho x >> "$FAKE_DIR/seq.calls"\necho 1\necho 2\necho 3\n')
    (tmp_path / "services").write_text("".join(s + "\n" for s in services), encoding="utf-8", newline="\n")
    frames = [ps] if isinstance(ps, str) else ps
    for i, frame in enumerate(frames):
        name = "ps" if i == len(frames) - 1 else f"ps.{i + 1}"
        (tmp_path / name).write_text(frame, encoding="utf-8", newline="\n")
    env = dict(os.environ, FAKE_DIR=str(tmp_path), PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    result = subprocess.run([BASH, "-eo", "pipefail", "-c", script or step_script()], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    # the fake docker really answered (the step's own calls reached it), so a missing or unrunnable fake
    # cannot let a test pass: `ps -a` and `config --services` both appear in its call log
    if script is None:
        # an empty service list stops the step before the first `ps -a` (polls=False); every other run polls
        calls = (tmp_path / "docker.calls").read_text(encoding="utf-8") if (tmp_path / "docker.calls").exists() else ""
        assert "config --services" in calls and (not polls or " ps -a " in " " + calls + " "), f"the fake docker was not used: {calls!r}\n{result.stderr}"
    return result


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
    ("a service exited but still reports healthy", "registry running healthy\nledger running healthy\napprover exited healthy\n"),
    ("a service is paused but still reports healthy", "registry running healthy\nledger running healthy\napprover paused healthy\n"),
])
def test_a_dead_or_unhealthy_or_missing_container_fails(tmp_path, name, ps):
    r = run_step(tmp_path, ps)
    assert r.returncode != 0, f"{name}: the step passed\n" + r.stdout + r.stderr


def test_a_service_absent_on_the_first_poll_and_healthy_on_the_second_passes(tmp_path):
    first = "registry running healthy\nledger running healthy\n"
    assert run_step(tmp_path, [first, healthy()]).returncode == 0


# C-348 (reviewer C-347 F-C347-2): the "fake docker was used" assertion is itself pinned. A stand-in for docker that
# answers but never logs (what an unrunnable or wrong fake looks like), or that logs only the config call, must
# make run_step's own assertion fire, whatever the executable bits are.
NO_LOG_DOCKER = FAKE_DOCKER.replace('echo "$*" >> "$d/docker.calls"\n', "")
CONFIG_ONLY_LOG_DOCKER = NO_LOG_DOCKER.replace(
    '  *" config --services "*) cat "$d/services" ;;',
    '  *" config --services "*) echo "$*" >> "$d/docker.calls"; cat "$d/services" ;;')


def test_a_fake_docker_that_logs_nothing_is_reported_as_not_used(tmp_path):
    assert NO_LOG_DOCKER != FAKE_DOCKER
    with pytest.raises(AssertionError, match="the fake docker was not used"):
        run_step(tmp_path, healthy(), docker_text=NO_LOG_DOCKER)


def test_a_fake_docker_that_logs_only_config_is_reported_as_not_used(tmp_path):
    assert CONFIG_ONLY_LOG_DOCKER != NO_LOG_DOCKER
    with pytest.raises(AssertionError, match="the fake docker was not used"):
        run_step(tmp_path, healthy(), docker_text=CONFIG_ONLY_LOG_DOCKER)


def test_the_fake_commands_are_executable(tmp_path):
    run_step(tmp_path, healthy())
    for name in ("docker", "sleep", "seq"):
        assert os.access(tmp_path / name, os.X_OK), name
    assert (tmp_path / "seq.calls").exists(), "the stubbed seq was not used (the real one would run 45 polls)"


def test_an_empty_service_list_fails(tmp_path):
    r = run_step(tmp_path, healthy(), services=[], polls=False)
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
