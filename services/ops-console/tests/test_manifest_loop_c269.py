"""guarded_manifest_path and a symlink loop (C-269, reviewer C-239 F-C239-1, LOW, proven): on Python 3.12
``Path.resolve`` raises RuntimeError for a loop, and the guard caught only OSError and ValueError, so
``GET /api/agents/{id}/manifest`` answered 500. It now refuses like any unresolvable ref (404). The
patched tests do not depend on the interpreter's own behaviour for a loop; the real-link tests skip where
the OS cannot create symlinks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ops_console.api import ManifestRefused, ServiceClient, create_app, guarded_manifest_path


class Stub:
    def __init__(self, status=200, body=None):
        self.status, self.body = status, body if body is not None else {}

    def get(self, path, **kw):
        class R:
            status_code = self.status

            def json(_):  # noqa: N805
                return self.body

        return R()

    post = get


def sc(stub) -> ServiceClient:
    return ServiceClient(client=stub, base_url="http://t")


def console(manifest_dir, ref) -> TestClient:
    other = sc(Stub())
    reg = sc(Stub(200, {"agent_id": "a1", "manifest_ref": ref}))
    return TestClient(create_app(registry=reg, ledger=other, delegation=other, governor=other, killswitch=other,
                                 sentinel=other, lifecycle=other, attest=other, crosswalk=other,
                                 federation=other, replay=other, gateway=other, manifest_dir=manifest_dir))


@pytest.fixture()
def mdir(tmp_path):
    d = tmp_path / "manifests"
    d.mkdir()
    return d


def _symlink(link: Path, target: str) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("this OS or account cannot create symlinks")


@pytest.mark.parametrize("raised", [RuntimeError("Symlink loop from 'x'"), OSError(40, "Too many levels")])
def test_a_resolve_that_raises_for_a_loop_is_refused_404_not_an_unhandled_error(mdir, monkeypatch, raised):
    """The interpreter says the path is a loop: 3.12 raises RuntimeError, 3.13 and later an OSError."""
    real_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "loop.yaml":
            raise raised
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, "loop.yaml")
    assert e.value.status == 404 and "no manifest file at that ref" in e.value.reason


def test_the_manifest_route_answers_404_for_a_loop_not_500(mdir, monkeypatch):
    real_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "loop.yaml":
            raise RuntimeError("Symlink loop from 'x'")
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    r = console(mdir, "loop.yaml").get("/api/agents/a1/manifest")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["validation"] == "missing"


def test_a_real_self_link_in_the_manifest_directory_is_refused_not_a_500(mdir):
    _symlink(mdir / "loop.yaml", "loop.yaml")                      # a link to itself
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir, "loop.yaml")
    assert e.value.status in (403, 404)
    r = console(mdir, "loop.yaml").get("/api/agents/a1/manifest")
    assert r.status_code in (403, 404), r.text


def test_a_real_two_link_cycle_is_refused_not_a_500(mdir):
    _symlink(mdir / "a.yaml", "b.yaml")
    _symlink(mdir / "b.yaml", "a.yaml")
    r = console(mdir, "a.yaml").get("/api/agents/a1/manifest")
    assert r.status_code in (403, 404), r.text


def test_a_loop_in_the_manifest_directory_itself_is_refused_not_a_500(tmp_path, monkeypatch):
    real_resolve = Path.resolve

    def resolve(self, strict=False):
        if self.name == "loopdir":
            raise RuntimeError("Symlink loop from 'x'")
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(tmp_path / "loopdir", "ok.yaml")
    assert e.value.status == 404 and "manifest directory does not exist" in e.value.reason


def test_a_missing_manifest_directory_is_still_404_and_a_good_file_still_resolves(mdir):
    (mdir / "ok.yaml").write_text("a: 1\n", encoding="utf-8")
    assert guarded_manifest_path(mdir, "ok.yaml").name == "ok.yaml"
    with pytest.raises(ManifestRefused) as e:
        guarded_manifest_path(mdir / "nope", "ok.yaml")
    assert e.value.status == 404
