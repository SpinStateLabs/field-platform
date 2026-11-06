"""S4-15: `fedbroker sign` and `fedbroker crossing` fail cleanly (one stderr line, exit 1, no traceback, no key text)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from federation_broker import cli as cli_mod
from field_core.signing import generate_keypair

SECRET_MARK = "SYNTHETIC-KEY-TEXT-MARK"


@pytest.fixture()
def run(monkeypatch):
    monkeypatch.setenv("FIELD_FEDERATION_URL", "http://broker.invalid")
    runner = CliRunner(mix_stderr=False) if "mix_stderr" in CliRunner.__init__.__code__.co_varnames else CliRunner()

    def go(*args):
        return runner.invoke(cli_mod.app, list(args))
    return go


def manifest_file(tmp_path, data=None):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(data if data is not None else {"agent": {"id": "a"}}), encoding="utf-8")
    return p


def assert_clean(result, *forbidden):
    assert result.exit_code == 1, (result.exit_code, result.output)
    text = result.output
    assert "Traceback" not in text
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert len([ln for ln in text.splitlines() if ln.strip()]) == 1, text
    for f in forbidden:
        assert f not in text


@pytest.mark.parametrize("verb", ["sign", "crossing"])
def test_missing_manifest(run, tmp_path, verb):
    key = tmp_path / "k.pem"
    key.write_text(generate_keypair()[0], encoding="ascii")
    args = ["--manifest", str(tmp_path / "nope.yaml")]
    if verb == "sign":
        r = run("sign", *args, "--key", str(key))
    else:
        r = run("crossing", "--org", "Acme", "--agent-id", "a", *args, "--scope", "s", "--data-class", "d")
    assert_clean(r)


@pytest.mark.parametrize("verb", ["sign", "crossing"])
def test_manifest_is_a_yaml_list(run, tmp_path, verb):
    m = tmp_path / "list.yaml"
    m.write_text("- a\n- b\n", encoding="utf-8")
    key = tmp_path / "k.pem"
    key.write_text(generate_keypair()[0], encoding="ascii")
    if verb == "sign":
        r = run("sign", "--manifest", str(m), "--key", str(key))
    else:
        r = run("crossing", "--org", "Acme", "--agent-id", "a", "--manifest", str(m), "--scope", "s",
                "--data-class", "d")
    assert_clean(r)


def test_manifest_yaml_syntax_error(run, tmp_path):
    m = tmp_path / "bad.yaml"
    m.write_text("a: [unclosed\n", encoding="utf-8")
    key = tmp_path / "k.pem"
    key.write_text(generate_keypair()[0], encoding="ascii")
    assert_clean(run("sign", "--manifest", str(m), "--key", str(key)))


def test_sign_missing_key(run, tmp_path):
    assert_clean(run("sign", "--manifest", str(manifest_file(tmp_path)), "--key", str(tmp_path / "nokey.pem")))


def test_sign_non_ascii_key(run, tmp_path):
    key = tmp_path / "k.pem"
    key.write_text(f"-----BEGIN PRIVATE KEY-----\n{SECRET_MARK}É\n-----END PRIVATE KEY-----\n", encoding="utf-8")
    assert_clean(run("sign", "--manifest", str(manifest_file(tmp_path)), "--key", str(key)), SECRET_MARK)


def test_sign_public_key_given_as_key(run, tmp_path):
    key = tmp_path / "pub.pem"
    key.write_text(generate_keypair()[1], encoding="ascii")
    assert_clean(run("sign", "--manifest", str(manifest_file(tmp_path)), "--key", str(key)))


def test_sign_garbage_key_text_not_echoed(run, tmp_path):
    key = tmp_path / "g.pem"
    key.write_text(f"-----BEGIN PRIVATE KEY-----\n{SECRET_MARK}\n-----END PRIVATE KEY-----\n", encoding="ascii")
    assert_clean(run("sign", "--manifest", str(manifest_file(tmp_path)), "--key", str(key)), SECRET_MARK)


def test_crossing_broker_unreachable(run, tmp_path, monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectError("nope: secret-token-abc", request=httpx.Request("POST", url))
    monkeypatch.setattr(cli_mod, "httpx", SimpleNamespace(post=boom, TransportError=httpx.TransportError))
    r = run("crossing", "--org", "Acme", "--agent-id", "a", "--manifest", str(manifest_file(tmp_path)),
            "--scope", "s", "--data-class", "d")
    assert_clean(r, "secret-token-abc")
    assert "http://broker.invalid" in r.output


def test_crossing_timeout(run, tmp_path, monkeypatch):
    def boom(url, **kw):
        raise httpx.ReadTimeout("slow", request=httpx.Request("POST", url))
    monkeypatch.setattr(cli_mod, "httpx", SimpleNamespace(post=boom, TransportError=httpx.TransportError))
    assert_clean(run("crossing", "--org", "Acme", "--agent-id", "a", "--manifest", str(manifest_file(tmp_path)),
                     "--scope", "s", "--data-class", "d"))


def test_sign_happy_path_unchanged(run, tmp_path):
    key = tmp_path / "k.pem"
    key.write_text(generate_keypair()[0], encoding="ascii")
    r = run("sign", "--manifest", str(manifest_file(tmp_path)), "--key", str(key))
    assert r.exit_code == 0, r.output
    assert r.output.strip() and "\n" not in r.output.strip()
