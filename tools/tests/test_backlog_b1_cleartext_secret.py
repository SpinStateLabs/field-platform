"""Backlog B1: tools/d16_record_check.py refuses to send the perimeter secret over cleartext to a non-loopback,
non-private --base (the G19 / C-20 rule estate_probe and renew_token already enforce), and phase_g_check has no
--allow-plaintext override any more. Nothing here touches a network: the estate is a stub. Every value is made up."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d16_record_check as dc  # noqa: E402
import estate_probe as ep  # noqa: E402
import phase_g_check as pgc  # noqa: E402

OP = "don"
H = "0123456789abcdef" * 4
OP_KEY = "fok_" + "b1" * 20


class Reached(Exception):
    pass


@pytest.fixture()
def stub(monkeypatch):
    seen: list[str] = []

    class Est:
        def __init__(self, base, secret, *a, **k):
            seen.append(base)

        def call(self, method, path):
            return 200, [{"event_type": "kill.revive", "hash": H, "payload": {
                "operator_id_authenticated": OP, "operator_claimed": "Don H", "operator_key_fp": "0a1b2c3d"}}]

    monkeypatch.setattr(ep, "Estate", Est)
    monkeypatch.delenv("FIELD_OPERATOR_KEY", raising=False)
    return seen


def _run(tmp_path, base):
    f = tmp_path / "secret"
    f.write_text("made-up-secret-b1\n", encoding="utf-8")
    return dc.main(["--operator-id", OP, "--base", base, "--secret-file", str(f)])


@pytest.mark.parametrize("base", ["http://estate.example.com", "http://8.8.8.8:18080", "http://[2001:db8::1]:18080",
                                  "ftp://estate.example.com"])
def test_d16_refuses_a_cleartext_public_base_and_sends_nothing(tmp_path, capsys, stub, base):
    assert _run(tmp_path, base) == 2
    out = capsys.readouterr().out
    assert "cleartext" in out and "made-up-secret-b1" not in out
    assert stub == []


@pytest.mark.parametrize("base", ["https://estate.example.com", "http://127.0.0.1:18080", "http://localhost:18080",
                                  "http://[::1]:18080", "http://10.0.0.5:18080", "http://192.168.1.10:18080"])
def test_d16_allows_https_loopback_and_private_for_the_secret_alone(tmp_path, capsys, stub, base):
    assert _run(tmp_path, base) == 0
    assert stub == [base]


@pytest.mark.parametrize("base", ["http://10.0.0.5:18080", "http://192.168.1.10:18080"])
def test_d16_with_an_env_operator_key_allows_cleartext_to_loopback_only(tmp_path, capsys, stub, monkeypatch, base):
    monkeypatch.setenv("FIELD_OPERATOR_KEY", OP_KEY)
    assert _run(tmp_path, base) == 2 and stub == []
    assert OP_KEY not in capsys.readouterr().out


def test_d16_with_an_env_operator_key_still_allows_loopback_and_https(tmp_path, stub, monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR_KEY", OP_KEY)
    assert _run(tmp_path, "http://127.0.0.1:18080") == 0
    assert _run(tmp_path, "https://10.0.0.5:18080") == 0


def test_d16_has_no_cleartext_override_flag(tmp_path, capsys, stub):
    f = tmp_path / "secret"
    f.write_text("made-up-secret-b1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        dc.main(["--operator-id", OP, "--base", "http://estate.example.com", "--secret-file", str(f),
                 "--allow-plaintext"])
    assert e.value.code == 2 and stub == []


def test_d16_events_file_path_needs_no_transport_check(tmp_path, capsys, stub):
    f = tmp_path / "ev.json"
    f.write_text("[]", encoding="utf-8")
    assert dc.main(["--operator-id", OP, "--events", str(f)]) == 1 and stub == []


def test_phase_g_check_has_no_allow_plaintext_flag(capsys):
    with pytest.raises(SystemExit) as e:
        pgc.build_parser().parse_args(["--base", "http://estate.example.com", "--allow-plaintext"])
    assert e.value.code == 2 and "unrecognized arguments" in capsys.readouterr().err
    assert "allow_plaintext" not in Path(pgc.__file__).read_text(encoding="utf-8")


def test_phase_g_check_refuses_the_secret_to_a_public_http_base_even_if_the_old_attribute_is_set(monkeypatch, capsys):
    """A caller that still builds a Namespace with allow_plaintext=True gets no bypass."""
    def boom(*a, **k):
        raise Reached
    monkeypatch.delenv("FIELD_OPERATOR_KEY", raising=False)
    monkeypatch.setattr(ep, "Estate", boom)
    with pytest.raises(SystemExit) as e:
        pgc._run(argparse.Namespace(base="http://estate.example.com", allow_plaintext=True), "made-up-secret-b1", None)
    assert e.value.code == 2 and "cleartext" in capsys.readouterr().err


@pytest.mark.parametrize("base", ["ftp://127.0.0.1:18080", "ftp://localhost:18080", "ws://[::1]:18080",
                                  "file://127.0.0.1/x", "ftp://10.0.0.5:18080"])
def test_d16_refuses_a_non_http_scheme_even_to_a_loopback_or_private_host(tmp_path, capsys, stub, base):
    """R1 N2 (mutant G3): only http and https are accepted; any other scheme is refused even to loopback."""
    assert _run(tmp_path, base) == 2
    assert "cleartext" in capsys.readouterr().out and stub == []


def test_the_refusal_helper_accepts_only_http_and_https():
    assert dc.cleartext_refusal("https://127.0.0.1", True) is None
    assert dc.cleartext_refusal("http://127.0.0.1", True) is None
    for scheme in ("ftp", "ws", "wss", "file", "gopher", "HTTPX"):
        assert dc.cleartext_refusal(f"{scheme}://127.0.0.1", False) is not None, scheme

