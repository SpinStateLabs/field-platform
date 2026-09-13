"""Local twin of CI's compose-upgrade-smoke job — everything except docker.

The CI job cannot run on rog-command (no docker there by rule), so the parts
that are not docker are proven here with the same files the job uses:
integration/demo/fixtures/upgrade-smoke/make_fixture.py writes the old-schema
/data, tools/volume_admin.py seeds the manifests volume from it, the REAL
services start on it (estate_harness.py, every create_app under the proxy
prefixes) with a random perimeter secret and both rosters armed, and the job's
own upgrade_flow.py and `estate_probe.py health --expect-perimeter
--expect-build-sha` must pass. Negative controls show the flow FAILS when the
rosters are not armed and when the fixture's history is not what was pinned,
and that EVERY other flow check can fail: one estate_harness fault per check
(perimeter off, an unmigrated registry row, a BLOCK for a ledgered ALLOW, a
segmented /verify, a check ledgered twice) turns exactly that check, and no
other, into a FAIL.

What this does NOT prove (only the CI job can): the Dockerfile ARG -> ENV
wiring, the compose volume mounts and their :ro flag, manifests-admin running
before the services, and the Caddy route map.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
FIXTURE = REPO / "integration" / "demo" / "fixtures" / "upgrade-smoke"
HARNESS = Path(__file__).with_name("estate_harness.py")
sys.path.insert(0, str(TOOLS))

import estate_probe  # noqa: E402
import volume_admin  # noqa: E402
from sealed_ledger.store import LedgerStore, journal_path_for  # noqa: E402

BUILD_SHA = "9b2f4c1e8d7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c"
OLD_COLUMNS = ["agent_id", "name", "owner", "domain", "manifest_ref", "status", "created_at", "updated_at"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"upgrade_smoke_{name}", FIXTURE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_fixture = _load("make_fixture")
upgrade_flow = _load("upgrade_flow")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _capture(fn, *args) -> tuple[int, str]:
    out = io.StringIO()
    saved = sys.stdout, sys.stderr
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = fn(*args)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    sys.stdout, sys.stderr = saved  # estate_probe may wrap them in its redactor
    return code, out.getvalue()


class UpgradedEstate:
    """The fixture /data, seeded manifests volume, and the real services on it."""

    def __init__(self, root: Path, *, rosters: bool):
        self.data = root / "data"
        self.pin = make_fixture.write_fixture(self.data)
        self.pin_file = root / "pin.json"
        self.pin_file.write_text(json.dumps(self.pin) + "\n")
        self.volume = root / "field-manifests"
        self.volume.mkdir()
        assert volume_admin.seed(self.data / "manifests", self.volume) == 0
        # the frozen field-data copy is not what readers use after the upgrade
        shutil.rmtree(self.data / "manifests")
        self.manifest_ref = str(self.volume / "upgrade-smoke-agent.yaml")
        self.secret = secrets.token_hex(32)
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = dict(os.environ, FIELD_SHARED_SECRET=self.secret, FIELD_BUILD_SHA=BUILD_SHA)
        for var in ("FIELD_DOA_ROSTER", "FIELD_LIFECYCLE_ROSTER"):
            env.pop(var, None)
        if rosters:
            env["FIELD_DOA_ROSTER"] = str(self.data / "doa-roster.yaml")
            env["FIELD_LIFECYCLE_ROSTER"] = str(self.data / "owners.csv")
        self.proc = subprocess.Popen([sys.executable, str(HARNESS), str(self.port), str(self.data), "--secret"],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"harness exited early: {self.proc.returncode}")
            try:
                urllib.request.urlopen(f"{self.base}/ledger/health", timeout=2).read()
                return
            except OSError:
                time.sleep(0.3)
        self.close()
        raise RuntimeError("harness did not come up")

    def flow(self, monkeypatch, pin_file: Path | None = None, agent: str | None = None) -> tuple[int, str]:
        monkeypatch.setenv("FIELD_SHARED_SECRET", self.secret)
        return _capture(upgrade_flow.main, ["--base", self.base, "--pin", str(pin_file or self.pin_file),
                                            "--manifest-ref", self.manifest_ref]
                        + (["--agent", agent] if agent else []))

    def faults(self, *on: str) -> None:
        req = urllib.request.Request(f"{self.base}/__fault", data=json.dumps({"on": list(on)}).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req, timeout=10).read())["on"] == sorted(on)

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=20)


@pytest.fixture(scope="module")
def armed(tmp_path_factory):
    e = UpgradedEstate(tmp_path_factory.mktemp("armed"), rosters=True)
    try:
        yield e
    finally:
        e.close()


# --- the fixture is really the old schema ------------------------------------------------


def test_the_fixture_is_a_pre_c2_single_file_ledger_and_a_pre_v12_registry(tmp_path):
    data = tmp_path / "data"
    pin = make_fixture.write_fixture(data)
    ledger = data / "ledger" / "events.jsonl"
    assert not journal_path_for(ledger).exists()
    # a pre-C2 ledger directory: the one file, no C2 writer lock file
    assert sorted(p.name for p in ledger.parent.iterdir()) == ["events.jsonl"]
    verification = LedgerStore(ledger).verify()
    assert verification.ok and verification.length == pin["event_count"] == 5
    assert verification.segments is None  # single-file: no C2 keys
    assert sorted(p.name for p in ledger.parent.iterdir()) == ["events.jsonl"]  # reading wrote nothing
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[pin["head_index"]])["hash"] == pin["head_hash"]
    conn = sqlite3.connect(str(data / "registry" / "agents.sqlite3"))
    try:
        assert [r[1] for r in conn.execute("PRAGMA table_info(agents)")] == OLD_COLUMNS
    finally:
        conn.close()
    assert (data / "manifests" / "upgrade-smoke-agent.yaml").is_file()
    assert (data / "doa-roster.yaml").is_file() and (data / "owners.csv").is_file()


def test_the_fixture_refuses_to_write_over_existing_estate_data(tmp_path):
    data = tmp_path / "data"
    (data / "ledger").mkdir(parents=True)
    (data / "ledger" / "events.jsonl").write_text("real estate history\n")
    code, _ = _capture(make_fixture.main, [str(data)])
    assert code == 2
    assert (data / "ledger" / "events.jsonl").read_text() == "real estate history\n"
    assert not (data / "registry").exists()


# --- the job's flow passes on the upgraded estate ------------------------------------------


def test_the_upgrade_flow_passes_with_the_secret_set_and_both_rosters_armed(armed, monkeypatch):
    code, out = armed.flow(monkeypatch)
    assert code == 0, out
    assert armed.secret not in out
    assert "[FAIL]" not in out and "/sentinel/check upgrade.probe ALLOW" in out


def test_the_job_health_step_passes_on_the_upgraded_estate(armed, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", armed.secret)
    estate_probe.RESULTS.clear()
    code, out = _capture(estate_probe.main, ["--base", armed.base, "health", "--expect-perimeter",
                                             "--expect-build-sha", BUILD_SHA])
    assert code == 0, out
    assert armed.secret not in out


def test_the_flow_fails_when_the_fixture_history_is_not_the_pinned_one(armed, monkeypatch, tmp_path):
    forged = tmp_path / "pin.json"
    forged.write_text(json.dumps(dict(armed.pin, head_hash="e" * 64)) + "\n")
    code, out = armed.flow(monkeypatch, forged)
    assert code == 1
    assert "[FAIL] fixture head eeeeeeeeeeeeeeee" in out


def test_the_flow_refuses_without_a_secret(armed, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    code, _ = _capture(upgrade_flow.main, ["--base", armed.base, "--pin", str(armed.pin_file)])
    assert code == 2


def test_the_flow_fails_when_the_rosters_are_not_armed(tmp_path, monkeypatch):
    e = UpgradedEstate(tmp_path, rosters=False)
    try:
        code, out = e.flow(monkeypatch)
    finally:
        e.close()
    assert code == 1
    assert "[FAIL] lifecycle roster armed" in out
    assert "[FAIL] DOA roster armed: off-roster mint 403 D.grantor" in out
    assert "[FAIL] exactly one delegation.mint for upgrade-smoke-agent, doa_checked=true" in out


# --- every flow check can fail -------------------------------------------------------------

#: (estate_harness fault, the ONE upgrade_flow.py check it must turn into a FAIL)
FLOW_FAULTS = [
    ("no_authn_registry", "perimeter on: unauthenticated POST /registry/agents is 401"),
    ("registry_unmigrated_rows", "pre-v1.2 registry row legacy-fixture-agent served with migrated attested_at=None"),
    ("sentinel_allow_as_block", "/sentinel/check upgrade.probe ALLOW"),
    ("ledger_verify_segmented", "ledger still one file: /verify carries no segments keys"),
    ("sentinel_check_ledgered_twice", "exactly one conformance.allow for upgrade-smoke-sentinel-check-ledgered-twice"),
]


def _fail_lines(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if "[FAIL]" in line]


def test_a_fresh_agent_passes_the_flow_on_an_estate_that_already_ran_it(armed, monkeypatch):
    """The control for the fault runs below: a second agent id on the same
    estate passes every check, so a FAIL there is the fault's, not reuse's."""
    for agent in ("upgrade-smoke-control-1", "upgrade-smoke-control-2"):
        code, out = armed.flow(monkeypatch, agent=agent)
        assert code == 0, out
        assert _fail_lines(out) == [] and "15/15 checks passed" in out


@pytest.mark.parametrize("fault, failing", FLOW_FAULTS, ids=[f for f, _ in FLOW_FAULTS])
def test_each_flow_check_fails_on_the_estate_fault_it_exists_to_catch(armed, monkeypatch, fault, failing):
    armed.faults(fault)
    try:
        code, out = armed.flow(monkeypatch, agent=f"upgrade-smoke-{fault.replace('_', '-')}")
    finally:
        armed.faults()
    assert code == 1, out
    fails = _fail_lines(out)
    assert len(fails) == 1 and fails[0].startswith(f"[FAIL] {failing}"), out
    assert armed.secret not in out
