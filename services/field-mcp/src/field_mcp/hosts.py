"""The internal-host predicate for a configured base URL: ``field_core.hosts.is_internal_host`` with names not trusted
by their shape, so only loopback, the private address ranges and ``localhost`` pass. ``tests/test_config.py``
(``test_base_url_refused``, ``test_base_url_accepted``) pins the corpus.
"""
from __future__ import annotations

from field_core.hosts import is_internal_host as _core


def is_internal_host(host: str | None) -> bool:
    return _core(host, allow_names=False)
