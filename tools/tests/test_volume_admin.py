"""tools/volume_admin.py - the only writer of the GB10 manifests and keys volumes.

On the GB10 every platform service mounts `field-manifests` read-only at
/data/manifests, so registered manifest_refs (/data/manifests/<id>.yaml) are
served from that volume. If the first `up` seeded it wrongly, every agent's
/check would BLOCK I.manifest; if install wrote an invalid file, that agent
would; if keys generate overwrote the anchor key, every earlier rotation
signature would stop verifying. Each rule is pinned here with the directory
layout the containers see (/estate/manifests, /manifests, /src, /keys),
and each assertion fails if its guard is removed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import volume_admin  # noqa: E402
from field_core.clients import ManifestResolver  # noqa: E402
from field_core.signing import key_fingerprint  # noqa: E402

CANARY = REPO / "manifests" / "canary-gb10.yaml"
SSL = REPO / "manifests" / "ssl-invoicing-agent.yaml"
POSIX = os.name == "posix"


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = volume_admin.main(list(argv))
    return code, out.getvalue()


@pytest.fixture()
def estate(tmp_path):
    """A pre-upgrade field-data volume: manifests written straight into it."""
    d = tmp_path / "estate" / "manifests"
    (d / "nested").mkdir(parents=True)
    (d / "canary-gb10.yaml").write_bytes(CANARY.read_bytes())
    (d / "ssl-invoicing-agent.yaml").write_bytes(SSL.read_bytes())
    (d / "nested" / "notes.txt").write_bytes(b"operator notes, not a manifest\n")
    return d


@pytest.fixture()
def volume(tmp_path):
    v = tmp_path / "field-manifests"
    v.mkdir()
    return v


def _seed(estate: Path, volume: Path) -> tuple[int, str]:
    return _run("manifests", "seed", "--estate", str(estate), "--volume", str(volume))


def _files(d: Path) -> dict[str, bytes]:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


# --- seed ------------------------------------------------------------------------------


def test_first_seed_copies_every_file_byte_for_byte_and_writes_a_marker(estate, volume):
    code, out = _seed(estate, volume)
    assert code == 0, out
    copied = {k: v for k, v in _files(volume).items() if not k.startswith(".")}
    assert copied == _files(estate)
    marker = json.loads((volume / volume_admin.MARKER).read_text())
    assert set(marker["files"]) == set(_files(estate))
    assert "3 file(s) seeded" in out


def test_a_registered_ref_resolves_to_the_same_manifest_after_the_seed(estate, volume):
    """The upgrade must not change what any reader resolves."""
    before, why_before = ManifestResolver(manifest_dir=estate).resolve_detail("canary-gb10.yaml")
    assert _seed(estate, volume)[0] == 0
    after, why_after = ManifestResolver(manifest_dir=volume).resolve_detail("canary-gb10.yaml")
    assert why_before == why_after == "ok"
    assert after.model_dump() == before.model_dump()


def test_a_seeded_volume_is_never_written_again_by_seed(estate, volume):
    assert _seed(estate, volume)[0] == 0
    snapshot = _files(volume)
    (estate / "canary-gb10.yaml").write_bytes(b"changed on the data volume after the upgrade\n")
    (estate / "late.yaml").write_bytes(SSL.read_bytes())
    code, out = _seed(estate, volume)
    assert code == 0 and "nothing written" in out
    assert _files(volume) == snapshot


def test_no_manifests_on_the_data_volume_seeds_an_empty_volume(tmp_path, volume):
    code, out = _seed(tmp_path / "missing", volume)
    assert code == 0, out
    assert "EMPTY" in out
    assert (volume / volume_admin.MARKER).exists()


def test_seed_refuses_different_bytes_already_in_an_unseeded_volume(estate, volume):
    (volume / "canary-gb10.yaml").write_bytes(b"not what the estate has\n")
    code, out = _seed(estate, volume)
    assert code == 1
    assert "canary-gb10.yaml" in out
    assert not (volume / volume_admin.MARKER).exists()
    assert _files(volume) == {"canary-gb10.yaml": b"not what the estate has\n"}  # nothing written


def test_seed_refuses_a_file_it_did_not_put_there(estate, volume):
    (volume / "hand-copied.yaml").write_bytes(SSL.read_bytes())
    code, out = _seed(estate, volume)
    assert code == 1
    assert "hand-copied.yaml" in out
    assert not (volume / volume_admin.MARKER).exists()
    assert set(_files(volume)) == {"hand-copied.yaml"}


def test_an_interrupted_seed_resumes(estate, volume):
    """A crash after some atomic copies and before the marker: the copied files
    are identical, so the next `up` finishes the seed instead of refusing."""
    (volume / "canary-gb10.yaml").write_bytes(CANARY.read_bytes())
    (volume / f"{volume_admin.TMP_PREFIX}ssl-invoicing-agent.yaml").write_bytes(b"torn")
    code, out = _seed(estate, volume)
    assert code == 0, out
    assert {k: v for k, v in _files(volume).items() if not k.startswith(".")} == _files(estate)
    assert not list(volume.rglob(f"{volume_admin.TMP_PREFIX}*"))


def test_seed_refuses_an_unmounted_volume(estate, tmp_path):
    assert _seed(estate, tmp_path / "not-mounted")[0] == 2


@pytest.mark.parametrize("garbage", [b"{not json", b"", b"\xff\xfe\x00"])
def test_seed_refuses_an_unreadable_marker(estate, volume, garbage):
    """A marker that cannot be read is not 'already seeded': the volume's state
    is unknown, so seed stops (exit 1) and touches nothing."""
    (volume / volume_admin.MARKER).write_bytes(garbage)
    (volume / "canary-gb10.yaml").write_bytes(b"whatever an earlier run left\n")
    snapshot = _files(volume)
    code, out = _seed(estate, volume)
    assert code == 1, out
    assert "unreadable" in out and "already seeded" not in out
    assert _files(volume) == snapshot


def test_seed_names_every_seeded_file_that_is_not_a_manifest(estate, volume):
    """A roster kept under /data/manifests on a pre-Phase-C estate is frozen by
    the seed (install refuses non-manifests): the seed output says so."""
    (estate / "doa-roster.yaml").write_text("grantors: []\n")
    (estate / "owners.csv").write_text("owner\nFIELD canary\n")
    code, out = _seed(estate, volume)
    assert code == 0, out
    notes = sorted(line.split()[1] for line in out.splitlines() if line.startswith("note: "))
    assert notes == ["doa-roster.yaml", "nested/notes.txt", "owners.csv"]
    assert "install` cannot change it" in out


@pytest.mark.skipif(not POSIX, reason="symlinks need privileges on Windows")
def test_seed_copies_a_symlink_as_a_symlink(estate, volume):
    os.symlink("canary-gb10.yaml", estate / "alias.yaml")
    assert _seed(estate, volume)[0] == 0
    assert os.readlink(volume / "alias.yaml") == "canary-gb10.yaml"


# --- install ---------------------------------------------------------------------------


@pytest.fixture()
def src(tmp_path):
    s = tmp_path / "src"
    s.mkdir()
    (s / "canary-gb10.yaml").write_bytes(CANARY.read_bytes())
    (s / "ssl-invoicing-agent.yaml").write_bytes(SSL.read_bytes())
    (s / "broken.yaml").write_text("schema_version: field.spinstatelabs.ca/v1\nagent: {}\n")
    (s / "doa-roster.example.yaml").write_text("grantors: []\n")
    return s


def _install(src: Path, volume: Path, *names: str) -> tuple[int, str]:
    return _run("manifests", "install", "--src", str(src), "--volume", str(volume), *names)


def test_install_refuses_an_unseeded_volume(src, volume):
    code, out = _install(src, volume, "canary-gb10.yaml")
    assert code == 1
    assert "not seeded" in out
    assert _files(volume) == {}


def test_install_writes_and_a_reader_resolves_the_new_bytes(tmp_path, src, volume):
    assert _seed(tmp_path / "none", volume)[0] == 0
    reader = ManifestResolver(manifest_dir=volume)
    assert reader.resolve_detail("canary-gb10.yaml")[1] == "missing"
    code, out = _install(src, volume, "canary-gb10.yaml", "ssl-invoicing-agent.yaml")
    assert code == 0, out
    assert (volume / "canary-gb10.yaml").read_bytes() == CANARY.read_bytes()
    manifest, why = reader.resolve_detail("canary-gb10.yaml")
    assert why == "ok" and manifest.agent.name == "canary-gb10"
    log = [json.loads(line) for line in (volume / volume_admin.INSTALL_LOG).read_text().splitlines()]
    assert [e["name"] for e in log] == ["canary-gb10.yaml", "ssl-invoicing-agent.yaml"]
    assert log[0]["sha256_before"] is None


def test_reinstalling_identical_bytes_logs_nothing(tmp_path, src, volume):
    assert _seed(tmp_path / "none", volume)[0] == 0
    assert _install(src, volume, "canary-gb10.yaml")[0] == 0
    code, out = _install(src, volume, "canary-gb10.yaml")
    assert code == 0 and "unchanged" in out
    assert len((volume / volume_admin.INSTALL_LOG).read_text().splitlines()) == 1


def test_one_unresolvable_file_means_nothing_is_written(tmp_path, src, volume):
    assert _seed(tmp_path / "none", volume)[0] == 0
    for bad in ("broken.yaml", "doa-roster.example.yaml", "absent.yaml"):
        code, out = _install(src, volume, "canary-gb10.yaml", bad)
        assert code == 2, (bad, out)
        assert "nothing written" in out
    assert not (volume / "canary-gb10.yaml").exists()
    assert not (volume / volume_admin.INSTALL_LOG).exists()


@pytest.mark.parametrize("name", ["../canary-gb10.yaml", "sub/canary-gb10.yaml", ".hidden.yaml",
                                  "canary-gb10.txt", volume_admin.MARKER, "/abs/canary-gb10.yaml"])
def test_install_accepts_only_plain_manifest_file_names(tmp_path, src, volume, name):
    assert _seed(tmp_path / "none", volume)[0] == 0
    # A VALID manifest really is at that path (except the absolute name, which
    # would land outside tmp_path), so only the name guard can refuse it.
    if not name.startswith("/"):
        target = src / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(CANARY.read_bytes())
        (volume / "sub").mkdir(exist_ok=True)
    snapshot = _files(volume)
    code, out = _install(src, volume, name)
    assert code == 2, out
    assert "is not a plain manifest file name" in out and "nothing written" in out
    assert _files(volume) == snapshot  # no manifest and no install log


# --- keys ------------------------------------------------------------------------------


def test_generate_writes_a_key_pair_the_ledger_accepts_and_prints_no_key_material(tmp_path):
    from sealed_ledger.api import load_anchor_key

    keys = tmp_path / "keys"
    code, out = _run("keys", "generate", "--dir", str(keys), "ledger-anchor")
    assert code == 0, out
    private, public = keys / "ledger-anchor.pem", keys / "ledger-anchor.pub.pem"
    assert "PRIVATE KEY" in private.read_text() and "PRIVATE" not in out and "BEGIN" not in out
    assert load_anchor_key(private)  # the rotation route's own loader: Ed25519, readable
    assert f"fingerprint: {key_fingerprint(public.read_text())}" in out
    if POSIX:
        assert (private.stat().st_mode & 0o777) == 0o600
        assert (keys.stat().st_mode & 0o777) == 0o700


def test_generate_never_overwrites_a_key(tmp_path):
    keys = tmp_path / "keys"
    assert _run("keys", "generate", "--dir", str(keys), "ledger-anchor")[0] == 0
    before = (keys / "ledger-anchor.pem").read_bytes(), (keys / "ledger-anchor.pub.pem").read_bytes()
    code, out = _run("keys", "generate", "--dir", str(keys), "ledger-anchor")
    assert code == 1 and "never overwritten" in out
    assert ((keys / "ledger-anchor.pem").read_bytes(), (keys / "ledger-anchor.pub.pem").read_bytes()) == before


def test_generate_refuses_when_only_the_public_half_exists(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "ledger-anchor.pub.pem").write_text("someone else's public key\n")
    assert _run("keys", "generate", "--dir", str(keys), "ledger-anchor")[0] == 1
    assert not (keys / "ledger-anchor.pem").exists()


@pytest.mark.parametrize("name", ["../x", "Ledger", "a/b", "", "x_y"])
def test_generate_refuses_a_bad_key_name(tmp_path, name):
    assert _run("keys", "generate", "--dir", str(tmp_path / "keys"), name)[0] == 2
    assert not (tmp_path / "keys").exists()


def test_export_public_prints_the_public_pem_that_verifies_a_rotation_anchor(tmp_path):
    """The PEM, not the fingerprint, is what `ledger verify --pubkey` needs: the
    exported bytes must verify the signed anchor of a real rotation made with
    the generated private key."""
    from sealed_ledger.anchors import AnchorRecord, append_anchor_line, verify_anchors
    from sealed_ledger.api import load_anchor_key
    from sealed_ledger.store import LedgerStore

    keys = tmp_path / "keys"
    code, gen_out = _run("keys", "generate", "--dir", str(keys), "ledger-anchor")
    assert code == 0, gen_out
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = volume_admin.main(["keys", "export-public", "--dir", str(keys), "ledger-anchor"])
    assert code == 0, err.getvalue()
    pem = out.getvalue()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----") and pem.rstrip().endswith("-----END PUBLIC KEY-----")
    assert "PRIVATE" not in pem + err.getvalue()
    fingerprint = key_fingerprint(pem)
    assert f"fingerprint: {fingerprint}" in gen_out and f"fingerprint: {fingerprint}" in err.getvalue()
    store = LedgerStore(tmp_path / "ledger" / "events.jsonl")
    for i in range(3):
        store.append("fixture.event", {"i": i})
    rotation = store.rotate(private_key_pem=load_anchor_key(keys / "ledger-anchor.pem"),
                            operator="test", reason="export-public")
    anchors = tmp_path / "rotation-anchors.jsonl"
    append_anchor_line(anchors, AnchorRecord.model_validate(rotation.anchor))
    checked = verify_anchors(store, anchors, public_key_pem=pem)
    assert checked.ok and checked.signatures_checked == 1, checked
    assert _run("keys", "generate", "--dir", str(tmp_path / "other"), "ledger-anchor")[0] == 0
    other = (tmp_path / "other" / "ledger-anchor.pub.pem").read_text()
    assert not verify_anchors(store, anchors, public_key_pem=other).ok  # the check is not vacuous


@pytest.mark.parametrize("planted", ["private", "ec-public", "garbage", "missing"])
def test_export_public_refuses_anything_but_an_ed25519_public_key(tmp_path, planted):
    """A private key under the public name is refused and never echoed."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from field_core.signing import generate_keypair

    keys = tmp_path / "keys"
    keys.mkdir()
    if planted == "private":
        (keys / "ledger-anchor.pub.pem").write_text(generate_keypair()[0])
    elif planted == "ec-public":
        ec_public = ec.generate_private_key(ec.SECP256R1()).public_key()
        (keys / "ledger-anchor.pub.pem").write_bytes(
            ec_public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    elif planted == "garbage":
        (keys / "ledger-anchor.pub.pem").write_text("not a key\n")
    code, out = _run("keys", "export-public", "--dir", str(keys), "ledger-anchor")
    assert code == 1, out
    assert "nothing printed" in out or "does not exist" in out
    assert "BEGIN" not in out


def test_export_public_never_echoes_what_else_is_in_the_file(tmp_path):
    """The PEM loader accepts a public key followed by other blocks (measured:
    a private key appended to the .pub.pem still loads). What is printed is
    re-encoded from the parsed public key, so the private block never leaves."""
    from field_core.signing import generate_keypair

    keys = tmp_path / "keys"
    keys.mkdir()
    private_pem, public_pem = generate_keypair()
    (keys / "ledger-anchor.pub.pem").write_text("# ledger anchor\n" + public_pem + private_pem)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = volume_admin.main(["keys", "export-public", "--dir", str(keys), "ledger-anchor"])
    assert code == 0, err.getvalue()
    assert out.getvalue() == public_pem
    assert "PRIVATE" not in out.getvalue() + err.getvalue()


@pytest.mark.parametrize("name", ["../x", "Ledger", "a/b", "x_y"])
def test_export_public_refuses_a_bad_key_name(tmp_path, name):
    keys = tmp_path / "keys"
    assert _run("keys", "generate", "--dir", str(keys), "ledger-anchor")[0] == 0
    code, out = _run("keys", "export-public", "--dir", str(keys), name)
    assert code == 2 and "BEGIN" not in out


def test_usage_errors_are_exit_2():
    assert _run()[0] == 2
    assert _run("manifests", "install")[0] == 2
