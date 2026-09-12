"""Shared test hygiene for the kill-switch suite.

Two autouse guards, both about NOT leaking state between tests:

* ``FIELD_DATA_DIR`` is redirected into ``tmp_path`` so the default
  ``HeartbeatStore`` path can never write into the repo.
* ``FIELD_KILL_ENDPOINT_ALLOWLIST`` is cleared before every test, so a test
  that arms the outbound halt signal cannot leave it armed for the next one
  (the allowlist is read per call precisely so this works).
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FIELD_KILL_ENDPOINT_ALLOWLIST", raising=False)
    monkeypatch.delenv("FIELD_MANIFEST_DIR", raising=False)
