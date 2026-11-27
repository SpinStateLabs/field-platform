"""OUR agent's manifest as the registry records it, for an outbound crossing.

The registry record names a manifest file (``manifest_ref``); it is read with the shared resolver's bounded read and
relative-path rule. Every failure is a fixed text: no path, no upstream body.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from field_core.clients import AgentNotRegisteredError, ManifestResolver, RegistryClient
from field_core.validation import parse_manifest_text

NOT_REGISTERED = "our agent is not registered"
REGISTRY_UNREAD = "the agent registry could not be read"
NOT_ACTIVE = "our agent is not active in the registry"
NO_REF = "the registry record names no manifest"
UNREADABLE = "the registered manifest cannot be read"

log = logging.getLogger(__name__)


class RegisteredManifest:
    def __init__(self, registry: Any = None, resolver: ManifestResolver | None = None):
        self._registry = registry
        self._resolver = resolver

    def read(self, agent_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """``(manifest, None)``, or ``(None, why)``."""
        if self._registry is None:
            self._registry = RegistryClient()
        try:
            record = self._registry.get_agent(agent_id)
        except AgentNotRegisteredError:
            return None, NOT_REGISTERED
        except Exception as exc:
            log.warning("registry record not read (%s)", type(exc).__name__)
            return None, REGISTRY_UNREAD
        if record.get("status") != "active":
            return None, NOT_ACTIVE
        ref = record.get("manifest_ref")
        if not isinstance(ref, str) or not ref:
            return None, NO_REF
        resolver = self._resolver or ManifestResolver()
        path = Path(ref)
        if not path.is_absolute():
            path = resolver.manifest_dir / path
        # the resolver's own bounded read: a device, a directory or an oversized file is never read
        raw = resolver._read_bounded(path)
        if not isinstance(raw, bytes):
            return None, UNREADABLE
        try:
            data = parse_manifest_text(raw.decode("utf-8"), path)
        except Exception as exc:
            log.warning("registered manifest not parsed (%s)", type(exc).__name__)
            return None, UNREADABLE
        return (data, None) if isinstance(data, dict) else (None, UNREADABLE)
