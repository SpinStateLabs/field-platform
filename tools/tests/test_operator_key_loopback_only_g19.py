"""Phase G C-20, tools half (G19): an operator key goes over cleartext to LOOPBACK only. The tools' RFC 1918
allowance stays for the perimeter secret alone (flags-off behaviour unchanged). https is always fine, and
--allow-plaintext remains the explicit override where the tool has it."""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import estate_probe as ep  # noqa: E402
import phase_g_check as pgc  # noqa: E402
import renew_token as rt  # noqa: E402
from field_core.hosts import is_internal_host  # noqa: E402

OP_ID = "test-operator"
OP_KEY = "test-op-key-NEVER-PRINT-g19-0123456789abcdef"

LOOPBACK = ["localhost", "LOCALHOST", "127.0.0.1", "127.0.0.2", "127.255.255.254", "::1", "::ffff:127.0.0.1"]
NOT_LOOPBACK = ["10.0.0.5", "172.16.0.1", "172.31.255.254", "192.168.1.1", "fd00::1", "::ffff:10.0.0.1",
                "169.254.169.254", "0.0.0.0", "8.8.8.8", "forcegw", "svc.internal", "example.com", "", None,
                "127.1", "0x7f.1", "2130706433", "127.0.0.1 .evil.test", "[::1]"]


class Reached(Exception):
    """The cleartext guard let the call through to the estate client."""


def _boom(*_a, **_k):
    raise Reached


@pytest.fixture
def key_file(tmp_path, monkeypatch):
    for k in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE", "FIELD_SHARED_SECRET"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / "op.key"
    p.write_text(OP_KEY + "\n", encoding="utf-8")
    return p


# -- the predicate, in each of the three copies ---------------------------------------------------------


@pytest.mark.parametrize("module", [ep, rt, pgc], ids=["estate_probe", "renew_token", "phase_g_check"])
@pytest.mark.parametrize("host", LOOPBACK + NOT_LOOPBACK)
def test_each_copy_is_loopback_only_and_a_subset_of_the_internal_predicate(module, host):
    expected = bool(is_internal_host(host, allow_names=False)) and _reference_loopback(host)
    assert module._loopback_host(host) is expected


def _reference_loopback(host):
    host = (host or "").lower()
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def test_the_cases_name_what_they_claim():
    assert all(ep._loopback_host(h) for h in LOOPBACK)
    assert not any(ep._loopback_host(h) for h in NOT_LOOPBACK)


# -- estate_probe ------------------------------------------------------------------------------------


def _probe(base, key_file, *extra):
    return ep.main(["--base", base, "--operator-id", OP_ID, "--operator-key-file", str(key_file), *extra,
                    "registry"])


@pytest.mark.parametrize("base", ["http://10.0.0.5:18080", "http://172.16.0.1:18080", "http://192.168.1.1:18080",
                                  "http://[fd00::1]:18080", "http://forcegw:18080"])
def test_estate_probe_refuses_an_operator_key_to_a_private_http_base(monkeypatch, key_file, base, capsys):
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(SystemExit) as e:
        _probe(base, key_file)
    assert e.value.code == 2
    assert "cleartext" in capsys.readouterr().err


@pytest.mark.parametrize("base", ["http://127.0.0.1:18080", "http://localhost:18080", "http://[::1]:18080",
                                  "https://10.0.0.5:18080", "https://estate.example.com"])
def test_estate_probe_allows_an_operator_key_on_loopback_http_and_on_https(monkeypatch, key_file, base):
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(Reached):
        _probe(base, key_file)


def test_estate_probe_allow_plaintext_is_still_the_explicit_override(monkeypatch, key_file):
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(Reached):
        _probe("http://10.0.0.5:18080", key_file, "--allow-plaintext")


def test_the_secret_alone_keeps_the_private_allowance(monkeypatch, tmp_path):
    for k in ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_OPERATOR_KEY_FILE"):
        monkeypatch.delenv(k, raising=False)
    secret = tmp_path / "s"
    secret.write_text("test-shared-secret-g19\n", encoding="utf-8")
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(Reached):
        ep.main(["--base", "http://10.0.0.5:18080", "--secret-file", str(secret), "registry"])


# -- phase_g_check -----------------------------------------------------------------------------------


def _pgc_args(base, allow=False):
    return argparse.Namespace(base=base, allow_plaintext=allow)


@pytest.mark.parametrize("base", ["http://10.0.0.5:18080", "http://192.168.1.1:18080"])
def test_phase_g_check_refuses_an_operator_key_to_a_private_http_base(monkeypatch, base, capsys):
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(SystemExit) as e:
        pgc._run(_pgc_args(base), None, OP_KEY)
    assert e.value.code == 2 and "cleartext" in capsys.readouterr().err


def test_phase_g_check_refuses_the_env_operator_key_too(monkeypatch, capsys):
    monkeypatch.setenv("FIELD_OPERATOR_KEY", OP_KEY)
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(SystemExit) as e:
        pgc._run(_pgc_args("http://10.0.0.5:18080"), None, None)
    assert e.value.code == 2


@pytest.mark.parametrize("base", ["http://127.0.0.1:18080", "https://10.0.0.5:18080"])
def test_phase_g_check_allows_loopback_http_and_https(monkeypatch, base):
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(Reached):
        pgc._run(_pgc_args(base), None, OP_KEY)


def test_phase_g_check_secret_alone_keeps_the_private_allowance(monkeypatch):
    monkeypatch.delenv("FIELD_OPERATOR_KEY", raising=False)
    monkeypatch.setattr(ep, "Estate", _boom)
    with pytest.raises(Reached):
        pgc._run(_pgc_args("http://10.0.0.5:18080"), "test-shared-secret-g19", None)


# -- renew_token ------------------------------------------------------------------------------------


def _validate(base, secret, key):
    args = rt.parse(["--agent", "a", "--base", base, "--env-file", "x", "--env-key", "K", "--check"])
    rt.validate(args, secret, key)


@pytest.mark.parametrize("base", ["http://10.0.0.5:18080", "http://172.16.0.1:18080", "http://192.168.1.1:18080"])
def test_renew_token_refuses_an_operator_key_to_a_private_http_base(base):
    with pytest.raises(rt.Refused, match="cleartext"):
        _validate(base, None, OP_KEY)
    with pytest.raises(rt.Refused, match="cleartext"):
        _validate(base, "test-shared-secret-g19", OP_KEY)


@pytest.mark.parametrize("base", ["http://127.0.0.1:18080", "http://localhost:18080", "https://10.0.0.5:18080"])
def test_renew_token_allows_an_operator_key_on_loopback_http_and_on_https(base):
    _validate(base, None, OP_KEY)


def test_renew_token_secret_alone_keeps_the_private_allowance():
    _validate("http://10.0.0.5:18080", "test-shared-secret-g19", None)
    with pytest.raises(rt.Refused, match="cleartext"):
        _validate("http://8.8.8.8:18080", "test-shared-secret-g19", None)
