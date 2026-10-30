"""HTTP clients for the services delegation-authority depends on, plus the
shared filesystem manifest resolver.

Both HTTP clients accept an injected httpx-compatible client (FastAPI's
TestClient qualifies), so tests wire real service apps in-process.

Fail-closed rule (ENFORCED): if the sealed ledger cannot acknowledge the
event, the mint/revoke does not happen. Authority changes that cannot be
audited must not occur.

Auth headers (Phase G C-4, ENFORCED by tests/test_clients_per_request_headers_c4.py):
a client built here (no injected client) reads its auth headers on EVERY
request (``x-field-auth``, plus the operator pair on a guarded route only,
C-511), never once at construction, so a rotated or revoked operator key or
shared secret takes effect on the next request without restarting the
service. An injected client is the caller's and gets nothing added.

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

Signed operator events (2026-10-27, GB10 Stage 1 LOG-ONLY): the ledger
verifies a caller signature over the payload it will STORE, which under an
armed Phase G mode is ``operator_auth.admit_ledger_event``'s output (reserved
operator keys stripped unless the caller may attribute the type; on
``operator.unauthenticated`` / ``operator.refused`` also ``claimed_id``
masked and ``self_reported`` stamped). A signing client therefore signs and
sends exactly that payload: ``signed_append_body`` runs the same admission,
with the headers the request will carry, before signing. Without it every
LOG-ONLY ``operator.unauthenticated`` record (and any start-type event whose
reserved keys the ledger strips) was refused 403 "invalid caller signature"
and a stop-type one landed ``caller_unsigned``. An unsigned client's body is
unchanged (the ledger still applies the admission itself).
"""

from __future__ import annotations

from field_core.guarded_operator import (LEDGER_GUARDED, REGISTRY_GUARDED, Routes, request_headers)

import logging
from collections.abc import Mapping
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from field_core.errors import upstream_error
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
    """The ledger did not acknowledge an append or a read. ``status_code`` is
    the HTTP status when the ledger answered (403, 503, ...), None when it
    could not be reached (transport error, timeout)."""

    def __init__(self, message: str = "", status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _sent_headers(client: Any) -> Mapping[str, str]:
    """The headers an injected client sends on every request (an httpx
    client's or a TestClient's ``headers``), {} when it has none."""
    h = getattr(client, "headers", None)
    try:
        return dict(h) if h else {}
    except (TypeError, ValueError):
        return {}


def _as_the_ledger_stores_it(event_type: str, payload: dict[str, Any],
                             sent_headers: Mapping[str, str]) -> dict[str, Any]:
    """The payload the ledger's ``POST /events`` admission will store for this
    append from a caller presenting ``sent_headers`` (the very function the
    ledger runs, ``operator_auth.admit_ledger_event``). Flags OFF: ``payload``
    itself. A type the ledger refuses outright is returned as built (the
    ledger refuses it either way)."""
    from field_core.operator_auth import OperatorRefused, admit_ledger_event

    try:
        return admit_ledger_event(event_type, payload, sent_headers)
    except OperatorRefused:
        return payload


def signed_append_body(caller: "CallerSigner | None", event_type: str, payload: dict[str, Any],
                       agent_id: str | None,
                       sent_headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The POST /events body for one append: exactly the pre-F2b three keys,
    plus the three caller keys when ``caller`` signs. Every service's ledger
    append (normal events AND the operator layer's ``operator.unauthenticated``
    / ``operator.refused`` records) is built here.

    Phase G: inside a guarded request the authenticated operator is merged into
    the payload BEFORE it is signed ({} when the mode is off; reserved keys a
    caller supplied are dropped, ``merge_payload``). When ``caller`` signs, the
    payload is then put in the form the ledger will store
    (``_as_the_ledger_stores_it`` with ``sent_headers``, the headers the
    request carries), so the signature verifies over the stored payload. A
    payload the canonical JSON cannot encode is sent unsigned (one warning per
    process), never an exception here."""
    from field_core.operator_auth import merge_payload

    payload = merge_payload(payload)
    if caller is not None:
        payload = _as_the_ledger_stores_it(event_type, payload, sent_headers or {})
    body: dict[str, Any] = {"event_type": event_type, "payload": payload, "agent_id": agent_id}
    if caller is not None:
        try:
            body.update(caller.fields(event_type, agent_id, payload))
        except (TypeError, ValueError) as exc:
            _warn_caller_key_once(
                f"caller signing skipped: payload not canonicalisable ({type(exc).__name__}); "
                "appending unsigned"
            )
    return body


class RegistryUnreachableError(Exception):
    pass


class AgentNotRegisteredError(Exception):
    pass


class AgentNotActiveError(Exception):
    def __init__(self, agent_id: str, status: str):
        self.status = status
        super().__init__(f"agent '{agent_id}' has status '{status}'")


def _request_auth(own_client: bool, method: str, path: str, routes: Routes) -> dict[str, Any]:
    """Phase G C-4: the auth headers for ONE request, read now.

    A client this module built itself carries no fixed auth headers; every
    request gets ``x-field-auth`` (when FIELD_SHARED_SECRET is set) at call
    time, plus the service's own operator pair ONLY when (method, path) is a
    guarded route of the target (``routes``, C-511: a read never carries the
    pair), so a rotated or revoked key takes effect on the next request without
    a restart. An injected client belongs to its caller and is called exactly
    as before (nothing added). Called inside each method's ``try``, so a
    failure to build the headers is reported like any transport failure."""
    return {"headers": request_headers(method, path, routes)} if own_client else {}


class HeaderCollisionError(ValueError):
    """A per-call header names a header the client already sets for that
    request (``RegistryClient.set_status(extra_headers=...)``)."""


def _with_extra_headers(base: Mapping[str, str], extra: Mapping[str, str]) -> dict[str, str]:
    """``base`` then ``extra``, in that order; a name in both (without case) is
    refused, so ``extra`` can add headers but never replace one."""
    taken = {k.lower() for k in base}
    clash = sorted(k for k in extra if k.lower() in taken)
    if clash:
        raise HeaderCollisionError(f"per-call header(s) {clash} would replace a header "
                                   "the client sets itself")
    return {**base, **extra}


class LedgerClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None,
                 caller: CallerSigner | None = None):
        self._client = client
        self._own_client = client is None
        self._base = (base_url or os.environ.get(
            "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
        )).rstrip("/")
        if self._client is None:
            import httpx

            # No headers here (C-4): they are built per request (_request_auth).
            self._client = httpx.Client(timeout=5.0)
        # F2b: the caller key is loaded here, once per client (never per append).
        self._caller = caller if caller is not None else CallerSigner.from_env()

    def append_body(self, event_type: str, payload: dict[str, Any], agent_id: str | None,
                    sent_headers: Mapping[str, str] | None = None) -> dict[str, Any]:
        """The POST /events body (``signed_append_body`` with this client's
        signer). ``sent_headers``: the headers the request will carry; None =
        the injected client's own headers (a client built here: none)."""
        if sent_headers is None:
            sent_headers = {} if self._own_client else _sent_headers(self._client)
        return signed_append_body(self._caller, event_type, payload, agent_id, sent_headers)

    def append(
        self, event_type: str, payload: dict[str, Any], agent_id: str | None = None
    ) -> dict[str, Any]:
        try:
            auth = _request_auth(self._own_client, "POST", "/events", LEDGER_GUARDED)
            sent = auth.get("headers", {}) if self._own_client else _sent_headers(self._client)
            resp = self._client.post(
                f"{self._base}/events",
                json=self.append_body(event_type, payload, agent_id, sent_headers=sent),
                **auth,
            )
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 201:
            raise LedgerUnreachableError(
                upstream_error(resp, "ledger append"),
                status_code=resp.status_code,
            )
        return resp.json()

    def retention_check(self) -> dict[str, Any]:
        """``GET /retention/check`` (C2): the estate retention policy vs every
        registered manifest. A transport error or any non-200 raises
        ``LedgerUnreachableError`` — a check that did not run is never "ok"."""
        try:
            resp = self._client.get(f"{self._base}/retention/check",
                                    **_request_auth(self._own_client, "GET", "/retention/check", LEDGER_GUARDED))
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 200:
            raise LedgerUnreachableError(
                upstream_error(resp, "ledger retention check")
            )
        return resp.json()

    def events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """``GET /events`` (optionally one ``event_type``), in global order. A
        transport error, a non-200 or a body that is not a JSON list raises
        ``LedgerUnreachableError`` — a read that did not happen is never "no events"."""
        params = {"event_type": event_type} if event_type else {}
        try:
            resp = self._client.get(f"{self._base}/events", params=params,
                                    **_request_auth(self._own_client, "GET", "/events", LEDGER_GUARDED))
        except Exception as exc:
            raise LedgerUnreachableError(str(exc)) from exc
        if resp.status_code != 200:
            raise LedgerUnreachableError(
                upstream_error(resp, "ledger events read")
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
        self._own_client = client is None
        self._base = (base_url or os.environ.get(
            "FIELD_REGISTRY_URL", "http://127.0.0.1:8001"
        )).rstrip("/")
        if self._client is None:
            import httpx

            # No headers here (C-4): the kill-switch's S1 hop must present the
            # CURRENT svc identity on every PATCH, not the one it started with.
            self._client = httpx.Client(timeout=5.0)

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        try:
            resp = self._client.get(f"{self._base}/agents/{agent_id}",
                                    **_request_auth(self._own_client, "GET", f"/agents/{agent_id}", REGISTRY_GUARDED))
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code == 404:
            raise AgentNotRegisteredError(agent_id)
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                upstream_error(resp, "registry")
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
            resp = self._client.get(f"{self._base}/agents", params=params,
                                    **_request_auth(self._own_client, "GET", "/agents", REGISTRY_GUARDED))
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                upstream_error(resp, "registry")
            )
        return resp.json()

    def set_status(self, agent_id: str, status: str, *,
                   extra_headers: Mapping[str, str] | None = None) -> dict[str, Any]:
        """``PATCH /agents/{agent_id}`` with ``{"status": status}``.

        ``extra_headers`` (Phase G C-12): headers added to THIS one request,
        after the per-request auth headers (``_request_auth``). The kill-switch
        sends ``x-field-operator-on-behalf-of`` through it. A name that the
        client already sets for the request (an auth header, compared without
        case) is refused with :class:`HeaderCollisionError` before anything is
        sent: a per-call header never replaces the caller's identity. ``None``
        (the default) sends exactly what this method sent before the argument
        existed."""
        try:
            auth = _request_auth(self._own_client, "PATCH", f"/agents/{agent_id}", REGISTRY_GUARDED)
            if extra_headers is not None:
                auth = {"headers": _with_extra_headers(auth.get("headers", {}), extra_headers)}
            resp = self._client.patch(
                f"{self._base}/agents/{agent_id}", json={"status": status},
                **auth,
            )
        except HeaderCollisionError:
            raise
        except Exception as exc:
            raise RegistryUnreachableError(str(exc)) from exc
        if resp.status_code == 404:
            raise AgentNotRegisteredError(agent_id)
        if resp.status_code != 200:
            raise RegistryUnreachableError(
                upstream_error(resp, "registry")
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
