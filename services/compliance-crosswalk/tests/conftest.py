"""Shared test hygiene for the crosswalk suite (v1.2 D4).

Autouse, for every test:

* **Offline by construction.** ``regwatch._client_factory`` — the one place
  the default fetcher builds its outbound ``httpx.Client`` — is replaced by a
  factory that raises. A test that forgets to inject a fake fetcher fails
  loudly instead of reaching EUR-Lex, OSFI or NIST. (``TestClient`` has its
  own in-process transport and is unaffected.) The single exception is a
  test marked ``live_fetch``, which also skips unless
  ``CROSSWALK_LIVE_FETCH=1`` — the manual proof that the real hosts answer.
* ``FIELD_DATA_DIR`` points into ``tmp_path`` so a default ``StaleStore()``
  never writes into the working directory; ``FIELD_SHARED_SECRET`` and
  ``FIELD_CROSSWALK_EVERY`` start unset (tests that need them set them).
"""

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_fetch: reads the real regulatory hosts; runs only with "
        "CROSSWALK_LIVE_FETCH=1",
    )


class NetworkRefused(RuntimeError):
    pass


def _refuse_network():
    raise NetworkRefused(
        "tests are offline: inject a fake fetcher (create_app(fetcher=...), "
        "run_check(fetcher=...)) or mark the test live_fetch"
    )


@pytest.fixture(autouse=True)
def _offline_and_isolated(request, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv("FIELD_CROSSWALK_EVERY", raising=False)
    if request.node.get_closest_marker("live_fetch") is not None:
        if os.environ.get("CROSSWALK_LIVE_FETCH") != "1":
            pytest.skip("live fetch: set CROSSWALK_LIVE_FETCH=1 to read the real hosts")
        return
    from compliance_crosswalk import regwatch

    monkeypatch.setattr(regwatch, "_client_factory", _refuse_network)
