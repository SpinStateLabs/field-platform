"""Tests for tools/topology_lint.py: fixtures plus the real shipped descriptors."""

from __future__ import annotations

import datetime
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent
_spec = importlib.util.spec_from_file_location("topology_lint", TOOLS / "topology_lint.py")
lint = importlib.util.module_from_spec(_spec)
sys.modules["topology_lint"] = lint  # dataclasses resolves cls.__module__ here
_spec.loader.exec_module(lint)  # type: ignore[union-attr]

BASE_OPEN = """
x-service: &svc
  environment: &env
    FIELD_DOA_ROSTER: ${FIELD_DOA_ROSTER:-}
    FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:-}
services:
  delegation:
    <<: *svc
    environment: *env
"""

GB10_OPEN = """
services:
  witness:
    environment:
      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:-}
"""

GB10_ARMED = """
services:
  witness:
    environment:
      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set the perimeter secret}
      FIELD_DOA_ROSTER: /data/doa-roster.yaml
  delegation:
    environment:
      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set the perimeter secret}
      FIELD_DOA_ROSTER: /data/doa-roster.yaml
"""

ENTRY_OPEN = (
    'export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-}"\n'
    'export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-}"\n'
)
ENTRY_ARMED = (
    'export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-/data/doa-roster.yaml}"\n'
    ': "${FIELD_SHARED_SECRET:?FIELD_SHARED_SECRET must be set}"\n'
)


def make_tree(tmp: Path, *, base=BASE_OPEN, gb10=GB10_OPEN, entry=ENTRY_OPEN, toml="[env]\n", extra=None) -> Path:
    files = {
        "integration/demo/docker-compose.yml": base,
        "integration/demo/docker-compose.gb10.yml": gb10,
        "integration/fly/entrypoint.sh": entry,
        "integration/fly/fly.toml": toml,
    }
    files.update(extra or {})
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp


def run(root: Path, allow=None, today=None):
    reports = lint.analyse(root)
    allowlist = lint.load_allowlist(allow) if allow else []
    errors, notes = lint.evaluate(reports, allowlist, lint.unclassified_descriptors(root), today)
    return reports, errors, notes


def status(reports, topo, var):
    return next(r for r in reports if r.topology.id == topo).vars[var].status


# --- classify_value --------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("${FIELD_SHARED_SECRET:-}", lint.EMPTY),
        ('"${FIELD_SHARED_SECRET:-}"', lint.EMPTY),
        ("", lint.EMPTY),
        (None, lint.EMPTY),
        ("${FIELD_SHARED_SECRET:?set it}", lint.ARMED),
        ("${FIELD_SHARED_SECRET:-fallback}", lint.ARMED),
        ("/data/doa-roster.yaml", lint.ARMED),
        ("${FIELD_SHARED_SECRET}", lint.OPERATOR),
        ("$(cat /run/secret)", lint.OPERATOR),
    ],
)
def test_classify_value(raw, expected):
    assert lint.classify_value(raw, "FIELD_SHARED_SECRET") == expected


# --- fixtures --------------------------------------------------------------

def test_passing_fixture(tmp_path):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED)
    reports, errors, notes = run(root)
    assert errors == [] and notes == []
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.ARMED
    assert status(reports, "fly", "FIELD_DOA_ROSTER") == lint.ARMED
    # The demo topology stays open and that is not a finding.
    assert status(reports, "demo-compose", "FIELD_SHARED_SECRET") == lint.EMPTY


def test_failing_fixture_names_each_deployed_pair_and_never_the_demo(tmp_path):
    root = make_tree(tmp_path)
    _, errors, _ = run(root)
    failed = {e.split()[1] + " " + e.split()[3] for e in errors}
    assert failed == {
        "gb10 FIELD_SHARED_SECRET", "gb10 FIELD_DOA_ROSTER",
        "fly FIELD_SHARED_SECRET", "fly FIELD_DOA_ROSTER",
    }
    assert not any("demo-compose" in e for e in errors)


def test_fly_toml_env_arms_a_roster_and_one_unarmed_var_still_fails(tmp_path):
    root = make_tree(tmp_path, gb10=GB10_ARMED, toml='[env]\nFIELD_DOA_ROSTER = "/data/r.yaml"\n')
    reports, errors, _ = run(root)
    assert status(reports, "fly", "FIELD_DOA_ROSTER") == lint.ARMED
    assert errors == ["FAIL fly (deployed) FIELD_SHARED_SECRET is empty-default, not armed"]


def test_one_weak_service_weakens_the_topology(tmp_path):
    weak = GB10_ARMED + "  canary:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:-}\n"
    root = make_tree(tmp_path, gb10=weak, entry=ENTRY_ARMED)
    reports, errors, _ = run(root)
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY
    assert len(errors) == 1


def test_compose_only_tags_are_accepted(tmp_path):
    tagged = GB10_ARMED + '  proxy:\n    ports: !override ["18080:8080"]\n'
    root = make_tree(tmp_path, gb10=tagged, entry=ENTRY_ARMED)
    _, errors, _ = run(root)
    assert errors == []


def test_unclassified_descriptor_fails(tmp_path):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED,
                     extra={"integration/new/docker-compose.prod.yml": "services: {}\n"})
    _, errors, _ = run(root)
    assert errors == [
        "unclassified descriptor integration/new/docker-compose.prod.yml: "
        "add it to a Topology (demo or deployed) in tools/topology_lint.py"
    ]


def test_missing_declared_descriptor_is_an_error(tmp_path):
    root = make_tree(tmp_path)
    (root / "integration/fly/fly.toml").unlink()
    with pytest.raises(SystemExit):
        lint.analyse(root)


# --- allowlist -------------------------------------------------------------

TODAY = datetime.date(2026, 10, 23)


def _allow(tmp_path, entries, verified_on="2026-10-23", verified_by="tester"):
    p = tmp_path / "allow.yaml"
    lines = ["exceptions:"]
    for t, v, reason in entries:
        lines += [f"  - topology: {t}", f"    var: {v}", f"    reason: {reason}"]
        if verified_on is not None:
            lines.append(f"    verified_on: {verified_on}")
        if verified_by is not None:
            lines.append(f"    verified_by: {verified_by}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_allowlist_waives_exactly_the_listed_pairs(tmp_path):
    root = make_tree(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "presence checked")])
    _, errors, notes = run(root, allow, today=TODAY)
    assert len(errors) == 3 and not any("gb10 (deployed) FIELD_SHARED" in e for e in errors)
    assert notes == ["ALLOWED gb10 FIELD_SHARED_SECRET is empty-default: presence checked"]


# --- allowlist expiry (verified_on) -----------------------------------------

def _only_gb10_secret_failing(tmp_path):
    """Tree where exactly gb10/FIELD_SHARED_SECRET fails, so one entry is the whole allowlist."""
    gb10 = (GB10_OPEN + "      FIELD_DOA_ROSTER: /data/doa-roster.yaml\n"
            "  delegation:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:-}\n"
            "      FIELD_DOA_ROSTER: /data/doa-roster.yaml\n")
    return make_tree(tmp_path, gb10=gb10, entry=ENTRY_ARMED)


def test_fresh_allowlist_entry_passes(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], verified_on="2026-10-23")
    _, errors, notes = run(root, allow, today=TODAY)
    assert errors == [] and len(notes) == 1


def test_entry_exactly_at_the_limit_still_passes(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    on = TODAY - datetime.timedelta(days=lint.ALLOWLIST_MAX_AGE_DAYS)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], verified_on=on.isoformat())
    _, errors, _ = run(root, allow, today=TODAY)
    assert errors == []


def test_entry_31_days_old_fails(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    on = TODAY - datetime.timedelta(days=31)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], verified_on=on.isoformat())
    _, errors, _ = run(root, allow, today=TODAY)
    assert len(errors) == 1
    assert "expired" in errors[0] and "31 days old" in errors[0] and "gb10 FIELD_SHARED_SECRET" in errors[0]


def test_entry_missing_verified_on_fails(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], verified_on=None)
    _, errors, _ = run(root, allow, today=TODAY)
    assert len(errors) == 1 and "has no verified_on" in errors[0]


def test_entry_with_bad_or_future_verified_on_or_no_verified_by_fails(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    for kwargs, needle in [
        ({"verified_on": "yesterday"}, "unparseable verified_on"),
        ({"verified_on": "2026-11-01"}, "in the future"),
        ({"verified_by": None}, "no verified_by"),
    ]:
        allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], **kwargs)
        _, errors, _ = run(root, allow, today=TODAY)
        assert len(errors) == 1 and needle in errors[0], (kwargs, errors)


def test_cli_today_flag_makes_a_stale_entry_fail_the_run(tmp_path, capsys):
    root = _only_gb10_secret_failing(tmp_path / "t")
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")])
    base = ["--root", str(root), "--allowlist", str(allow)]
    assert lint.main(base + ["--today", "2026-10-23"]) == 0
    assert lint.main(base + ["--today", "2026-11-23"]) == 1
    assert "expired" in capsys.readouterr().out


def test_stale_allowlist_entry_fails(tmp_path):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r"),
                              ("nowhere", "FIELD_DOA_ROSTER", "x")])
    _, errors, _ = run(root, allow, today=TODAY)
    assert any("gb10 FIELD_SHARED_SECRET is no longer a failing pair" in e for e in errors)
    assert any("unknown topology 'nowhere'" in e for e in errors)


def test_allowlist_entry_without_reason_is_rejected(tmp_path):
    p = tmp_path / "a.yaml"
    p.write_text("exceptions:\n  - topology: fly\n    var: FIELD_DOA_ROSTER\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        lint.load_allowlist(p)


def test_allowlisting_the_demo_does_not_hide_a_deployed_topology(tmp_path):
    # Classification is code: an allowlist entry for the demo id waives nothing.
    root = make_tree(tmp_path)
    allow = _allow(tmp_path, [("demo-compose", "FIELD_SHARED_SECRET", "x")])
    _, errors, _ = run(root, allow, today=TODAY)
    assert sum(e.startswith("FAIL") for e in errors) == 4
    assert any("stale allowlist entry: demo-compose" in e for e in errors)


# --- CLI -------------------------------------------------------------------

def test_cli_exit_codes(tmp_path, capsys):
    ok = make_tree(tmp_path / "ok", gb10=GB10_ARMED, entry=ENTRY_ARMED)
    assert lint.main(["--root", str(ok)]) == 0
    bad = make_tree(tmp_path / "bad")
    assert lint.main(["--root", str(bad)]) == 1
    assert "RESULT: FAIL" in capsys.readouterr().out
    assert lint.main(["--root", str(tmp_path / "empty")]) == 2


# --- the real shipped files -------------------------------------------------

def test_real_descriptors_status_is_pinned():
    """Pin what the shipped files actually say, so a change shows up as a diff.

    Today both deployed topologies default both variables to empty. When a
    descriptor is made fail-closed this test must be updated together with
    tools/topology_lint_allowlist.yaml.
    """
    reports = lint.analyse(REPO)
    got = {(r.topology.id, v): x.status for r in reports for v, x in r.vars.items()}
    assert got == {
        ("demo-compose", "FIELD_SHARED_SECRET"): lint.EMPTY,
        ("demo-compose", "FIELD_DOA_ROSTER"): lint.EMPTY,
        ("gb10", "FIELD_SHARED_SECRET"): lint.EMPTY,
        ("gb10", "FIELD_DOA_ROSTER"): lint.EMPTY,
        ("fly", "FIELD_SHARED_SECRET"): lint.EMPTY,
        ("fly", "FIELD_DOA_ROSTER"): lint.EMPTY,
    }


def test_real_descriptors_are_all_classified():
    assert lint.unclassified_descriptors(REPO) == []


def test_real_descriptors_pass_only_through_the_allowlist():
    """Clean with the committed allowlist; the four findings fail without it."""
    # Pinned clock: the committed entries are dated 2026-10-23 and expire by
    # design; this test checks the waiver logic, not the wall clock.
    assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 0
    reports = lint.analyse(REPO)
    errors, _ = lint.evaluate(reports, [], [])
    assert len(errors) == 4 and all(e.startswith("FAIL") for e in errors)


def test_committed_allowlist_records_evidence_and_verification():
    entries = lint.load_allowlist(TOOLS / "topology_lint_allowlist.yaml")
    assert len(entries) == 4
    for e in entries:
        assert "known gap, tracked" not in e["reason"]
        assert "values never read" in e["reason"] and "2026-10-23" in e["reason"]
        assert lint._parse_verified_on(e["verified_on"]) == datetime.date(2026, 10, 23)
        assert "presence check" in e["verified_by"] and "operator to re-confirm" in e["verified_by"]
        assert str(e.get("comment", "")).strip()


# --- review findings: compose tag/semantic handling (group A) ----------------

ARMED_BASE = """
services:
  delegation:
    command: delegation serve --host 0.0.0.0 --port 8003
    environment:
      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}
      FIELD_DOA_ROSTER: /data/doa-roster.yaml
"""


def _not_armed(reports, topo, var):
    return status(reports, topo, var) != lint.ARMED


def test_reset_tag_removes_the_variable_and_is_never_armed(tmp_path):
    # `!reset null` used to be read as the string "null", which classified as armed.
    gb10 = "services:\n  delegation:\n    environment:\n      FIELD_SHARED_SECRET: !reset null\n"
    root = make_tree(tmp_path, base=ARMED_BASE, gb10=gb10, entry=ENTRY_ARMED)
    reports, errors, _ = run(root)
    assert _not_armed(reports, "gb10", "FIELD_SHARED_SECRET")
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") == lint.ARMED
    assert any(e.startswith("FAIL gb10 (deployed) FIELD_SHARED_SECRET") for e in errors)


def test_override_tag_replaces_the_whole_environment_map(tmp_path):
    keep = "services:\n  delegation:\n    environment:\n      OTHER: x\n"
    gone = "services:\n  delegation:\n    environment: !override\n      OTHER: x\n"
    # control: a plain override file merges key by key and the base stays armed
    reports, errors, _ = run(make_tree(tmp_path / "keep", base=ARMED_BASE, gb10=keep, entry=ENTRY_ARMED))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.ARMED and errors == []
    # !override drops the base map, so both variables are no longer set
    reports, errors, _ = run(make_tree(tmp_path / "gone", base=ARMED_BASE, gb10=gone, entry=ENTRY_ARMED))
    assert _not_armed(reports, "gb10", "FIELD_SHARED_SECRET") and _not_armed(reports, "gb10", "FIELD_DOA_ROSTER")
    assert sum(e.startswith("FAIL gb10") for e in errors) == 2


def test_bare_list_entry_is_a_host_passthrough_not_empty(tmp_path):
    base = "services:\n  delegation:\n    environment:\n      - FIELD_SHARED_SECRET\n      - FIELD_DOA_ROSTER=\n"
    root = make_tree(tmp_path, base=base, gb10="services: {}\n", entry=ENTRY_ARMED)
    reports, _, _ = run(root)
    assert status(reports, "demo-compose", "FIELD_SHARED_SECRET") == lint.OPERATOR
    assert status(reports, "demo-compose", "FIELD_DOA_ROSTER") == lint.EMPTY  # `VAR=` is an explicit empty


@pytest.mark.parametrize("bad", ['"just a string"', "42", "true"])
def test_environment_of_the_wrong_type_is_a_descriptor_error(tmp_path, bad):
    base = f"services:\n  delegation:\n    environment: {bad}\n"
    root = make_tree(tmp_path, base=base)
    with pytest.raises(SystemExit):
        lint.analyse(root)
    assert lint.main(["--root", str(root)]) == 2


@pytest.mark.parametrize(
    "extra,needle",
    [
        ("    env_file: .env\n", "env_file"),
        ("    extends:\n      file: other.yml\n      service: a\n", "extends"),
    ],
)
def test_env_file_and_extends_fail_in_a_deployed_topology(tmp_path, extra, needle):
    gb10 = GB10_ARMED + "  extra:\n    image: x\n" + extra
    root = make_tree(tmp_path, gb10=gb10, entry=ENTRY_ARMED)
    _, errors, _ = run(root)
    assert len(errors) == 1 and errors[0].startswith("FAIL gb10 (deployed)") and needle in errors[0]


def test_top_level_include_fails_in_a_deployed_topology(tmp_path):
    root = make_tree(tmp_path, gb10="include:\n  - other.yml\n" + GB10_ARMED, entry=ENTRY_ARMED)
    _, errors, _ = run(root)
    assert len(errors) == 1 and "include" in errors[0]


def test_env_file_in_the_demo_topology_is_not_a_finding(tmp_path):
    base = BASE_OPEN + "  extra:\n    image: x\n    env_file: .env\n"
    root = make_tree(tmp_path, base=base, gb10=GB10_ARMED, entry=ENTRY_ARMED)
    _, errors, _ = run(root)
    # the base file is also part of gb10, so that is where it is reported
    assert errors and all("(deployed)" in e and "gb10" in e for e in errors)
    reports = lint.analyse(root)
    demo = next(r for r in reports if r.topology.id == "demo-compose")
    assert any("env_file" in f for f in demo.findings)


def test_profiles_are_noted_in_the_report(tmp_path):
    gb10 = GB10_ARMED + "  witness2:\n    profiles: [witness]\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?x}\n"
    root = make_tree(tmp_path, gb10=gb10, entry=ENTRY_ARMED)
    reports = lint.analyse(root)
    gb = next(r for r in reports if r.topology.id == "gb10")
    assert any("witness2" in n and "witness" in n for n in gb.notes)
