"""CLI (dry-run default, refusals), the manifest sketch (validates offline), and the DOA-roster consequence."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from deployment_agent import cli  # noqa: E402
from deployment_agent.actions import ADR_SCOPE, Action, ActionKind  # noqa: E402
from deployment_agent.manifest import FORBIDDEN_SCOPE, ManifestError, load_manifest  # noqa: E402
from deployment_agent.refuse import refuse  # noqa: E402

MANIFEST = ROOT / "manifests" / "deployment-agent.yaml"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


# ---- CLI ------------------------------------------------------------------------------------------------------


def test_plan_lists_the_steps_and_makes_no_provider_call():
    code, out, err = run("plan", "--target", "fly-app-a", "--manifest", str(MANIFEST))
    assert code == 0 and err == ""
    assert "planned -> minted -> installed -> verified -> old_revoked -> done" in out
    assert "REFUSED" not in out and "no provider call was made" in out
    assert "[placeholder]" in out  # ttl is not decided


def test_run_defaults_to_dry_run_and_says_it_is_a_simulation(tmp_path):
    code, out, err = run("run", "--target", "fly-app-a", "--journal-dir", str(tmp_path), "--manifest", str(MANIFEST))
    assert code == 0, err
    assert "SIMULATION" in out and "FAKE" in out and "done" in out
    assert (tmp_path / "journal" / "rotation-fly-app-a.jsonl").is_file()


def test_the_simulation_journal_holds_ids_only(tmp_path):
    run("run", "--target", "fly-app-a", "--journal-dir", str(tmp_path))
    text = (tmp_path / "journal" / "rotation-fly-app-a.jsonl").read_text(encoding="utf-8")
    assert "fakesecret" not in text
    for line in text.splitlines():
        assert set(json.loads(line)) <= {"seq", "ts", "target", "event", "state", "run_id", "cred_old", "cred_new",
                                          "snapshot", "reason", "ttl_days", "sha", "ref"}


@pytest.mark.parametrize("argv,needle", [
    (["run", "--no-dry-run"], "needs --manifest"),
    (["run", "--no-dry-run", "--manifest", "/no/such/manifest.yaml", "--i-have-a-provider"], "needs --manifest"),
    (["run", "--no-dry-run", "--manifest", str(MANIFEST)], "needs --i-have-a-provider"),
    (["run", "--no-dry-run", "--i-have-a-provider"], "needs --manifest"),
])
def test_non_dry_run_is_refused_without_a_manifest_and_the_explicit_flag(argv, needle):
    code, out, err = run(*argv)
    assert code == 2 and needle in err and out == ""


def test_non_dry_run_is_refused_even_with_both_because_no_provider_exists():
    code, out, err = run("run", "--no-dry-run", "--manifest", str(MANIFEST), "--i-have-a-provider",
                         "--target", "fly-app-a")
    assert code == 2 and "ADR-0079" in err and "no real provider" in err
    assert out == ""


def test_the_flag_changes_nothing_in_a_dry_run(tmp_path):
    a = run("run", "--target", "fly-app-a", "--journal-dir", str(tmp_path / "a"))
    b = run("run", "--target", "fly-app-a", "--i-have-a-provider", "--journal-dir", str(tmp_path / "b"))
    assert a[0] == b[0] == 0 and "SIMULATION" in b[1]


def test_a_bad_ttl_or_target_is_rejected():
    code, _, err = run("plan", "--target", "fly-app-a", "--ttl-days", "400", "--manifest", str(MANIFEST))
    assert code == 2 and "1..30" in err
    with pytest.raises(SystemExit):
        run("plan", "--target", "../etc")


def test_module_entry_point_runs(tmp_path):
    import subprocess

    r = subprocess.run([sys.executable, "-m", "deployment_agent", "plan", "--target", "x1"],
                       cwd=TOOLS, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "plan only" in r.stdout


# ---- manifest ---------------------------------------------------------------------------------------------------


def test_the_manifest_sketch_loads_and_its_scope_equals_the_adr_scope():
    m = load_manifest(MANIFEST)
    assert m.scope == ADR_SCOPE
    assert m.granted_by == "Don Hagell, Spin State Labs"
    assert m.local_sentinel and m.sentinel_max_age_s >= 1


def test_the_manifest_scope_omits_every_deliberately_absent_scope():
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert not set(doc["delegation"]["scope"]) & FORBIDDEN_SCOPE
    # and the refuse list agrees: each is refused even if a caller listed it in scope
    for value in FORBIDDEN_SCOPE:
        kind = ActionKind(value)
        assert refuse(Action(kind)) is not None


def test_delegation_expiry_is_at_most_30_days_from_the_adr_date():
    m = load_manifest(MANIFEST)
    assert (date.fromisoformat(m.expiry) - date(2026, 10, 23)).days <= 30


def test_every_figure_in_the_manifest_is_marked_as_a_placeholder():
    text = MANIFEST.read_text(encoding="utf-8")
    for needle in ("limit: 1 ", "sentinel_max_age_s: 300", 'expiry: "2026-11-22"'):
        line = next(ln for ln in text.splitlines() if needle in ln)
        assert "[placeholder]" in line, line


@pytest.mark.parametrize("edit,message", [
    (lambda d: d["delegation"]["scope"].append("edit manifest"), "deliberately-absent"),
    (lambda d: d["delegation"]["scope"].append("deploy anything"), "wider than the ADR"),
    (lambda d: d["enforcement"]["kill_switch"].pop("sentinel_max_age_s"), "sentinel_max_age_s"),
    (lambda d: d["enforcement"]["kill_switch"].pop("local_sentinel"), "local_sentinel"),
    (lambda d: d["enforcement"]["spend_cap"].update(on_breach="warn"), "halt"),
    (lambda d: d["delegation"].update(granted_by=" "), "granted_by"),
    (lambda d: d["agent"].update(name="other-agent"), "agent.name"),
])
def test_the_loader_rejects_a_manifest_that_widens_or_weakens_it(tmp_path, edit, message):
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    edit(doc)
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ManifestError, match=message):
        load_manifest(p)


def test_the_manifest_validates_with_field_core_offline():
    """The FIELD validator (field_core, no network). VALID_WITH_WARNINGS is expected: the only warning is that a
    30-day delegation expiry is 'near-term'."""
    pytest.importorskip("field_core")
    from field_core.validation import ValidationStatus, validate_manifest_file

    result = validate_manifest_file(MANIFEST, now=None)
    assert result.status is not ValidationStatus.INVALID, result.critical_gaps
    assert result.critical_gaps == []
    assert result.sections_present and all(result.sections_present.values())
    assert [w for w in result.warnings if "near-term" not in w] == []


def test_the_manifest_is_listed_in_the_manifests_readme():
    assert "deployment-agent.yaml" in (ROOT / "manifests" / "README.md").read_text(encoding="utf-8")


# ---- DOA roster consequence -------------------------------------------------------------------------------------------


def test_the_roster_generator_needs_no_new_grantor_row_only_a_wider_existing_one(tmp_path):
    """Run the generator on COPIES (a scratch directory; no live roster is touched)."""
    pytest.importorskip("delegation_authority")
    import generate_doa_roster as gen

    mdir = tmp_path / "manifests"
    mdir.mkdir()
    for name in ("ssl-invoicing-agent.yaml", "ssl-timekeeping-agent.yaml", "deployment-agent.yaml"):
        shutil.copy(ROOT / "manifests" / name, mdir / name)
    agents = ["ssl-invoicing-agent", "ssl-timekeeping-agent", "ssl-deployment-agent"]
    files = {"ssl-deployment-agent": "deployment-agent"}
    registry = [{"agent_id": a, "name": a, "owner": "Don Hagell", "domain": "ops", "status": "active",
                 "manifest_ref": f"/data/manifests/{files.get(a, a)}.yaml"} for a in agents]
    reg = tmp_path / "agents.json"
    reg.write_text(json.dumps(registry), encoding="utf-8")
    out_path = tmp_path / "doa-roster.yaml"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        code = gen.main(["--registry", str(reg), "--manifests", str(mdir), "--out", str(out_path)])
    assert code == 0
    roster = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    rows = {g["grantor"]: g for g in roster["grantors"]}
    assert set(rows) == {"Don Hagell, Spin State Labs"}  # no new grantor row
    assert ADR_SCOPE <= set(rows["Don Hagell, Spin State Labs"]["allowed_scope"])  # the existing row widens by six scopes
    assert "max_spend_usd" not in rows["Don Hagell, Spin State Labs"]  # generator would overwrite a hand-set cap


def test_manifest_deny_patterns_cover_the_command_aliases():
    import re

    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    pats = [re.compile(p, re.IGNORECASE) for p in doc["enforcement"]["irreversible_actions"]["deny_patterns"]]
    cmds = [
        "flyctl destroy x", "fly destroy x -y", "fly vol delete v", "fly volume delete v", "fly machine destroy m",
        "fly apps destroy x", "docker -H tcp://x system prune", "docker network prune", "docker buildx prune",
        "docker volume rm v", "docker volume prune", "git -C . push", "git -c k=v push", '"docker" "system" "prune"',
        "git push --force",
    ]
    missed = [c for c in cmds if not any(p.search(c) for p in pats)]
    assert missed == []
