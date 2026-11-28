"""The ledger readers and the kill-switch's fixed-shape fallback row.

``tools/rollback_read_check.py`` exercises only the event types a release ADDS, so a new payload shape under an existing
type is not covered by it. The kill-switch writes such a shape when the ledger refuses a row: the same ``kill.*`` type
with only the allowlisted keys. This runs the tool's own writer and readers, on this tree, over that shape under every
``kill.*`` type below, with an agent id and without one."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import rollback_read_check as rrc  # noqa: E402
from kill_switch import api as kill_api  # noqa: E402

TYPES = ["kill.agent", "kill.agent.failed", "kill.domain", "kill.revive", "kill.drill.start", "kill.drill.refused",
         "kill.drill.complete", "kill.drill.restore_skipped", "kill.drill.restore_failed", "kill.endpoint_called",
         "kill.endpoint_failed", "kill.endpoint_skipped"]
#: the two types the status-pairing reader counts as the record behind a registry change to "killed"
PAIRING_TYPES = {"kill.agent", "kill.drill.start"}
SHAPE = {"operator": "rollback-check", "reason": kill_api.LEDGER_FALLBACK_REASON, "refused_status": 422,
         "operator_id_authenticated": "rollback-check", "operator_key_fp": "0f0f0f0f"}

#: runs one role of the tool in its own process with the fixtures replaced; the baseline rows use two types that are
#: not under test, so each tested type occurs exactly once
RUNNER = """
import json, sys
from pathlib import Path
import rollback_read_check as rrc
role, tree, work, spec = sys.argv[1], sys.argv[2], Path(sys.argv[3]), json.loads(sys.argv[4])
agent = rrc.AGENT if spec["agent"] else None
rrc.FIXTURES = {t: (agent, dict(spec["shape"])) for t in spec["types"]}
rrc.BASELINE = [("registry.registered", rrc.AGENT, {"operator": "rollback-check"}),
                ("delegation.mint", rrc.AGENT, {"operator": "rollback-check"})]
run = rrc.role_write if role == "write" else rrc.role_read
sys.exit(run(tree, work, spec["types"]))
"""


def _run_role(role: str, work: Path, spec: dict) -> None:
    keep = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG") if k in os.environ}
    roots = [str(p) for p in rrc.source_roots(REPO)] + [str(REPO / "tools")]
    (work / "manifests").mkdir(parents=True, exist_ok=True)
    env = {**keep, "HOME": str(work), "PYTHONPATH": os.pathsep.join(roots), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONUTF8": "1", "FIELD_DATA_DIR": str(work), "FIELD_MANIFEST_DIR": str(work / "manifests"),
           "NO_PROXY": "*"}
    done = subprocess.run([sys.executable, "-c", RUNNER, role, str(REPO), str(work), json.dumps(spec)], env=env,
                          cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert done.returncode == 0, done.stderr[-3000:]


def _report(tmp_path: Path, agent: bool) -> dict:
    spec = {"agent": agent, "shape": SHAPE, "types": TYPES}
    _run_role("write", tmp_path, spec)
    _run_role("read", tmp_path, spec)
    return json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))


def test_the_shape_under_test_is_the_one_the_kill_switch_writes():
    assert tuple(SHAPE) == kill_api.LEDGER_FALLBACK_KEYS


def test_every_reader_takes_a_fallback_row_that_names_an_agent(tmp_path):
    report = _report(tmp_path, agent=True)
    assert {name: cell["status"] for name, cell in report["whole"].items()} == dict.fromkeys(report["whole"], "OK")
    for event_type in TYPES:
        cells = {reader: cell["status"] for reader, cell in report["types"][event_type].items()}
        expected = dict.fromkeys(rrc.READERS, "OK")
        if event_type in PAIRING_TYPES:
            # correct for these two: the kill-switch writes the row only after the kill or drill start happened
            expected["status_pairing"] = "REFUSED"
        assert cells == expected, (event_type, report["types"][event_type])


@pytest.mark.parametrize("reader", ["parse", "ledger_filter", "ops_console"])
def test_a_fallback_row_without_an_agent_id_is_read(tmp_path, reader):
    report = _report(tmp_path, agent=False)
    assert {name: cell["status"] for name, cell in report["whole"].items()} == dict.fromkeys(report["whole"], "OK")
    for event_type in TYPES:
        assert report["types"][event_type][reader]["status"] == "OK", (event_type, report["types"][event_type])
        # an agent replay has nothing to show for a row with no agent
        assert report["types"][event_type]["replay"]["status"] == "SKIPPED", event_type
