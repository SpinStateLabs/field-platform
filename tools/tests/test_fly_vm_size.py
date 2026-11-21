"""T9: integration/fly/fly.toml [[vm]] is what ``fly deploy -c`` applies, so it must say the size the estate
actually runs (force-field-sandbox: 4 shared CPUs, 2048 MB). A toml that still said ``cpus = 1`` would shrink the
resized machine back at the next deploy. Nothing else in the file is pinned here."""

from __future__ import annotations

import tomllib
from pathlib import Path

FLY_TOML = Path(__file__).resolve().parents[2] / "integration" / "fly" / "fly.toml"


def _vm() -> dict:
    vms = tomllib.loads(FLY_TOML.read_text(encoding="utf-8"))["vm"]
    assert len(vms) == 1, "one [[vm]] block: the estate is a single machine"
    return vms[0]


def test_vm_is_four_shared_cpus_and_two_gigabytes():
    vm = _vm()
    assert vm["cpu_kind"] == "shared"
    assert vm["cpus"] == 4
    assert vm["memory"] == "2gb"
