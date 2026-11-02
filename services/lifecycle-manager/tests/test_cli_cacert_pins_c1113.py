"""C-1113 (reviewer Q-72 survivors M14, M17, M33 for C-1098): pin three properties of ``cli._verify_from`` that the
code has today and the docs promise, and that no test held.

M14  the ``--cacert`` bundle REPLACES the trust store; nothing loads the default store after it (the runbook says
     "replace", a change that called ``load_default_certs`` would make the private-CA option a trust ADD).
M17  the context keeps a TLS floor of 1.2 (a lowered floor would negotiate an old protocol with the estate).
M33  a refusal names the exception class and never its text: an ``OSError`` carries the path in ``str(exc)``.

Mutants (hand-run on cli.py, each red against this file and green before): M14 ``ctx.load_default_certs()`` after the
cafile; M17 ``ctx.minimum_version = TLSv1`` ; M33 the refusal formats ``exc`` instead of ``type(exc).__name__``.
Throwaway CA made in-process, loopback only, no network, no estate value.
"""
from __future__ import annotations

import datetime
import ssl
from pathlib import Path

import pytest
import typer

from lifecycle_manager import cli


def _ca_pem(out: Path, name: str) -> Path:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(key, hashes.SHA256()))
    path = out / "ca.pem"
    path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    return path


def test_the_cacert_bundle_replaces_the_store_and_nothing_loads_the_default_store_after_it(tmp_path, monkeypatch):
    ca = _ca_pem(tmp_path, "c1113 throwaway CA")
    calls: list = []
    real = ssl.SSLContext.load_default_certs
    monkeypatch.setattr(ssl.SSLContext, "load_default_certs",
                        lambda self, *a, **k: (calls.append(a), real(self, *a, **k))[1])
    ctx = cli._verify_from(ca)
    assert calls == []                                        # M14: no default store loaded, before or after the file
    assert ctx.cert_store_stats()["x509_ca"] == 1             # exactly the bundle's one CA, nothing added


def test_the_cacert_context_keeps_a_tls_floor_of_1_2(tmp_path):
    ctx = cli._verify_from(_ca_pem(tmp_path, "c1113 throwaway CA"))
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2      # M17


@pytest.mark.parametrize("exc", [
    OSError(2, "No such file or directory", "/c1113/secret-looking/path/ca.pem"),
    PermissionError(13, "Permission denied", "/c1113/secret-looking/path/ca.pem"),
])
def test_an_oserror_is_refused_by_class_name_without_echoing_its_path(tmp_path, monkeypatch, capsys, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(ssl, "create_default_context", boom)
    with pytest.raises(typer.Exit) as stopped:
        cli._verify_from(tmp_path / "ca.pem")
    err = capsys.readouterr().err
    assert stopped.value.exit_code == 2
    assert type(exc).__name__ in err and "nothing sent" in err    # M33: the class, not str(exc)
    assert "secret-looking" not in err and "No such file" not in err and "Permission denied" not in err
    assert str(tmp_path) not in err
