"""The registry's agent-id rule, in one place.

The registry stores ids matching ``[a-z0-9][a-z0-9._-]*`` (``agent_registry.models``). A caller outside the registry
that puts an id into a URL or a ledger row also bounds its length: 128 characters, below the sealed ledger's 200 for
an ``agent_id`` (a longer one is refused there, so an action on it could not be recorded) and above the 64 the registry
allows a NEW id."""

from __future__ import annotations

import re

#: Use with ``fullmatch``. The registry's stored-id pattern; a NEW id is held to a stricter one there.
REGISTRY_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")
#: The same rule, anchored, for a pydantic ``Field(pattern=...)`` (with ``max_length=REGISTRY_ID_MAX_LENGTH``).
REGISTRY_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
REGISTRY_ID_MAX_LENGTH = 128


def registry_id_ok(value: object) -> bool:
    """True for an agent id that may be put into a registry URL and keyed on in the ledger."""
    return (isinstance(value, str) and len(value) <= REGISTRY_ID_MAX_LENGTH
            and REGISTRY_ID_RE.fullmatch(value) is not None)
