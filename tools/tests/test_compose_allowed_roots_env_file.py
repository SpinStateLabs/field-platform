"""FIELD_COMPOSE_ALLOWED_ROOTS from the compose project's .env: used only when the process does not set it, under the
same rule, and nothing else of the file is ever shown. Every path and value here is made up."""
import json
import os
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
OTHER = "made-up-secret-value-Q1"
MODEL = {"services": {"s": {"volumes": [{"type": "bind", "source": ROOT_A + "/caller-keys", "target": "/k"}]}}}


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    model = tmp_path / "model.json"
    model.write_text(json.dumps(MODEL), encoding="utf-8")
    env = tmp_path / "integration" / "demo" / ".env"
    env.parent.mkdir(parents=True)

    def run(*extra):
        return crc.main([str(model), "--repo-root", str(tmp_path), *extra])

    return env, run


def test_without_a_file_or_a_variable_the_source_is_refused(project):
    env, run = project
    assert run() == 2 and VAR not in os.environ


@pytest.mark.parametrize("line", [
    f"{VAR}={ROOT_A}", f"export {VAR}={ROOT_A}", f'{VAR}="{ROOT_A}"', f"{VAR}='{ROOT_A}:{ROOT_B}'  # note",
    f"{VAR}={ROOT_A} # note", f"{VAR} = {ROOT_A}", f"{VAR}={ROOT_B}\n{VAR}={ROOT_A}",
], ids=["plain", "export", "double", "single-comment", "comment", "spaces", "last-wins"])
def test_the_project_env_file_supplies_the_variable(project, capsys, line):
    env, run = project
    env.write_text(f"FIELD_SHARED_SECRET={OTHER}\n{line}\r\n", encoding="utf-8")
    assert run() == 0
    out = capsys.readouterr()
    assert "read from the compose project's .env" in out.out
    assert OTHER not in out.out + out.err
    assert VAR not in os.environ                       # taken for this run only


@pytest.mark.parametrize("value", [ROOT_B, ""], ids=["another-root", "empty"])
def test_a_variable_set_in_the_process_wins(project, monkeypatch, value):
    env, run = project
    env.write_text(f"{VAR}={ROOT_A}\n", encoding="utf-8")
    monkeypatch.setenv(VAR, value)
    assert run() == 2 and os.environ[VAR] == value


@pytest.mark.parametrize("line", [f"{VAR}=/etc", f"{VAR}=relative/dir", f'{VAR}="{ROOT_A}', f"{VAR}=${{HOME}}/x"],
                         ids=["system", "relative", "unfinished-quote", "not-literal"])
def test_a_bad_value_in_the_file_refuses_the_check_without_echoing_it(project, capsys, line):
    env, run = project
    env.write_text(f"FIELD_SHARED_SECRET={OTHER}\n{line}\n", encoding="utf-8")
    assert run() == 2
    out = capsys.readouterr().out
    assert VAR in out and OTHER not in out and line.split("=", 1)[1].strip('"') not in out
    assert VAR not in os.environ


def test_a_file_without_the_variable_changes_nothing(project, capsys):
    env, run = project
    env.write_text(f"FIELD_SHARED_SECRET={OTHER}\n#{VAR}={ROOT_A}\n", encoding="utf-8")
    assert run() == 2 and "read from" not in capsys.readouterr().out


def test_an_unreadable_file_refuses(project):
    env, run = project
    env.mkdir()                                        # a directory where the file should be
    assert run() == 2


def test_env_file_names_another_file_and_it_must_exist(project, tmp_path):
    env, run = project
    other = tmp_path / "estate.env"
    other.write_text(f"{VAR}={ROOT_A}\n", encoding="utf-8")
    assert run("--env-file", str(other)) == 0
    assert run("--env-file", str(tmp_path / "missing.env")) == 2


def test_the_default_file_beside_the_first_compose_file():
    import argparse

    args = argparse.Namespace(env_file=None, run_compose=["/p/integration/demo/a.yml", "/q/b.yml"], repo_root="/r")
    assert crc._project_env_path(args) == os.path.join("/p/integration/demo", ".env")


def test_the_reader_looks_at_one_assignment_only(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"X={OTHER}\n", encoding="utf-8")
    assert rules.env_file_value(str(f), VAR) is None
