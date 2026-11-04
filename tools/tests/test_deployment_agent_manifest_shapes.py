"""load_manifest answers a wrong-shaped manifest with ManifestError, never a traceback (S5-23); the CLI says
'refused: ...' and exits 2 (the documented refusal path)."""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from deployment_agent import cli  # noqa: E402
from deployment_agent.manifest import ManifestError, load_manifest  # noqa: E402

MANIFEST = ROOT / "manifests" / "deployment-agent.yaml"


def _write(tmp_path, mutate):
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    mutate(doc)
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


def _ks(value):
    return lambda d: d["enforcement"].__setitem__("kill_switch", value)


def _ks_field(key, value):
    return lambda d: d["enforcement"]["kill_switch"].__setitem__(key, value)


BAD = [
    pytest.param(_ks("on"), id="kill_switch-string"),
    pytest.param(_ks([1]), id="kill_switch-list"),
    pytest.param(_ks(None), id="kill_switch-null"),
    pytest.param(_ks(5), id="kill_switch-int"),
    pytest.param(_ks_field("sentinel_max_age_s", True), id="age-bool"),
    pytest.param(_ks_field("sentinel_max_age_s", 0), id="age-zero"),
    pytest.param(_ks_field("sentinel_max_age_s", "x"), id="age-str"),
    pytest.param(_ks_field("local_sentinel", ["a"]), id="sentinel-list"),
    pytest.param(_ks_field("local_sentinel", {"a": 1}), id="sentinel-dict"),
    pytest.param(_ks_field("local_sentinel", 7), id="sentinel-int"),
    pytest.param(lambda d: d["delegation"].__setitem__("granted_by", ["x"]), id="granted_by-list"),
]


@pytest.mark.parametrize("mutate", BAD)
def test_a_wrong_shaped_manifest_is_a_manifest_error(tmp_path, mutate):
    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, mutate))


@pytest.mark.parametrize("raw", [b"\xff\xfe\x00bad", "a: b".encode("utf-16"), b"\x80\x81\x82"], ids=["bin", "utf16", "high"])
def test_a_file_that_is_not_utf8_is_a_manifest_error(tmp_path, raw):
    p = tmp_path / "m.yaml"
    p.write_bytes(raw)
    with pytest.raises(ManifestError):
        load_manifest(p)


def test_a_directory_or_unreadable_path_is_a_manifest_error(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


def test_the_real_manifest_still_loads():
    assert load_manifest(MANIFEST).name


@pytest.mark.parametrize("cmd", ["plan", "run"])
def test_the_cli_refuses_with_exit_2_not_a_traceback(tmp_path, cmd):
    p = _write(tmp_path, _ks("on"))
    out, err = io.StringIO(), io.StringIO()
    args = [cmd, "--target", "fly-app-a", "--manifest", str(p)]
    if cmd == "run":
        args += ["--journal-dir", str(tmp_path / "j")]
    code = cli.main(args, out=out, err=err)
    assert code == 2 and err.getvalue().startswith("refused:"), (code, err.getvalue())
