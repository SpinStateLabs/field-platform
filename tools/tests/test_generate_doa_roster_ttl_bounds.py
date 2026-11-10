"""S3-22: generate_doa_roster --max-ttl-days is bounded to 1..3650. It was a bare int with only DoaRoster's gt=0
behind it, so 10**12 wrote a roster whose mint would later overflow timedelta. A value outside the bound is a
Refused (exit 2, nothing written, the message names the flag and the range, not the value or any path), checked
BEFORE any input file is read."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import generate_doa_roster as gen  # noqa: E402
from delegation_authority.doa import load_roster  # noqa: E402
from field_core.templates_api import template_data  # noqa: E402


def _estate(tmp_path: Path) -> Path:
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    data = template_data("default")
    data["agent"]["name"] = "inv"
    data["identity"]["principal"] = "Don Co"
    data["delegation"]["granted_by"] = "Don Co"
    data["delegation"]["scope"] = ["a"]
    data["delegation"]["expiry"] = "2027-06-30"
    (mdir / "inv.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return mdir


def _run(tmp_path: Path, *extra: str) -> tuple[int, str, Path]:
    mdir = _estate(tmp_path)
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps([{"agent_id": "inv", "name": "inv", "owner": "x", "domain": "d",
                                     "status": "active", "manifest_ref": "/data/manifests/inv.yaml"}]),
                        encoding="utf-8")
    out = tmp_path / "out" / "doa-roster.yaml"
    se = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
        code = gen.main(["--registry", str(registry), "--manifests", str(mdir), "--out", str(out), *extra])
    return code, se.getvalue(), out


@pytest.mark.parametrize("days", ["0", "-1", "3651", str(10**12)])
def test_a_value_outside_1_to_3650_is_refused_and_nothing_is_written(tmp_path, days):
    code, err, out = _run(tmp_path, "--max-ttl-days", days)
    assert code == 2
    assert err.startswith("REFUSED (nothing written)") and "--max-ttl-days" in err and "3650" in err
    assert not out.exists() and not out.parent.exists()
    fixed = "--max-ttl-days must be an integer from 1 to 3650"
    assert days not in err.replace(fixed, "") and str(tmp_path) not in err   # neither the value nor any path


@pytest.mark.parametrize("days", [1, 3650])
def test_the_bounds_themselves_write_a_roster_the_service_loads(tmp_path, days):
    code, err, out = _run(tmp_path, "--max-ttl-days", str(days))
    assert code == 0, err
    roster = load_roster(out)
    assert {g.max_ttl_days for g in roster.grantors} == {days}


def test_the_default_is_unchanged(tmp_path):
    code, err, out = _run(tmp_path)
    assert code == 0, err
    assert {g.max_ttl_days for g in load_roster(out).grantors} == {30}


def test_the_bound_is_checked_before_any_input_is_read(tmp_path):
    se = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(se):
        code = gen.main(["--registry", str(tmp_path / "missing.json"), "--manifests", str(tmp_path / "nope"),
                         "--out", str(tmp_path / "o.yaml"), "--max-ttl-days", "99999"])
    assert code == 2 and "--max-ttl-days" in se.getvalue() and "not a directory" not in se.getvalue()
    assert not (tmp_path / "o.yaml").exists()


def test_the_generator_bound_is_inside_the_services_own_bound():
    assert gen.MAX_TTL_DAYS == 3650 and 1 <= gen.MAX_TTL_DAYS <= 999_999_999
