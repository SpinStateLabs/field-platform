"""ManifestResolver cache is keyed on (mtime_ns, size, inode) and bounded (S12-5)."""
from __future__ import annotations

import copy
import os

import yaml

from field_core.clients import ManifestResolver
from field_core.templates_api import template_data


def _data(name: str) -> dict:
    d = copy.deepcopy(template_data("default"))
    d["agent"]["name"] = name
    d["agent"]["description"] = "Reads timesheets, drafts invoices"
    d["identity"]["principal"] = "Controller, Spin State Labs"
    d["identity"]["org"] = "Spin State Labs"
    d["identity"]["jurisdiction"] = ["PIPEDA"]
    d["identity"]["model_provider"] = "Anthropic"
    d["enforcement"]["kill_switch"]["endpoint"] = f"http://127.0.0.1:8005/kill/{name}"
    d["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    d["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
    d["delegation"]["granted_by"] = "Controller, Spin State Labs"
    d["delegation"]["scope"] = ["read timesheets", "draft invoices"]
    d["delegation"]["expiry"] = "2027-06-30"
    d["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke"}
    return d


def _write(path, name, description=None):
    d = _data(name)
    if description is not None:
        d["agent"]["description"] = description
    path.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")


def test_replacement_that_restores_the_old_mtime_is_re_read(tmp_path):
    p = tmp_path / "m.yaml"
    _write(p, "first-agent")
    r = ManifestResolver(tmp_path)
    old = p.stat()
    assert r.resolve("m.yaml").agent.name == "first-agent"
    _write(p, "second-agent-with-a-longer-name", description="x" * 40)
    os.utime(p, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert p.stat().st_size != old.st_size
    assert r.resolve("m.yaml").agent.name == "second-agent-with-a-longer-name"


def test_same_size_different_mtime_ns_is_re_read(tmp_path):
    p = tmp_path / "m.yaml"
    _write(p, "aaa-agent")
    r = ManifestResolver(tmp_path)
    old = p.stat()
    r.resolve("m.yaml")
    _write(p, "bbb-agent")
    assert p.stat().st_size == old.st_size
    os.utime(p, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000))
    assert r.resolve("m.yaml").agent.name == "bbb-agent"


def test_unchanged_file_returns_the_same_object(tmp_path):
    p = tmp_path / "m.yaml"
    _write(p, "same-agent")
    r = ManifestResolver(tmp_path)
    assert r.resolve("m.yaml") is r.resolve("m.yaml")


def test_cache_is_bounded(tmp_path):
    r = ManifestResolver(tmp_path)
    for i in range(300):
        _write(tmp_path / f"m{i}.yaml", f"agent-{i}")
        assert r.resolve(f"m{i}.yaml") is not None
    assert len(r._cache) <= 256
    assert str(tmp_path / "m299.yaml") in r._cache      # the newest survives, the oldest went
    assert str(tmp_path / "m0.yaml") not in r._cache


def test_deleted_file_is_missing_and_evicted(tmp_path):
    p = tmp_path / "m.yaml"
    _write(p, "gone-agent")
    r = ManifestResolver(tmp_path)
    r.resolve("m.yaml")
    assert str(p) in r._cache
    p.unlink()
    assert r.resolve_detail("m.yaml") == (None, "missing")
    assert str(p) not in r._cache
