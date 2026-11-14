"""S4-18: a wrong-shaped compose model is REFUSED (exit 2) and an unreadable or non-UTF-8 file is exit 3: never a traceback."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import compose_resolved_check as crc  # noqa: E402

REPO = "/repo"
SVC = {"services": {"a": {"image": "x"}}}

SHAPES = {
    "volumes list": {**SVC, "volumes": ["a", "b"]},
    "volumes string": {**SVC, "volumes": "x"},
    "secrets list": {**SVC, "secrets": ["s"]},
    "configs list": {**SVC, "configs": ["c"]},
    "secrets number": {**SVC, "secrets": 5},
    "additional_contexts list with non-string": {"services": {"a": {"build": {"context": REPO, "additional_contexts": [1]}}}},
    "additional_contexts list with mapping": {"services": {"a": {"build": {"context": REPO, "additional_contexts": [{"x": "/etc"}]}}}},
    "additional_contexts number": {"services": {"a": {"build": {"context": REPO, "additional_contexts": 5}}}},
    "env_file number": {"services": {"a": {"env_file": 5}}},
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_a_wrong_shape_is_a_named_problem_not_an_exception(name):
    problems = crc.check_model(SHAPES[name], REPO)
    assert problems, name
    assert all(isinstance(p, str) for p in problems)


def test_mixed_key_types_do_not_break_sorting():
    model = {**SVC, "volumes": {1: {}, "a": {}}, "secrets": {2: {"file": "/etc/shadow"}, "s": {}}}
    problems = crc.check_model(model, REPO)
    assert any("/etc/shadow" in p for p in problems)


@pytest.mark.parametrize("model", [
    {**SVC, "volumes": None, "secrets": None, "configs": None},
    {**SVC, "volumes": {}, "secrets": {}, "configs": {}},
    {"services": {"a": {"build": {"context": REPO, "additional_contexts": ["x=docker-image://alpine"]}}}},
    {"services": {"a": {"env_file": ["/repo/a.env", {"path": "/repo/b.env"}]}}},
])
def test_well_shaped_models_stay_clean(model):
    assert crc.check_model(model, REPO) == []


@pytest.fixture()
def run(tmp_path, capsys):
    def go(content, binary=False):
        f = tmp_path / "m.yaml"
        f.write_bytes(content if binary else content.encode("utf-8"))
        code = crc.main([str(f), "--repo-root", REPO])
        return code, capsys.readouterr().out
    return go


@pytest.mark.parametrize("text", ["services: {a: {image: x}}\nvolumes: [a]\n", "services: {a: {image: x}}\nsecrets: [s]\n",
                                  "services: {a: {image: x}}\nconfigs: 5\n"])
def test_main_refuses_a_wrong_shaped_file_exit_2(run, text):
    code, out = run(text)
    assert code == 2 and "REFUSED" in out and "Traceback" not in out


def test_main_non_utf8_file_is_exit_3(run):
    code, out = run(b"services: {a: {image: \xff\xfe}}\n", binary=True)
    assert code == 3
    assert "could not read the model (UnicodeDecodeError)" in out


def test_main_missing_file_is_still_exit_3(tmp_path, capsys):
    assert crc.main([str(tmp_path / "nope.yaml"), "--repo-root", REPO]) == 3


def test_main_clean_file_is_exit_0(run):
    code, out = run("services: {a: {image: x}}\n")
    assert code == 0 and "every bind source is allowed" in out
