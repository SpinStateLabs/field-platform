"""Scout S-2-13: `forcegw presets --show <unknown>` printed a KeyError traceback, and `forcegw telemetry` printed the reply
body for ANY status (a 401 or 503 exited 0) and raised a traceback when the gateway was down. Now an unknown preset lists
the known names on stderr and exits 2; telemetry prints the body only on a 200, and otherwise one line with the status
(never the body) and exit 1, or the exception class name only when the gateway cannot be reached. No network: httpx.get is
stubbed."""
from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from force_gateway import cli as cli_module
from force_gateway.cli import app
from force_gateway.presets import PRESETS

BODY_MARKER = "UPSTREAM-BODY-MARKER-9921"


def invoke(*args):
    return CliRunner().invoke(app, list(args))


# ---- presets ---------------------------------------------------------------------------------------------------------

def test_presets_lists_every_preset_with_its_letters():
    r = invoke("presets")
    assert r.exit_code == 0
    for name, letters in PRESETS.items():
        assert name in r.output and "+".join(letters) in r.output


def test_presets_show_analysis_prints_the_force_block():
    r = invoke("presets", "--show", "analysis")
    assert r.exit_code == 0
    assert "FORCE Runtime Protocol" in r.output and "preset: analysis" in r.output


@pytest.mark.parametrize("name", PRESETS)
def test_every_known_preset_can_be_shown(name):
    r = invoke("presets", "--show", name)
    assert r.exit_code == 0 and f"preset: {name}" in r.output


@pytest.mark.parametrize("bad", ["vibes", "ANALYSIS", "analysis ", "x" * 300, "../etc/passwd"])
def test_an_unknown_preset_exits_2_with_the_known_names_and_no_traceback(bad):
    r = invoke("presets", "--show", bad)
    assert r.exit_code == 2
    assert "Traceback" not in r.output and "KeyError" not in r.output
    for name in PRESETS:
        assert name in r.stderr
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_an_unknown_preset_message_goes_to_stderr_not_stdout():
    r = invoke("presets", "--show", "vibes")
    assert r.stdout.strip() == ""
    assert "vibes" in r.stderr or "unknown" in r.stderr.lower()


# ---- telemetry -------------------------------------------------------------------------------------------------------

def _stub(monkeypatch, status=200, text='{"calls": 3}', exc=None, seen=None):
    def fake_get(url, **kw):
        if seen is not None:
            seen.append((url, kw))
        if exc is not None:
            raise exc
        return httpx.Response(status, text=text, request=httpx.Request("GET", url))
    monkeypatch.setattr(cli_module.httpx, "get", fake_get)


def test_telemetry_200_prints_the_body(monkeypatch):
    seen = []
    _stub(monkeypatch, 200, '{"calls": 3}', seen=seen)
    monkeypatch.setenv("FIELD_GATEWAY_URL", "http://gw.test:1234/")
    r = invoke("telemetry")
    assert r.exit_code == 0 and r.stdout.strip() == '{"calls": 3}'
    assert seen[0][0] == "http://gw.test:1234/telemetry" and seen[0][1]["timeout"] == 10.0


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 429, 500, 503])
def test_telemetry_a_non_200_exits_1_with_the_status_and_never_the_body(monkeypatch, status):
    _stub(monkeypatch, status, f"{BODY_MARKER} secret-ish text")
    r = invoke("telemetry")
    assert r.exit_code == 1
    assert str(status) in r.stderr
    assert BODY_MARKER not in r.output and BODY_MARKER not in r.stderr
    assert "Traceback" not in r.output


@pytest.mark.parametrize("exc", [
    httpx.ConnectError(f"refused {BODY_MARKER}"),
    httpx.ReadTimeout(f"slow {BODY_MARKER}"),
    httpx.ConnectTimeout("t"),
    httpx.RemoteProtocolError("bad"),
])
def test_telemetry_a_transport_error_exits_1_with_the_class_name_only(monkeypatch, exc):
    _stub(monkeypatch, exc=exc)
    r = invoke("telemetry")
    assert r.exit_code == 1
    assert type(exc).__name__ in r.stderr
    assert BODY_MARKER not in r.output and BODY_MARKER not in r.stderr and "Traceback" not in r.output
