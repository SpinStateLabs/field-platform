"""The ONLY place ``anthropic`` is imported.

CI installs every service with ``--no-deps`` and the test suite runs without
the ``anthropic`` package, so nothing may import it at module import time.
``make_client`` imports it inside the function; the image installs it
(``services/claude-approver/Dockerfile``), the tests inject a fake instead.

The key is passed straight to the SDK constructor. It is never logged, never
echoed, and never put in an exception message by this module.
"""

from __future__ import annotations

from typing import Any


def make_client(key: str) -> Any:
    """Build the Managed Agents client from the org API key.

    The SDK adds the ``managed-agents-2026-04-01`` beta header itself on every
    ``client.beta.sessions.*`` / ``client.beta.agents.*`` call (claude-api
    skill, ``shared/managed-agents-api-reference.md`` "Beta Headers")."""
    import anthropic  # noqa: PLC0415 - deliberately local, see module docstring

    return anthropic.Anthropic(api_key=key)
