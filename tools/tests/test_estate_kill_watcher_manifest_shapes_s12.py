"""S12-32: `estate_kill_watcher --manifest` refuses a manifest of any shape with `refused: ...` and exit 2, never a traceback.

from_manifest did `((data or {}).get("enforcement") or {}).get("kill_switch")`; the isinstance check covered only the top
level, so `enforcement: x` (a string), a non-empty list or a number was `AttributeError: 'str' object has no attribute
'get'` out of main(): a traceback and the interpreter's exit code from a tool whose exit codes other scripts read.
Every other manifest fault is a Refused (exit 2). The messages are fixed text; nothing from the manifest is echoed."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import estate_kill_watcher as ekw  # noqa: E402

SECRET = "SECRET-MANIFEST-VALUE"
NOT_MAPPING = ["x", SECRET, [1, 2], [{"a": 1}], 5, 1.5, True, False, 0, "", []]


def _write(tmp_path: Path, data) -> str:
    p = tmp_path / "field-manifest.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(p)


def _main(path: str, capsys):
    rc = ekw.main(["--agent", "a1", "--base", "http://127.0.0.1:1", "--manifest", path, "--once"])
    return rc, capsys.readouterr().err


@pytest.mark.parametrize("enforcement", NOT_MAPPING, ids=repr)
def test_an_enforcement_that_is_not_a_mapping_is_refused_exit_2(tmp_path, capsys, enforcement):
    rc, err = _main(_write(tmp_path, {"enforcement": enforcement}), capsys)
    assert rc == ekw.EXIT_REFUSED == 2
    assert err.strip() == "refused: the manifest's enforcement is not a mapping"
    assert SECRET not in err and "Traceback" not in err


@pytest.mark.parametrize("kill_switch", NOT_MAPPING, ids=repr)
def test_a_kill_switch_that_is_not_a_mapping_is_refused_exit_2(tmp_path, capsys, kill_switch):
    rc, err = _main(_write(tmp_path, {"enforcement": {"kill_switch": kill_switch}}), capsys)
    assert rc == 2
    assert err.strip() == "refused: the manifest's enforcement.kill_switch is not a mapping"
    assert SECRET not in err and "Traceback" not in err


@pytest.mark.parametrize("data", [None, {}, {"enforcement": None}, {"enforcement": {}}, {"enforcement": {"kill_switch": None}},
                                  {"enforcement": {"kill_switch": {}}}, [1, 2], "x", 5],
                         ids=lambda d: repr(d)[:40])
def test_a_missing_section_or_a_non_mapping_top_level_keeps_the_no_sentinel_refusal(tmp_path, capsys, data):
    rc, err = _main(_write(tmp_path, data), capsys)
    assert rc == 2
    assert err.strip() == "refused: the manifest sets no enforcement.kill_switch.local_sentinel"


@pytest.mark.parametrize("sentinel", [None, "", "   ", 5, ["x"], {"a": 1}], ids=repr)
def test_a_missing_or_non_string_local_sentinel_keeps_its_refusal(tmp_path, capsys, sentinel):
    rc, err = _main(_write(tmp_path, {"enforcement": {"kill_switch": {"local_sentinel": sentinel}}}), capsys)
    assert rc == 2 and err.strip() == "refused: the manifest sets no enforcement.kill_switch.local_sentinel"


def test_a_local_sentinel_that_is_not_a_path_keeps_its_refusal(tmp_path, capsys):
    rc, err = _main(_write(tmp_path, {"enforcement": {"kill_switch": {"local_sentinel": "ESTATE_KILL"}}}), capsys)
    assert rc == 2 and "not a file path" in err


@pytest.mark.parametrize("age", [True, False, 0, -1, 1.5, "30", [30], {"a": 1}], ids=repr)
def test_a_bad_sentinel_max_age_s_is_refused(tmp_path, capsys, age):
    data = {"enforcement": {"kill_switch": {"local_sentinel": "state/ESTATE_KILL", "sentinel_max_age_s": age}}}
    rc, err = _main(_write(tmp_path, data), capsys)
    assert rc == 2 and err.strip() == "refused: the manifest's sentinel_max_age_s is not an integer of 1 or more"


@pytest.mark.parametrize("age,expected", [(None, None), (1, 1), (30, 30)])
def test_a_good_manifest_resolves_against_the_manifest_directory(tmp_path, age, expected):
    ks = {"local_sentinel": "state/ESTATE_KILL"}
    if age is not None:
        ks["sentinel_max_age_s"] = age
    path, got = ekw.from_manifest(_write(tmp_path, {"enforcement": {"kill_switch": ks}}))
    assert path == str(tmp_path / "state" / "ESTATE_KILL") and got == expected


def test_file_url_and_absolute_forms_still_resolve(tmp_path):
    target = tmp_path / "abs" / "ESTATE_KILL"
    for raw in (str(target), f"file://{target}"):
        path, _ = ekw.from_manifest(_write(tmp_path, {"enforcement": {"kill_switch": {"local_sentinel": raw}}}))
        assert path == str(target)


def test_an_unreadable_manifest_keeps_its_refusal(tmp_path, capsys):
    p = tmp_path / "bad.yaml"
    p.write_text("enforcement: [unclosed", encoding="utf-8")
    rc, err = _main(str(p), capsys)
    assert rc == 2 and err.strip() == "refused: --manifest is not readable YAML"
    rc, err = _main(str(tmp_path / "missing.yaml"), capsys)
    assert rc == 2 and err.strip() == "refused: --manifest is not readable YAML"
