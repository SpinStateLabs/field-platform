"""Shared test hygiene for the agent-registry suite.

v1.2 D3b: ``POST /agents`` now refuses a SET ``manifest_ref`` that does not
resolve (422), through field-core's shared resolver, against
``FIELD_MANIFEST_DIR``. The suite's registrations name
``manifests/invoicing-agent.yaml`` — a relative ref — so one autouse guard
points ``FIELD_MANIFEST_DIR`` at ``tests/fixtures``, where that ref IS a real,
``field validate``-VALID manifest (a copy of
``integration/demo/manifests/invoicing-agent.yaml`` taken before v1.2 D1 added
its ``enforcement.rate_limits`` block; nothing the registry checks reads that
block, so the copy was not refreshed). The tests themselves are
unchanged: their ref now resolves in any shell, instead of depending on the
caller's working tree. Tests that exercise the refusal set their own
directory with ``monkeypatch.setenv`` after this fixture has run.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _manifest_dir_holds_the_suites_manifest(monkeypatch):
    assert (FIXTURES / "manifests" / "invoicing-agent.yaml").is_file()
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(FIXTURES))
