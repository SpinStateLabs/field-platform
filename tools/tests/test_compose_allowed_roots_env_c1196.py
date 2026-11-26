"""C-1196 (coordinator ruling 2026-11-03): further bind roots can be added for the resolved-model check.

The roots are ADDED through an environment variable (a colon-separated list, FIELD_COMPOSE_ALLOWED_ROOTS); the committed
default stays as it is, the static pins keep checking only that default, and a malformed entry fails closed without
printing the value. Every path added here is made up."""
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import compose_bind_rules as rules  # noqa: E402
import compose_resolved_check as crc  # noqa: E402

VAR = "FIELD_COMPOSE_ALLOWED_ROOTS"
ROOT_A = "/data/example-field/keys"
ROOT_B = "/data/example-field/operators"
MODEL_SOURCE = f"{ROOT_A}/caller-keys"


@pytest.fixture()
def roots():
    return rules.allowed_absolute_roots


def test_the_variable_name_is_the_documented_one():
    assert rules.ENV_ALLOWED_ROOTS == VAR


def test_the_default_is_the_committed_root_and_nothing_else(roots):
    assert roots({}) == rules.ALLOWED_ABSOLUTE_ROOTS == (rules.CALLER_KEYS_ROOT,)


@pytest.mark.parametrize("value", ["", " ", "\t", ":", ":::", " : "])
def test_an_empty_variable_falls_back_to_the_default(roots, value):
    assert roots({VAR: value}) == rules.ALLOWED_ABSOLUTE_ROOTS


def test_the_variable_adds_a_root_and_keeps_the_default(roots):
    got = roots({VAR: ROOT_A})
    assert got == (*rules.ALLOWED_ABSOLUTE_ROOTS, ROOT_A)


def test_several_roots_a_trailing_separator_and_a_trailing_slash(roots):
    got = roots({VAR: f"{ROOT_A}/:{ROOT_B}:"})
    assert got == (*rules.ALLOWED_ABSOLUTE_ROOTS, ROOT_A, ROOT_B)


def test_a_repeated_root_is_listed_once(roots):
    got = roots({VAR: f"{ROOT_A}:{ROOT_A}:{rules.ALLOWED_ABSOLUTE_ROOTS[0]}"})
    assert got == (*rules.ALLOWED_ABSOLUTE_ROOTS, ROOT_A)


@pytest.mark.parametrize("entry", [
    "relative/path", "./x", "/data/../etc", "/data/./x", "/data//x", "/data/$X", "/data/`x`", "~/x", "/data/x\ny",
    "/", "/etc", "/etc/ssl", "/proc", "/var/run", "/var/run/docker.sock", "/home", "/home/user",
    "/home/user/.ssh", "/home/user/.config", "/root", "/opt",
])
def test_a_malformed_or_forbidden_entry_fails_closed_without_echoing_it(roots, entry):
    with pytest.raises(ValueError) as exc:
        roots({VAR: f"{ROOT_A}:{entry}"})
    assert entry not in str(exc.value) and VAR in str(exc.value)


def test_the_committed_constant_is_not_changed_by_the_variable(monkeypatch):
    # the static pins import the constant and check the DEFAULT of every `${VAR:-default}`; the estate's variable is not theirs
    monkeypatch.setenv(VAR, ROOT_A)
    assert ROOT_A not in rules.ALLOWED_ABSOLUTE_ROOTS


def test_a_source_outside_both_is_refused_with_the_same_message(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    refused = crc.source_problem(MODEL_SOURCE, "/repo/checkout", "volume", None)
    assert refused == "outside the repository and the allowed roots"
    monkeypatch.setenv(VAR, ROOT_B)
    assert crc.source_problem(MODEL_SOURCE, "/repo/checkout", "volume", None) == refused


def test_a_source_under_the_variable_root_is_allowed_and_the_default_still_is(monkeypatch):
    monkeypatch.setenv(VAR, ROOT_A)
    assert crc.source_problem(MODEL_SOURCE, "/repo/checkout", "volume", None) is None
    default_source = rules.ALLOWED_ABSOLUTE_ROOTS[0] + "/x"
    assert crc.source_problem(default_source, "/repo/checkout", "volume", None) is None


def test_the_root_itself_is_not_a_source_only_its_descendants(monkeypatch):
    monkeypatch.setenv(VAR, ROOT_A)
    assert crc.source_problem(ROOT_A, "/repo/checkout", "volume", None) == "outside the repository and the allowed roots"


def _model_file(tmp_path, source):
    p = tmp_path / "model.json"
    p.write_text(json.dumps({"services": {"svc": {"volumes": [{"type": "bind", "source": source, "target": "/k"}]}}}),
                 encoding="utf-8")
    return str(p)


def test_the_command_line_allows_a_variable_root_and_refuses_it_without(monkeypatch, tmp_path, capsys):
    model = _model_file(tmp_path, MODEL_SOURCE)
    monkeypatch.delenv(VAR, raising=False)
    assert crc.main(["--repo-root", str(tmp_path), model]) == 2
    monkeypatch.setenv(VAR, ROOT_A)
    assert crc.main(["--repo-root", str(tmp_path), model]) == 0
    assert "every bind source is allowed" in capsys.readouterr().out


def test_the_command_line_fails_closed_on_a_bad_variable_and_does_not_print_it(monkeypatch, tmp_path, capsys):
    model = _model_file(tmp_path, MODEL_SOURCE)
    monkeypatch.setenv(VAR, "/etc/made-up-entry-0123")
    assert crc.main(["--repo-root", str(tmp_path), model]) == 2
    out = capsys.readouterr().out
    assert "made-up-entry-0123" not in out and VAR in out


def test_a_runtime_socket_outside_the_forbidden_trees_is_refused(roots):
    with pytest.raises(ValueError, match="runtime socket"):
        roots({VAR: "/data/example-field/docker.sock"})


def test_an_empty_entry_between_two_roots_does_not_end_the_list(roots):
    assert roots({VAR: f"{ROOT_A}::{ROOT_B}"}) == (*rules.ALLOWED_ABSOLUTE_ROOTS, ROOT_A, ROOT_B)
