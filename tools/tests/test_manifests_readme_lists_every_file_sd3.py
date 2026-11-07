"""manifests/README.md names every file in manifests/ (scout S-D3). Three files
(conformance-sentinel, force-gateway, compliance-crosswalk: byte copies of the services'
packaged self-manifests, kept in sync by test_self_manifests_in_sync.py) sat in the
directory with no row, under a heading that called every file one of "Spin State's own
agents"."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "manifests" / "README.md").read_text(encoding="utf-8")
FILES = sorted(p.name for p in (ROOT / "manifests").iterdir() if p.is_file() and p.name != "README.md")
SELF = ["conformance-sentinel.yaml", "force-gateway.yaml", "compliance-crosswalk.yaml"]


def test_the_directory_is_not_empty():
    assert FILES, "manifests/ holds no manifest: the pin below would pass vacuously"


@pytest.mark.parametrize("name", FILES)
def test_every_file_in_manifests_is_named_in_the_readme(name):
    stem = name.rsplit(".", 1)[0]
    assert name in README or stem in README, f"manifests/{name} has no mention in manifests/README.md"


@pytest.mark.parametrize("name", SELF)
def test_the_three_self_manifests_have_a_table_row(name):
    rows = [ln for ln in README.splitlines() if ln.startswith("|") and f"`{name}`" in ln]
    assert len(rows) == 1, f"expected one table row for {name}, found {len(rows)}"


def test_the_rows_say_what_they_are_and_name_the_sync_test():
    text = " ".join(ln for ln in README.splitlines() if ln.startswith("|"))
    assert "test_self_manifests_in_sync" in text
    assert "self_manifest.yaml" in text and "byte" in text.lower()


def test_the_heading_no_longer_claims_every_file_is_an_agent():
    first = README.splitlines()[0]
    assert "platform" in first.lower() or "services" in first.lower()


def test_no_estate_address_or_deploy_status_was_added():
    for needle in ("fly.dev", "100.", "192.168.", "10.0.", "deployed", "armed"):
        # the pre-existing text may name Fly or arming in a how-to; only new self-manifest rows are checked
        rows = [ln for ln in README.splitlines() if ln.startswith("|") and any(f"`{n}`" in ln for n in SELF)]
        assert not any(needle in r for r in rows), (needle, rows)
