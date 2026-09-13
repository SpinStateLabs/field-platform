"""B0 - the shared manifest resolver in field_core.clients.

This is the ONE manifest resolver in the platform (lifted from
conformance_sentinel.engine, which now re-exports it). Four properties here
are load-bearing for governance, so each has a test that fails if someone
weakens it:

1. Fail-closed. A ref that is missing, unparseable or schema-invalid resolves
   to None so the caller blocks (I.manifest) instead of assuming a manifest.
2. The mtime cache is invalidated when the file changes. A stale cache would
   keep enforcing a scope the operator has already narrowed on disk.
3. One ref resolves to exactly its own manifest - no cross-file bleed. This is
   the field-core half of the sentinel's tenant-isolation guarantee.
4. Filesystem-only. field-core must NOT gain an httpx dependency, so a
   URL-form ref is never fetched; it is simply an unreadable path.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest
import yaml

from field_core.clients import (
    RESOLVE_REASONS,
    ManifestResolver,
    resolve_manifest,
    resolve_manifest_detail,
)
from field_core.manifest import FieldManifest
from field_core.templates_api import template_data

AGENT_ID = "invoicing-agent"
SCOPE = ["read timesheets", "draft invoices"]


def manifest_data(name: str = AGENT_ID, scope: list[str] | None = None) -> dict:
    data = copy.deepcopy(template_data("default"))
    data["agent"]["name"] = name
    data["agent"]["description"] = "Reads timesheets, drafts invoices"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = (
        f"http://127.0.0.1:8005/kill/{name}"
    )
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = list(scope or SCOPE)
    data["delegation"]["expiry"] = "2027-06-30"
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke",
    }
    return data


def write_manifest(path: Path, data: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data if data is not None else manifest_data(), sort_keys=False),
        encoding="utf-8",
    )
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def touch_newer(path: Path) -> None:
    """Bump mtime by whole seconds - a coarse filesystem timestamp must not
    make the cache-invalidation test pass or fail by luck."""
    stat = path.stat()
    os.utime(path, (stat.st_atime + 5, stat.st_mtime + 5))


BROKEN_YAML = "agent: [unclosed\n  name: x\n"


@pytest.fixture(autouse=True)
def _no_ambient_manifest_dir(monkeypatch):
    """No test here may inherit a FIELD_MANIFEST_DIR from the developer shell."""
    monkeypatch.delenv("FIELD_MANIFEST_DIR", raising=False)


# --- resolution -------------------------------------------------------------


def test_absolute_ref_resolves_regardless_of_manifest_dir(tmp_path):
    elsewhere = write_manifest(tmp_path / "abs" / f"{AGENT_ID}.yaml")
    resolver = ManifestResolver(manifest_dir=tmp_path / "unrelated")

    manifest = resolver.resolve(str(elsewhere))

    assert isinstance(manifest, FieldManifest)
    assert manifest.agent.name == AGENT_ID
    assert list(manifest.delegation.scope) == SCOPE


def test_relative_ref_joins_the_injected_manifest_dir(tmp_path):
    write_manifest(tmp_path / "manifests" / f"{AGENT_ID}.yaml")
    resolver = ManifestResolver(manifest_dir=tmp_path / "manifests")

    manifest = resolver.resolve(f"{AGENT_ID}.yaml")

    assert manifest is not None and manifest.agent.name == AGENT_ID
    # ...and the same relative ref is unreadable from a different dir.
    assert ManifestResolver(manifest_dir=tmp_path).resolve(f"{AGENT_ID}.yaml") is None


def test_manifest_dir_defaults_to_field_manifest_dir_env(tmp_path, monkeypatch):
    write_manifest(tmp_path / "d" / f"{AGENT_ID}.yaml")
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path / "d"))

    assert ManifestResolver().resolve(f"{AGENT_ID}.yaml") is not None


def test_manifest_dir_defaults_to_cwd_when_env_unset(tmp_path, monkeypatch):
    write_manifest(tmp_path / f"{AGENT_ID}.yaml")
    monkeypatch.chdir(tmp_path)

    assert ManifestResolver().manifest_dir == Path(".")
    assert ManifestResolver().resolve(f"{AGENT_ID}.yaml") is not None


# --- fail-closed ------------------------------------------------------------


def test_missing_file_resolves_to_none(tmp_path):
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve(str(tmp_path / "nope.yaml")) is None
    assert resolver.resolve("nope.yaml") is None


def test_no_ref_resolves_to_none(tmp_path):
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve(None) is None
    assert resolver.resolve("") is None


def test_invalid_yaml_resolves_to_none(tmp_path):
    write_text(tmp_path / "broken.yaml", BROKEN_YAML)

    assert ManifestResolver(manifest_dir=tmp_path).resolve("broken.yaml") is None


def test_yaml_that_is_not_a_mapping_resolves_to_none(tmp_path):
    write_text(tmp_path / "scalar.yaml", "just a string\n")

    assert ManifestResolver(manifest_dir=tmp_path).resolve("scalar.yaml") is None


def test_schema_invalid_manifest_resolves_to_none(tmp_path):
    """Parses as YAML, fails validation - the fail-closed case that matters
    most: a manifest that LOOKS present must not be honoured."""
    data = manifest_data()
    data.pop("enforcement")
    write_manifest(tmp_path / "no-enforcement.yaml", data)

    resolver = ManifestResolver(manifest_dir=tmp_path)
    assert resolver.resolve("no-enforcement.yaml") is None


def test_schema_invalid_manifest_is_never_cached(tmp_path):
    """An invalid manifest stays refused on every call, and must not occupy
    the cache slot the corrected file will need."""
    path = write_manifest(tmp_path / f"{AGENT_ID}.yaml", {"schema_version": "1.0"})
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve(f"{AGENT_ID}.yaml") is None
    assert resolver.resolve(f"{AGENT_ID}.yaml") is None

    write_manifest(path)
    touch_newer(path)
    assert resolver.resolve(f"{AGENT_ID}.yaml") is not None


def test_url_form_ref_is_not_fetched(tmp_path):
    """Filesystem-only by design (field-core has no httpx). A URL ref is just
    an unreadable path - never a network call."""
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve("https://example.com/manifest.yaml") is None
    assert resolver.resolve_detail("https://example.com/manifest.yaml")[1] == "missing"


# --- mtime cache ------------------------------------------------------------


def test_cache_returns_the_same_object_until_the_file_changes(tmp_path):
    path = write_manifest(tmp_path / f"{AGENT_ID}.yaml")
    resolver = ManifestResolver(manifest_dir=tmp_path)

    first = resolver.resolve(f"{AGENT_ID}.yaml")
    second = resolver.resolve(f"{AGENT_ID}.yaml")
    assert first is second, "unchanged file should be served from the mtime cache"

    write_manifest(path, manifest_data(scope=["read timesheets"]))
    touch_newer(path)

    third = resolver.resolve(f"{AGENT_ID}.yaml")
    assert third is not first, "changed file must be re-read, not served stale"
    assert list(third.delegation.scope) == ["read timesheets"]


def test_cache_never_bleeds_between_refs(tmp_path):
    """One resolver, two agents: each ref resolves to its own manifest. This
    is the field-core half of the sentinel's tenant-isolation guarantee."""
    write_manifest(tmp_path / "a.yaml", manifest_data(name="agent-a"))
    write_manifest(tmp_path / "b.yaml", manifest_data(name="agent-b"))
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve("a.yaml").agent.name == "agent-a"
    assert resolver.resolve("b.yaml").agent.name == "agent-b"
    assert resolver.resolve("a.yaml").agent.name == "agent-a"


# --- resolve_detail reasons -------------------------------------------------


def test_detail_reason_ok(tmp_path):
    write_manifest(tmp_path / f"{AGENT_ID}.yaml")

    manifest, reason = ManifestResolver(manifest_dir=tmp_path).resolve_detail(
        f"{AGENT_ID}.yaml"
    )

    assert reason == "ok" and manifest is not None


def test_detail_reason_ok_on_a_cache_hit(tmp_path):
    write_manifest(tmp_path / f"{AGENT_ID}.yaml")
    resolver = ManifestResolver(manifest_dir=tmp_path)
    resolver.resolve_detail(f"{AGENT_ID}.yaml")

    manifest, reason = resolver.resolve_detail(f"{AGENT_ID}.yaml")

    assert reason == "ok" and manifest is not None


@pytest.mark.parametrize("ref", [None, ""])
def test_detail_reason_no_ref(tmp_path, ref):
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve_detail(ref) == (None, "no_ref")


def test_detail_reason_missing(tmp_path):
    resolver = ManifestResolver(manifest_dir=tmp_path)

    assert resolver.resolve_detail("nope.yaml") == (None, "missing")
    assert resolver.resolve_detail(str(tmp_path / "nope.yaml")) == (None, "missing")


def test_detail_reason_invalid_for_unparseable_yaml(tmp_path):
    write_text(tmp_path / "broken.yaml", BROKEN_YAML)

    resolver = ManifestResolver(manifest_dir=tmp_path)
    assert resolver.resolve_detail("broken.yaml") == (None, "invalid")


def test_detail_reason_invalid_not_missing_for_schema_invalid_file(tmp_path):
    """C3 labels which RACI default it fell back to. A file that EXISTS but
    fails validation is 'invalid'; only an absent file is 'missing'."""
    data = manifest_data()
    data.pop("enforcement")
    write_manifest(tmp_path / "bad.yaml", data)

    manifest, reason = ManifestResolver(manifest_dir=tmp_path).resolve_detail(
        "bad.yaml"
    )

    assert manifest is None
    assert reason == "invalid", (
        "an existing-but-invalid manifest must not read as 'missing'"
    )


def test_every_documented_reason_is_reachable(tmp_path):
    """RESOLVE_REASONS is the contract C3 switches on - none of it is dead."""
    write_manifest(tmp_path / "good.yaml")
    write_text(tmp_path / "bad.yaml", BROKEN_YAML)
    resolver = ManifestResolver(manifest_dir=tmp_path)

    seen = {
        resolver.resolve_detail(ref)[1]
        for ref in ["good.yaml", None, "nope.yaml", "bad.yaml"]
    }

    assert seen == set(RESOLVE_REASONS)


def test_resolve_agrees_with_resolve_detail_for_every_reason(tmp_path):
    """resolve() delegates to resolve_detail(); this fails if they drift."""
    write_manifest(tmp_path / "good.yaml")
    write_text(tmp_path / "bad.yaml", BROKEN_YAML)

    for ref in ["good.yaml", None, "", "nope.yaml", "bad.yaml"]:
        resolver = ManifestResolver(manifest_dir=tmp_path)
        detail = resolver.resolve_detail(ref)[0]
        assert resolver.resolve(ref) is detail


# --- module-level functions -------------------------------------------------


def test_resolve_manifest_function_absolute_and_relative(tmp_path):
    path = write_manifest(tmp_path / "mdir" / f"{AGENT_ID}.yaml")

    assert resolve_manifest(str(path)).agent.name == AGENT_ID
    assert (
        resolve_manifest(f"{AGENT_ID}.yaml", manifest_dir=tmp_path / "mdir").agent.name
        == AGENT_ID
    )
    assert resolve_manifest(f"{AGENT_ID}.yaml", manifest_dir=tmp_path) is None


def test_resolve_manifest_function_fails_closed(tmp_path):
    write_text(tmp_path / "broken.yaml", BROKEN_YAML)
    data = manifest_data()
    data.pop("enforcement")
    write_manifest(tmp_path / "schema-bad.yaml", data)

    assert resolve_manifest(None) is None
    assert resolve_manifest("nope.yaml", manifest_dir=tmp_path) is None
    assert resolve_manifest("broken.yaml", manifest_dir=tmp_path) is None
    assert resolve_manifest("schema-bad.yaml", manifest_dir=tmp_path) is None


def test_resolve_manifest_detail_function_reasons(tmp_path):
    write_manifest(tmp_path / "good.yaml")
    write_text(tmp_path / "broken.yaml", BROKEN_YAML)
    data = manifest_data()
    data.pop("enforcement")
    write_manifest(tmp_path / "schema-bad.yaml", data)

    assert resolve_manifest_detail("good.yaml", manifest_dir=tmp_path)[1] == "ok"
    assert resolve_manifest_detail(None, manifest_dir=tmp_path) == (None, "no_ref")
    assert resolve_manifest_detail("nope.yaml", manifest_dir=tmp_path) == (
        None,
        "missing",
    )
    assert resolve_manifest_detail("broken.yaml", manifest_dir=tmp_path) == (
        None,
        "invalid",
    )
    assert resolve_manifest_detail("schema-bad.yaml", manifest_dir=tmp_path) == (
        None,
        "invalid",
    )


def test_module_functions_honour_a_changed_field_manifest_dir(tmp_path, monkeypatch):
    """The per-dir resolver cache is keyed by the RESOLVED dir, so re-pointing
    FIELD_MANIFEST_DIR is never served a stale resolver."""
    write_manifest(
        tmp_path / "one" / f"{AGENT_ID}.yaml", manifest_data(name="agent-one")
    )
    write_manifest(
        tmp_path / "two" / f"{AGENT_ID}.yaml", manifest_data(name="agent-two")
    )

    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path / "one"))
    assert resolve_manifest(f"{AGENT_ID}.yaml").agent.name == "agent-one"

    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path / "two"))
    assert resolve_manifest(f"{AGENT_ID}.yaml").agent.name == "agent-two"


def test_module_function_shares_the_mtime_cache(tmp_path):
    mdir = tmp_path / "cached"
    path = write_manifest(mdir / f"{AGENT_ID}.yaml")

    first = resolve_manifest(f"{AGENT_ID}.yaml", manifest_dir=mdir)
    assert resolve_manifest(f"{AGENT_ID}.yaml", manifest_dir=mdir) is first

    write_manifest(path, manifest_data(scope=["read timesheets"]))
    touch_newer(path)

    assert resolve_manifest(f"{AGENT_ID}.yaml", manifest_dir=mdir) is not first


# --- the sentinel keeps importing the same class ----------------------------


def test_sentinel_reexports_the_field_core_class():
    """api.py, the sentinel conftest and field-agent's conftest all import
    ManifestResolver from conformance_sentinel.engine. It must stay importable
    there AND be the same object, so there is exactly one resolver."""
    engine = pytest.importorskip("conformance_sentinel.engine")

    assert engine.ManifestResolver is ManifestResolver


def test_field_core_does_not_need_httpx_for_manifest_resolution(tmp_path, monkeypatch):
    """field-core must not gain an httpx dependency. Resolution must work with
    httpx removed from sys.modules and unimportable."""
    import builtins
    import sys

    write_manifest(tmp_path / f"{AGENT_ID}.yaml")
    monkeypatch.delitem(sys.modules, "httpx", raising=False)
    real_import = builtins.__import__

    def no_httpx(name, *args, **kwargs):
        if name == "httpx" or name.startswith("httpx."):
            raise ImportError("httpx is not a field-core dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_httpx)

    assert (
        ManifestResolver(manifest_dir=tmp_path).resolve(f"{AGENT_ID}.yaml") is not None
    )
    assert resolve_manifest(f"{AGENT_ID}.yaml", manifest_dir=tmp_path) is not None


def test_a_ref_with_an_embedded_nul_is_missing_not_a_crash(tmp_path):
    """The registry stores manifest_ref verbatim, and ``Path.stat`` raises
    ValueError (not OSError) for an embedded NUL. Fail-closed means
    ``missing``, never an exception that 500s the sentinel or a replay."""
    write_manifest(tmp_path / f"{AGENT_ID}.yaml")
    resolver = ManifestResolver(manifest_dir=tmp_path)
    for ref in (f"{AGENT_ID}\x00.yaml", str(tmp_path / "a\x00b.yaml"), "manifests/a\x00b.yaml"):
        assert resolver.resolve_detail(ref) == (None, "missing"), ref
        assert resolver.resolve(ref) is None
        assert resolve_manifest_detail(ref, manifest_dir=tmp_path) == (None, "missing")
    assert resolver.resolve(f"{AGENT_ID}.yaml") is not None  # a good ref still resolves
