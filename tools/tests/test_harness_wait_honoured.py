"""Every test estate that boots estate_harness.py honours FIELD_TEST_HARNESS_WAIT.

The harness imports every service (13 create_app factories) and takes 30-50 s to
answer /ledger/health on an idle Windows box, well over 60 s when a big pytest
process or anything else is loading the machine. test_estate_probe.py already
reads FIELD_TEST_HARNESS_WAIT (default 60) for that wait; test_upgrade_smoke_fixture.py
and test_estate_kill_watcher.py hard-coded 60, so on a loaded box their module
fixtures errored with "harness did not come up" while the same box with the
variable set passed every other estate test. These tests stub the harness with a
process that never serves and require each estate to give up after the
configured wait, not after the old fixed 60 s.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import test_estate_kill_watcher as kill_watcher  # noqa: E402
import test_upgrade_smoke_fixture as smoke  # noqa: E402

WAIT_S = 3
SLACK_S = 25  # far under the old fixed 60 s, far over the configured 3 s


@pytest.fixture
def silent_harness(tmp_path, monkeypatch):
    """A harness that never answers: it just sleeps (terminated by the estate on give-up)."""
    stub = tmp_path / "silent_harness.py"
    stub.write_text("import time\ntime.sleep(300)\n")
    monkeypatch.setenv("FIELD_TEST_HARNESS_WAIT", str(WAIT_S))
    monkeypatch.setattr(smoke, "HARNESS", stub)
    monkeypatch.setattr(kill_watcher, "HARNESS", stub)
    return stub


def test_upgrade_smoke_estate_gives_up_after_the_configured_wait(silent_harness, tmp_path):
    t0 = time.time()
    with pytest.raises(RuntimeError, match="did not come up"):
        smoke.UpgradedEstate(tmp_path, rosters=True)
    assert time.time() - t0 < WAIT_S + SLACK_S


def test_kill_watcher_estate_gives_up_after_the_configured_wait(silent_harness, tmp_path):
    t0 = time.time()
    with pytest.raises(RuntimeError, match="did not come up"):
        kill_watcher.Estate(tmp_path, secret=True)
    assert time.time() - t0 < WAIT_S + SLACK_S
