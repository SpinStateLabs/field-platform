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

Caller signatures (v1.2 F2b, GB10): when BOTH ``FIELD_LEDGER_CALLER_ID`` and
``FIELD_LEDGER_CALLER_KEY`` (a PEM path, Ed25519 private, the
``generate_keypair`` format, mounted only into this service) are set and the
key loads, every ``LedgerClient.append`` body also carries ``caller_id``,
``caller_ts`` (ISO 8601 UTC, now) and ``caller_signature`` (Ed25519 over the
canonical bytes of ``event_type``, ``agent_id``, ``payload``, ``caller_id``,
``caller_ts`` — ``field_core.signing.caller_signing_bytes``). Both unset ⇒
the body is exactly as before F2b. A key that is configured but cannot be
loaded ⇒ appends go UNSIGNED with ONE warning per process, never an
exception: a caller must still be able to revoke and kill, and the ledger's
FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE switch is the enforcement point. The
key is loaded once per ``CallerSigner`` (once per client), not per append.
"""

from __future__ import annotations

from field_core.authn import auth_headers

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from field_core.manifest import FieldManifest
from field_core.validation import load_manifest, validate_manifest_data

log = logging.getLogger("field_core.clients")

#: F2b env var names, spelled once.
CALLER_ID_ENV = "FIELD_LEDGER_CALLER_ID"
CALLER_KEY_ENV = "FIELD_LEDGER_CALLER_KEY"
#: One warning per process about a caller key that did not load (the
#: message names the env var and the failure class, never key material).
_caller_key_warned = False


def _warn_caller_key_once(message: str) -> None:
    global _caller_key_warned
    if _caller_key_warned:
        return
    _caller_key_warned = True
    log.warning("%s", message)


class CallerSigner:
    """F2b: this service's caller identity and its loaded Ed25519 key.

    Built ONCE from the environment (``from_env``), so the key file is read
    once per client, never per append. ``fields`` returns the three body
    keys an append gains (``caller_id``, ``caller_ts``, ``caller_signature``).
    The private key is never formatted into any message (``repr`` shows the
    caller id only)."""

    def __init__(self, caller_id: str, private_key: Any):
        self.caller_id = caller_id
        self._key = private_key

    def __repr__(self) -> str:
        return f"CallerSigner(caller_id={self.caller_id!r})"

    @classmethod
    def from_env(cls) -> "CallerSigner | None":
        """None (append unsigned, body as before F2b) when neither var is set.
        Set but unusable — only one of the two set, the key file missing,
        unreadable, not a PEM or not an Ed25519 private key — is ALSO None,
        after one warning per process; never an exception."""
        caller_id = os.environ.get(CALLER_ID_ENV, "").strip()
        key_path = os.environ.get(CALLER_KEY_ENV, "").strip()
        if not caller_id and not key_path:
            return None
        if not caller_id or not key_path:
            _warn_caller_key_once(
                f"caller signing off: {CALLER_ID_ENV} and {CALLER_KEY_ENV} must BOTH be set "
                f"(only {CALLER_ID_ENV if caller_id else CALLER_KEY_ENV} is); appending unsigned"
            )
            return None
        try:
            pem = Path(key_path).read_text(encoding="ascii")
        except (OSError, UnicodeError, ValueError) as exc:
            _warn_caller_key_once(
                f"caller signing off: {CALLER_KEY_ENV} unreadable ({type(exc).__name__}); "
                f"appending unsigned as {caller_id!r} would have signed"
            )
            return None
        # Imported here, not at module load: every service imports this module
        # at start and most never sign; cryptography's first import is slow.
        from field_core.signing import load_ed25519_private_key

        try:
            key = load_ed25519_private_key(pem)
        except ValueError as exc:
            _warn_caller_key_once(
                f"caller signing off: {CALLER_KEY_ENV} unusable ({exc}); appending unsigned"
            )
            return None
        finally:
            del pem
        return cls(caller_id, key)

    def fields(self, event_type: str, agent_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        """The three caller keys for one append, ``caller_ts`` = now (UTC)."""
        from field_core.signing import sign_caller

        caller_ts = datetime.now(timezone.utc).isoformat()
        signature = sign_caller(self._key, event_type=event_type, agent_id=agent_id, payload=payload,
                                caller_id=self.caller_id, caller_ts=caller_ts)
        return {"caller_id": self.caller_id, "caller_ts": caller_ts, "caller_signature": signature}


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
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None,
                 caller: CallerSigner | None = None):
        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=5.0, headers=auth_headers())
        # F2b: the caller key is loaded here, once per client (never per append).
        self._caller = caller if caller is not None else CallerSigner.from_env()

    def append_body(self, event_type: str, payload: dict[str, Any], agent_id: str | None) -> dict[str, Any]:
        """The POST /events body: exactly the pre-F2b three keys, plus the
        three caller keys when this client signs. A payload the canonical
        JSON cannot encode is sent unsigned (one warning per process), never
        an exception here — the transport reports it as it always did."""
        body: dict[str, Any] = {"event_type": event_type, "payload": payload, "agent_id": agent_id}
        if self._caller is not None:
            try:
                body.update(self._caller.fields(event_type, agent_id, payload))
            except (TypeError, ValueError) as exc:
                _warn_caller_key_once(
                    f"caller signing skipped: payload not canonicalisable ({type(exc).__name__}); "
                    "appending unsigned"
                )
        return body

    def append(
        self, event_type: str, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        try:
            resp = self._client.post(
                f"{self._base}/events", json=self.append_body(event_type, payload, agent_id),
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
