"""Per-request auth-header attachment.

``field_core.authn.auth_headers()`` is read at CALL time, not at client
construction — matching the server middleware, which also reads the secret
per request. A secret exported after the client was built is therefore
honored, and injected test clients get the header for free.
"""

from __future__ import annotations

from field_core.authn import auth_headers

from typing import Any


def _lower(name: Any) -> str:
    return (name.decode("latin-1") if isinstance(name, bytes) else str(name)).lower()


class AuthedClient:
    """Wrap any httpx-compatible client; merge fresh auth headers per call."""

    def __init__(self, inner: Any):
        self._inner = inner

    def _kw(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """A copy of the caller's headers plus each auth header the caller did not supply. Header names are
        case-insensitive: a caller's ``X-Field-Auth`` wins over the injected ``x-field-auth`` and one name is never sent
        twice (the caller's dict is not mutated)."""
        headers = dict(kwargs.pop("headers", None) or {})
        supplied = {_lower(key) for key in headers}
        for key, value in auth_headers().items():
            if key.lower() not in supplied:
                headers[key] = value
        kwargs["headers"] = headers
        return kwargs

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._inner.post(url, **self._kw(kwargs))

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._inner.get(url, **self._kw(kwargs))

    def patch(self, url: str, **kwargs: Any) -> Any:
        return self._inner.patch(url, **self._kw(kwargs))
