"""Shared test hygiene for the incident-replay suite.

Since C3 the engine's default ``ManifestResolver()`` reads
``FIELD_MANIFEST_DIR``, so a shell pointing it at a directory holding
``manifests/invoicing-agent.yaml`` (integration/demo does) changed the RACI
the reconstruction test asserts. One autouse guard makes the suite give the
same result in any shell:

* ``FIELD_MANIFEST_DIR`` points at an empty directory, so a relative
  ``manifest_ref`` never resolves against the caller's working tree;
* ``FIELD_DOA_ROSTER`` and ``FIELD_SHARED_SECRET`` are cleared, so the real
  delegation-authority mints without a roster and no app demands a header
  (both are read per request).
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path_factory.mktemp("no-manifests")))
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
