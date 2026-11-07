"""C-1098 (reviewer Q-09 F-Q09-1, Don's ruling: add the option): the CLI's estate clients take `--cacert`.

The estate clients are built with ``trust_env=False`` (C-575), so httpx never reads ``SSL_CERT_FILE`` for them: an
https estate behind a private CA was unreachable from the CLI with no switch to fix it. ``--cacert PATH`` now hands
the verbs a PEM bundle; ``_verify_from`` turns it into an SSL context that trusts ONLY that bundle, and every client a
builder makes gets it as ``verify=``. Nothing turns verification off: without the option the system trust store is
used, and there is no ``--insecure``.

Measured here with a throwaway CA made in-process (cryptography, pinned in constraints.txt) and a real TLS listener on
loopback: a made-up secret, no network, no estate value. Mutants: V1 ``verify=verify`` dropped from the client (the
bundle is ignored: the 200 test goes red); V2 ``_verify_from(None)`` returns False (the default-refuses test goes red);
V3 ``trust_env=True`` (the SSL_CERT_FILE test goes red); V4 a verb forgets to pass ``cacert`` (the per-verb test goes red).
"""
from __future__ import annotations

import datetime
import ipaddress
import ssl
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from field_core import authn
from lifecycle_manager import cli

SECRET = "c1098-made-up-perimeter-secret"


def _ca_and_leaf(out: Path, ca_name: str) -> tuple[Path, Path, Path]:
    """A throwaway CA and a leaf for 127.0.0.1 it signed; PEM files under ``out``."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)
    before, after = now - datetime.timedelta(minutes=5), now + datetime.timedelta(hours=1)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ca_name)])
    ca = (x509.CertificateBuilder().subject_name(ca_subject).issuer_name(ca_subject).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(before).not_valid_after(after)
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
            .issuer_name(ca_subject).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(before).not_valid_after(after)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    out.mkdir(parents=True, exist_ok=True)
    ca_pem, leaf_pem, leaf_key_pem = out / "ca.pem", out / "leaf.pem", out / "leaf.key"
    ca_pem.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    leaf_pem.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    leaf_key_pem.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
    return ca_pem, leaf_pem, leaf_key_pem


@dataclass
class Estate:
    url: str
    ca: Path           # the CA that signed the listener's certificate
    other_ca: Path     # a second, unrelated CA
    hits: list


@pytest.fixture
def estate(tmp_path) -> Estate:
    ca, leaf, key = _ca_and_leaf(tmp_path / "ca1", "c1098 throwaway CA one")
    other_ca, _, _ = _ca_and_leaf(tmp_path / "ca2", "c1098 throwaway CA two")
    hits: list = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(leaf), str(key))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield Estate(f"https://127.0.0.1:{server.server_port}", ca, other_ca, hits)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)


def _registry_client(monkeypatch, url: str, **kw) -> httpx.Client:
    monkeypatch.setenv("FIELD_REGISTRY_URL", url)
    return cli._service_client("registry", None, **kw)[1]


def test_by_default_an_estate_behind_a_private_ca_is_refused(secret, monkeypatch, estate):
    client = _registry_client(monkeypatch, estate.url)
    with pytest.raises(httpx.ConnectError):
        client.get("/health")
    assert estate.hits == []                                  # the handshake failed; no request reached the listener


def test_ssl_cert_file_is_still_not_read_by_the_estate_clients(secret, monkeypatch, estate):
    monkeypatch.setenv("SSL_CERT_FILE", str(estate.ca))
    client = _registry_client(monkeypatch, estate.url)
    assert client.trust_env is False
    with pytest.raises(httpx.ConnectError):
        client.get("/health")
    assert estate.hits == []


def test_the_cacert_bundle_makes_the_private_ca_trusted_and_changes_nothing_else(secret, monkeypatch, estate):
    client = _registry_client(monkeypatch, estate.url, verify=cli._verify_from(estate.ca))
    assert client.get("/health").status_code == 200 and estate.hits == ["/health"]
    assert client.trust_env is False and client.follow_redirects is False
    assert client.headers.get(authn.HEADER) == SECRET and isinstance(client.auth, cli.GuardedOperatorAuth)


def test_the_cacert_bundle_replaces_the_trust_store_rather_than_adding_to_it(secret, monkeypatch, estate):
    client = _registry_client(monkeypatch, estate.url, verify=cli._verify_from(estate.other_ca))
    with pytest.raises(httpx.ConnectError):
        client.get("/health")
    assert estate.hits == []


def test_verify_from_is_the_default_store_without_a_bundle_and_never_off(estate):
    assert cli._verify_from(None) is True
    ctx = cli._verify_from(estate.ca)
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_a_file_that_is_not_a_pem_bundle_is_refused_without_echoing_it(tmp_path, secret):
    bad = tmp_path / "not-a-bundle.txt"
    bad.write_text("this is not a certificate\n", encoding="utf-8")
    roster = tmp_path / "roster.csv"
    roster.write_text("agent_id,owner\n", encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["sweep", "--roster", str(roster), "--cacert", str(bad)])
    assert result.exit_code == 2, result.output
    assert "nothing sent" in result.output and str(bad) not in result.output
    assert "this is not a certificate" not in result.output


def test_every_client_a_builder_makes_carries_the_verify_value(secret, monkeypatch, estate):
    made: list = []
    real = httpx.Client

    class Recorder(real):
        def __init__(self, *a, **k):
            made.append(k.get("verify", "MISSING"))
            super().__init__(*a, **k)

    monkeypatch.setattr(cli.httpx, "Client", Recorder)
    ctx = cli._verify_from(estate.ca)
    cli.estate_clients(None, verify=ctx)
    assert made and all(v is ctx for v in made), made
    made.clear()
    cli._provision_clients(None, cacert=estate.ca)
    assert made and all(isinstance(v, ssl.SSLContext) for v in made), made
    made.clear()
    cli.estate_clients(None)
    assert made and all(v is True for v in made), made


def _run_verb(monkeypatch, tmp_path, verb: str, extra: list[str]) -> None:
    from field_core import operator_auth
    from lifecycle_manager import engine as engine_mod
    from test_cli_clients_no_proxy_c575 import _CaptureEngine

    _CaptureEngine.kwargs = None
    monkeypatch.setattr(engine_mod, "LifecycleEngine", _CaptureEngine)
    monkeypatch.setattr(cli, "operator_pair", lambda *a, **k: None)
    fake = type("Auth", (), {"mode": "enforce", "authenticated": True, "failure": None, "operator": None})()
    monkeypatch.setattr(operator_auth, "authenticate", lambda *a, **k: fake)
    monkeypatch.setattr(operator_auth, "bind", lambda *a, **k: None)
    monkeypatch.setattr(operator_auth, "bind_body_operator", lambda by, *a, **k: by)
    roster, manifest = tmp_path / "roster.csv", tmp_path / "agent.yaml"
    roster.write_text("agent_id,owner\n", encoding="utf-8")
    manifest.write_text("name: c1098\n", encoding="utf-8")
    argv = {
        "sweep": ["sweep", "--roster", str(roster), "--auto-kill-orphans"],
        "provision": ["provision", "--manifest", str(manifest), "--owner", "o", "--domain", "d", "--grantor", "g",
                      "--ttl-days", "1"],
        "decommission": ["decommission", "a", "--by", "b", "--reason", "r"],
    }[verb] + extra
    result = CliRunner().invoke(cli.app, argv)
    assert _CaptureEngine.kwargs is not None, f"{verb} never built an engine: {result.output}"


@pytest.mark.parametrize("verb", ["sweep", "provision", "decommission"])
def test_each_verb_hands_its_cacert_to_the_builder_and_the_default_is_the_store(monkeypatch, tmp_path, secret, verb,
                                                                                estate):
    seen: list = []
    original = cli.estate_clients

    def spy(pair, timeout=20.0, verify=True):
        seen.append(verify)
        return original(pair, timeout, verify)

    monkeypatch.setattr(cli, "estate_clients", spy)
    _run_verb(monkeypatch, tmp_path, verb, ["--cacert", str(estate.ca)])
    assert len(seen) == 1 and isinstance(seen[0], ssl.SSLContext), seen
    seen.clear()
    _run_verb(monkeypatch, tmp_path, verb, [])
    assert seen == [True], seen
