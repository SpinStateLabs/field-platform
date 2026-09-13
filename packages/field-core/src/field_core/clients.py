"""HTTP clients for the services delegation-authority depends on, plus the
shared filesystem manifest resolver.

Both HTTP clients accept an injected httpx-compatible client (FastAPI's
TestClient qualifies), so tests wire real service apps in-process.

Fail-closed rule (ENFORCED): if the sealed ledger cannot acknowledge the
event, the mint/revoke does not happen. Authority changes that cannot be
audited must not occur.

`ManifestResolver` is the one manifest resolver in the platform (lifted from
conformance_sentinel.engine, which now imports it from here). It is
filesystem-only by design: field-core must not gain an httpx dependency, so
URL-form manifest_refs are unsupported, as they always were.
"""

from __future__ import annotations

from field_core.authn import auth_headers

import os
from pathlib import Path
from typing import Any, Protocol

from field_core.manifest import FieldManifest
from field_core.validation import load_manifest, validate_manifest_data


class HttpLike(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...
    def get(self, url: str, **kwargs: Any) -> Any: ...
    def patch(self, url: str, **kwargs: Any) -> Any: ...


class LedgerUnreachableError(Exception):
    pass


class RegistryUnreachableError(Exception):
    pass


class AgentNotRegisteredError(Exception):
    pass


class AgentNotActiveError(Exception):
    def __init__(self, agent_id: str, status: str):
        self.status = status
        super().__init__(f"agent '{agent_id}' has status '{status}'")


class LedgerClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0, headers=auth_headers())

    def append(
        self, event_type: str, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        try:
            resp = self._client.post(
                f"{self._base}/events",
                json={"event_type": event_type, "payload": payload, "agent_id": agent_id},
            )
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 201:
            raise LedgerUnreachableError(
                f"ledger append returned {resp.status_code}: {resp.text}"
            )
        return resp.json()

    def retention_check(self) -> dict[str, Any]:
        """``GET /retention/check`` (C2): the estate retention policy vs every
        registered manifest. A transport error or any non-200 raises
        ``LedgerUnreachableError`` — a check that did not run is never "ok"."""
        try:
            resp = self._client.get(f"{self._base}/retention/check")
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 200:
            raise LedgerUnreachableError(
                f"ledger retention check returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    def events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """``GET /events`` (optionally one ``event_type``), in global order. A
        transport error, a non-200 or a body that is not a JSON list raises
        ``LedgerUnreachableError`` — a read that did not happen is never "no events"."""
        params = {"event_type": event_type} if event_type else {}
        try:
            resp = self._client.get(f"{self._base}/events", params=params)
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 200:
            raise LedgerUnreachableError(
                f"ledger events read returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise LedgerUnreachableError(f"ledger events read: not JSON: {exc}") from exc
        if not isinstance(body, list):
            raise LedgerUnreachableError(f"ledger events read returned {type(body).__name__}, not a list")
        return body


class RegistryClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_REGISTRY_URL", "http://127.0.0.1:8001"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0, headers=auth_headers())

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        try:
            resp = self._client.get(f"{self._base}/agents/{agent_id}")
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code == 404:
            raise AgentNotRegisteredError(agent_id)
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                f"registry returned {resp.status_code}: {resp.text}"
            )
        return resp.json()

    def require_active_agent(self, agent_id: str) -> dict[str, Any]:
        record = self.get_agent(agent_id)
        if record.get("status") != "active":
            raise AgentNotActiveError(agent_id, record.get("status", "<unknown>"))
        return record

    def list_agents(
        self, domain: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if domain:
            params["domain"] = domain
        if status:
            params["status"] = status
        try:
            resp = self._client.get(f"{self._base}/agents", params=params)
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                f"registry returned {resp.status_code}: {resp.text}"
            )
        return resp.json()

    def set_status(self, agent_id: str, status: str) -> dict[str, Any]:
        try:
            resp = self._client.patch(
                f"{self._base}/agents/{agent_id}", json={"status": status}
            )
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code == 404:
            raise AgentNotRegisteredError(agent_id)
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                f"registry returned {resp.status_code}: {resp.text}"
            )
        return resp.json()
# --- shared manifest resolver ------------------------------------------------
#
# Lifted verbatim from conformance_sentinel.engine (v1.1) so that the sentinel,
# delegation-authority, the ledger's retention check (C2 `GET /retention/check`,
# run inside the ledger container) and the crosswalk all resolve manifests the
# same way. Filesystem-only: no httpx, no URL refs.

#: Reasons returned by ``resolve_manifest_detail`` / ``ManifestResolver.resolve_detail``.
#: ``ok``      -> manifest loaded and schema-valid
#: ``no_ref``  -> the record carried no manifest_ref at all
#: ``missing`` -> a ref was given but no readable file is there
#: ``invalid`` -> the file exists but is unparseable or schema-invalid
RESOLVE_REASONS = ("ok", "no_ref", "missing", "invalid")


class ManifestResolver:
    """Loads + validates the manifest a registry record points at, with an
    mtime cache. manifest_ref may be absolute or relative to manifest_dir."""

    def __init__(self, manifest_dir: str | Path | None = None):
        self.manifest_dir = Path(
            manifest_dir or os.environ.get("FIELD_MANIFEST_DIR", ".")
        )
        self._cache: dict[str, tuple[float, FieldManifest]] = {}

    def resolve(self, manifest_ref: str | None) -> FieldManifest | None:
        """None = missing/invalid (caller blocks with I.manifest)."""
        return self.resolve_detail(manifest_ref)[0]

    def resolve_detail(
        self, manifest_ref: str | None
    ) -> tuple[FieldManifest | None, str]:
        """Same resolution as :meth:`resolve`, plus WHY it failed.

        Callers that pick a fallback (C3's RACI defaults) need to tell a
        manifest that was never referenced apart from one that is on disk but
        does not validate, so the distinction is deliberate and tested:
        a file that exists and fails validation is ``invalid``, not ``missing``.
        """
        if not manifest_ref:
            return None, "no_ref"
        path = Path(manifest_ref)
        if not path.is_absolute():
            path = self.manifest_dir / path
        try:
            mtime = path.stat().st_mtime
        except (OSError, ValueError):  # ValueError: an embedded NUL is no usable path
            return None, "missing"
        cached = self._cache.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1], "ok"
        try:
            data = load_manifest(path)
        except Exception:
            return None, "invalid"
        result = validate_manifest_data(data)
        if not result.ok:
            return None, "invalid"
        try:
            manifest = FieldManifest.from_dict(data)
        except Exception:
            return None, "invalid"
        self._cache[str(path)] = (mtime, manifest)
        return manifest, "ok"


#: One resolver per manifest_dir, so the mtime cache actually survives across
#: calls to the module-level functions below. Keyed by the RESOLVED directory
#: (env is read per call), so a changed FIELD_MANIFEST_DIR is never served a
#: stale resolver.
_RESOLVERS: dict[str, ManifestResolver] = {}


def _resolver_for(manifest_dir: str | Path | None) -> ManifestResolver:
    resolved = Path(manifest_dir or os.environ.get("FIELD_MANIFEST_DIR", "."))
    key = str(resolved)
    resolver = _RESOLVERS.get(key)
    if resolver is None:
        resolver = ManifestResolver(manifest_dir=resolved)
        _RESOLVERS[key] = resolver
    return resolver


def resolve_manifest(
    manifest_ref: str | None, manifest_dir: str | Path | None = None
) -> FieldManifest | None:
    """Resolve a manifest_ref to a validated FieldManifest, or None.

    Thin wrapper over :class:`ManifestResolver` — one resolver, one cache.
    """
    return _resolver_for(manifest_dir).resolve(manifest_ref)


def resolve_manifest_detail(
    manifest_ref: str | None, manifest_dir: str | Path | None = None
) -> tuple[FieldManifest | None, str]:
    """As :func:`resolve_manifest`, returning ``(manifest, reason)`` with
    reason in :data:`RESOLVE_REASONS`."""
    return _resolver_for(manifest_dir).resolve_detail(manifest_ref)
