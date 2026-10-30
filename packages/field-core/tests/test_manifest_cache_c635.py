"""C-635 (reviewer C-528 F-C528-3): the manifest resolver cache is keyed on the CONTENT, not the mtime.

A manifest rewritten with a different delegation scope and its original mtime put back (``os.utime``) was served from
the mtime cache with the OLD scope. The cache now keys on the sha256 of the bytes read, so a restored mtime, or a
same-size rewrite within the clock's resolution, cannot serve stale content."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

import field_core.clients as fc

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "services" / "agent-registry" / "tests" / "fixtures" / "manifests" / "invoicing-agent.yaml"


@pytest.fixture()
def resolver(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    shutil.copy(MANIFEST, d / "a.yaml")
    return fc.ManifestResolver(d), d / "a.yaml"


def _name_of(m):
    return m.agent.name if hasattr(m, "agent") and hasattr(m.agent, "name") else str(m)


def test_a_rewrite_with_the_original_mtime_restored_is_not_served_stale(resolver):
    r, path = resolver
    first, why = r.resolve_detail("a.yaml")
    assert why == "ok" and first is not None
    st = path.stat()
    text = path.read_text(encoding="utf-8")
    assert "name: invoicing-agent" in text
    path.write_text(text.replace("name: invoicing-agent", "name: invoicing-agenX", 1), encoding="utf-8")      # same size, different content
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))                            # the original mtime is back
    assert path.stat().st_mtime_ns == st.st_mtime_ns and path.stat().st_size == st.st_size
    second, why2 = r.resolve_detail("a.yaml")
    assert why2 == "ok" and second is not None
    assert second.model_dump() != first.model_dump()


def test_unchanged_content_is_served_from_the_cache_without_reparsing(resolver, monkeypatch):
    r, _ = resolver
    assert r.resolve_detail("a.yaml")[1] == "ok"
    calls = []
    real = fc.load_manifest
    monkeypatch.setattr(fc, "load_manifest", lambda p: calls.append(p) or real(p))
    assert r.resolve_detail("a.yaml")[1] == "ok"
    assert calls == []


def test_a_file_that_becomes_invalid_is_invalid_not_served_from_the_cache(resolver):
    r, path = resolver
    assert r.resolve_detail("a.yaml")[1] == "ok"
    st = path.stat()
    path.write_text("schema_version: field.spinstatelabs.ca/v1\nagent:\n  name: x\n", encoding="utf-8")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert r.resolve_detail("a.yaml") == (None, "invalid")


def test_a_removed_file_is_missing(resolver):
    r, path = resolver
    assert r.resolve_detail("a.yaml")[1] == "ok"
    path.unlink()
    assert r.resolve_detail("a.yaml") == (None, "missing")
