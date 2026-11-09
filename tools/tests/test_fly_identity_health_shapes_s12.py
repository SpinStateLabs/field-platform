"""S12-29: fly_identity_check tolerates any JSON shape from /health.

`_health` kept whatever json.loads returned, and `check_health` did `"_error" in h` and `h.get(...)`, so a /health that
answered null, a list, a number or a string was a TypeError / AttributeError out of main(): a traceback, no `C5-RESULT`
line, and the interpreter's exit code, from an identity check other scripts parse for PASS / FAIL. Now a body that is not
an object is a named problem and main() ends with `C5-RESULT: FAIL` and exit 1."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fly_identity_check as fic  # noqa: E402

SHAPES = [None, [], [1, 2], 5, 1.5, "x", True, ""]


@pytest.mark.parametrize("shape", SHAPES, ids=repr)
@pytest.mark.parametrize("expect", ["none", "four"])
def test_check_health_names_the_service_and_the_shape_and_never_raises(shape, expect):
    problems = fic.check_health({"registry": shape}, expect)
    assert len(problems) == 1
    assert problems[0] == f"registry: /health is not a JSON object ({type(shape).__name__})"


def test_one_bad_service_does_not_hide_the_others():
    good = {"operator_identity_id": None, "identity_present": False}
    problems = fic.check_health({"registry": good, "ledger": None, "console": {"operator_identity_id": "x", "identity_present": True}}, "none")
    assert len(problems) == 2
    assert problems[0].startswith("ledger: /health is not a JSON object")
    assert problems[1].startswith("console: /health operator_identity_id=")


def test_an_error_marker_and_good_objects_are_unchanged():
    assert fic.check_health({"ledger": {"_error": "URLError"}}, "none") == ["ledger: /health unreadable (URLError)"]
    assert fic.check_health({"ledger": {"operator_identity_id": None, "identity_present": False}}, "none") == []


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub_urlopen(monkeypatch, body: bytes):
    monkeypatch.setattr(fic.urllib.request, "urlopen", lambda url, timeout=None: _Resp(body))


@pytest.mark.parametrize("body", [b"null", b"[]", b"5", b'"x"', b"true", b"[1,2]"], ids=lambda b: b.decode())
def test__health_records_a_non_object_body_as_an_error_marker(monkeypatch, body):
    _stub_urlopen(monkeypatch, body)
    out = fic._health("http://127.0.0.1:1")
    assert set(out) == set(fic.HEALTH_PREFIX)
    assert all(v == {"_error": "NotAnObject"} for v in out.values())


def test__health_still_keeps_an_object_body(monkeypatch):
    _stub_urlopen(monkeypatch, b'{"operator_identity_id": null, "identity_present": false}')
    out = fic._health("http://127.0.0.1:1")
    assert all(v == {"operator_identity_id": None, "identity_present": False} for v in out.values())


def test_main_with_a_list_health_body_ends_with_a_fail_line_and_exit_1(monkeypatch, capsys):
    monkeypatch.setattr(fic, "check", lambda *a, **k: ([], ["processes_scanned=0"]))
    _stub_urlopen(monkeypatch, b"[]")
    rc = fic.main(["--expect", "none", "--health", "http://127.0.0.1:1"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "C5-RESULT: FAIL" in out and "NotAnObject" in out
    assert f"health_services_checked={len(fic.HEALTH_PREFIX)} health_mismatches={len(fic.HEALTH_PREFIX)}" in out


def test_main_with_object_bodies_still_passes(monkeypatch, capsys):
    monkeypatch.setattr(fic, "check", lambda *a, **k: ([], ["processes_scanned=0"]))
    _stub_urlopen(monkeypatch, b'{"operator_identity_id": null, "identity_present": false}')
    assert fic.main(["--expect", "none", "--health", "http://127.0.0.1:1"]) == 0
    assert "C5-RESULT: PASS expect=none" in capsys.readouterr().out
