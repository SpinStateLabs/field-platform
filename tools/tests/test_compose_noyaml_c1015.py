"""C-1015 (reviewer C-939 F-C939-1): a host without PyYAML still gets the exit contract. The JSON that `docker compose config
--format json` prints is read with the standard library; text that is not JSON needs PyYAML, and without it is exit 3 with
one line, never a traceback and exit 1. Simulated by blocking the module in the child process."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import compose_resolved_check as crc  # noqa: E402

REPO = "/srv-fixture/checkout"
LAUNCH = ("import runpy, sys; sys.modules['yaml'] = None; sys.argv = [sys.argv[1]] + sys.argv[2:]; "
          "runpy.run_path(sys.argv[0], run_name='__main__')")


def run_without_yaml(model_text):
    return subprocess.run([sys.executable, "-c", LAUNCH, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                          input=model_text, capture_output=True, text=True, timeout=60)


def test_a_json_model_is_read_without_pyyaml_clean_and_refused():
    clean = run_without_yaml(json.dumps({"services": {"s": {"image": "x"}}}))
    assert clean.returncode == 0 and "Traceback" not in clean.stderr, (clean.stdout, clean.stderr)
    refused = run_without_yaml(json.dumps({"services": {"s": {"volumes": [{"type": "bind", "source": "/etc", "target": "/x"}]}}}))
    assert refused.returncode == 2 and "REFUSED" in refused.stdout and "Traceback" not in refused.stderr


def test_a_yaml_model_without_pyyaml_is_exit_3_with_one_line():
    r = run_without_yaml("services:\n  s:\n    image: x\n")
    assert r.returncode == 3 and "Traceback" not in r.stderr, (r.returncode, r.stdout, r.stderr)
    assert "PyYAML is not installed" in r.stdout and "could not read the model" in r.stdout


@pytest.mark.parametrize("text", ["", "   ", "not json {", "[1, 2"])
def test_text_that_is_neither_without_pyyaml_is_exit_3(text):
    r = run_without_yaml(text)
    assert r.returncode == 3 and "Traceback" not in r.stderr, (text, r.stdout, r.stderr)


def test_with_pyyaml_a_yaml_model_and_a_json_model_both_load():
    assert crc.load_model('{"services": {"s": {}}}') == {"services": {"s": {}}}
    assert crc.load_model("services:\n  s: {}\n") == {"services": {"s": {}}}


def test_with_pyyaml_text_that_is_neither_is_a_value_error_family_exit_3():
    r = subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input="a: [unclosed", capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "Traceback" not in r.stderr, (r.stdout, r.stderr)


def test_load_model_without_yaml_raises_a_value_error_naming_pyyaml(monkeypatch):
    monkeypatch.setattr(crc, "yaml", None)
    assert crc.load_model('{"a": 1}') == {"a": 1}
    with pytest.raises(ValueError, match="PyYAML is not installed"):
        crc.load_model("a: 1\n")


# --- C-1032 (reviewer C-43 F-C391-2): the read-error line never quotes the model ---------------------------------------------

MARKER = "ZZMARKERZZ"


@pytest.mark.parametrize("text", [f"a: b: {MARKER}", f"key: [{MARKER}\nother: 1"])
def test_a_parser_error_that_quotes_the_model_is_never_printed(text):
    import yaml

    with pytest.raises(yaml.YAMLError) as caught:
        yaml.safe_load(text)
    assert MARKER in str(caught.value), "the probe must make the parser quote the model, or this test proves nothing"
    r = subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, "-"],
                       input=text, capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "could not read the model" in r.stdout, (r.stdout, r.stderr)
    assert MARKER not in r.stdout and MARKER not in r.stderr


def test_only_the_fixed_pyyaml_message_is_printed_with_its_text():
    r = run_without_yaml(f"services:\n  {MARKER}: x: y\n")
    assert r.returncode == 3 and "PyYAML is not installed" in r.stdout and MARKER not in r.stdout


def test_a_non_utf8_file_prints_its_error_type_only_not_the_codec_message(tmp_path):
    f = tmp_path / "bad.json"
    f.write_bytes(b'{"services": {"s": "\xff\xfe' + MARKER.encode() + b'"}}')
    r = subprocess.run([sys.executable, str(TOOLS / "compose_resolved_check.py"), "--repo-root", REPO, str(f)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "UnicodeDecodeError" in r.stdout, (r.stdout, r.stderr)
    assert "codec" not in r.stdout and "position" not in r.stdout and MARKER not in r.stdout
