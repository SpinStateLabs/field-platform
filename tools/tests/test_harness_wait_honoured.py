"""Every test estate that boots estate_harness.py honours FIELD_TEST_HARNESS_WAIT and
never leaks the harness process when it gives up.

The harness imports 13 services and takes 30-50 s to answer /ledger/health on an
idle Windows box, well over 60 s when a big pytest process or anything else is
loading the machine. test_upgrade_smoke_fixture.py and test_estate_kill_watcher.py
hard-coded 60 s while test_estate_probe.py read FIELD_TEST_HARNESS_WAIT, and the
90 s waits elsewhere ignored it. All now share harness_wait.harness_wait().

The estate tests stub the harness with a process that never serves, require each
estate to give up after the configured wait (not the old fixed 60 s) and require
the spawned stub to be dead afterwards.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import harness_wait  # noqa: E402
import test_estate_kill_watcher as kill_watcher  # noqa: E402
import test_estate_probe as probe  # noqa: E402
import test_renew_token as renew  # noqa: E402
import test_ssl_renewal as ssl_renewal  # noqa: E402
import test_upgrade_smoke_fixture as smoke  # noqa: E402

WAIT_S = 3
SLACK_S = 25  # far under the old fixed 60 s, far over the configured 3 s


# --- the helper ----------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", " ", "abc", "nan", "NaN", "inf", "-inf", "Infinity", "0", "0.0", "-5", "-0.1", "1e999x"])
def test_bad_values_fall_back_to_the_default(monkeypatch, bad):
    monkeypatch.setenv(harness_wait.ENV, bad)
    assert harness_wait.harness_wait(60) == 60.0
    assert harness_wait.harness_wait(90) == 90.0


def test_unset_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv(harness_wait.ENV, raising=False)
    assert harness_wait.harness_wait(60) == 60.0
    assert harness_wait.harness_wait(90) == 90.0


@pytest.mark.parametrize("good,expected", [("300", 300.0), (" 12.5 ", 12.5), ("1", 1.0), ("0.5", 0.5), ("1e2", 100.0)])
def test_good_values_are_honoured(monkeypatch, good, expected):
    monkeypatch.setenv(harness_wait.ENV, good)
    assert harness_wait.harness_wait(60) == expected


def test_init_failure_terminates_started_subprocesses():
    procs = []

    @harness_wait.kills_proc_on_init_failure
    class Boom:
        def __init__(self):
            self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            procs.append(self.proc)
            self.sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            procs.append(self.sentinel)
            raise KeyError("provisioning failed")

    with pytest.raises(KeyError):
        Boom()
    for p in procs:
        assert _dies(p), "a subprocess started before the constructor raised was left running"


# --- the estates ---------------------------------------------------------------------------

def _dies(proc, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def silent_harness(tmp_path, monkeypatch):
    """A harness that never answers. Returns the list of every subprocess the estate spawned."""
    stub = tmp_path / "silent_harness.py"
    stub.write_text("import time\ntime.sleep(300)\n")
    monkeypatch.setenv("FIELD_TEST_HARNESS_WAIT", str(WAIT_S))
    spawned: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        p = real_popen(*args, **kwargs)
        spawned.append(p)
        return p

    for mod in (smoke, kill_watcher, probe, renew, ssl_renewal):
        monkeypatch.setattr(mod, "HARNESS", stub)
        monkeypatch.setattr(mod.subprocess, "Popen", recording_popen)
    yield spawned
    for p in spawned:  # never leave a stub behind, whatever the assertions did
        harness_wait.terminate(p)


def _gives_up_promptly_and_leaves_nothing_running(spawned, build):
    t0 = time.time()
    with pytest.raises(RuntimeError, match="did not come up"):
        build()
    assert time.time() - t0 < WAIT_S + SLACK_S
    assert spawned, "the estate never started a harness"
    for p in spawned:
        assert _dies(p), "the estate gave up but left its harness process running"


def test_upgrade_smoke_estate(silent_harness, tmp_path):
    _gives_up_promptly_and_leaves_nothing_running(silent_harness, lambda: smoke.UpgradedEstate(tmp_path, rosters=True))


def test_kill_watcher_estate(silent_harness, tmp_path):
    _gives_up_promptly_and_leaves_nothing_running(silent_harness, lambda: kill_watcher.Estate(tmp_path, secret=True))


def test_estate_probe_estate(silent_harness, tmp_path):
    _gives_up_promptly_and_leaves_nothing_running(silent_harness, lambda: probe.Estate(tmp_path, secret=True))


def test_renew_token_estate(silent_harness, tmp_path):
    _gives_up_promptly_and_leaves_nothing_running(silent_harness, lambda: renew.Estate(tmp_path))


def test_ssl_renewal_estate(silent_harness, tmp_path):
    _gives_up_promptly_and_leaves_nothing_running(silent_harness, lambda: ssl_renewal.SslEstate(tmp_path))
