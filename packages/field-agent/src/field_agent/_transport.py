"""Per-request auth-header attachment.

``field_core.authn.auth_headers()`` is read at CALL time, not at client
construction — matching the server middleware, which also reads the secret
per request. A secret exported after the client was built is therefore
honored, and injected test clients get the header for free.
"""

from __future__ import annotations

import httpx
from field_core.authn import auth_headers

from typing import Any

# Upper bound on the reply body any SDK client will read (decoded bytes). A peer that streams more is refused.
MAX_RESPONSE_BYTES = 1_048_576

_FRAMING_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


class ResponseTooLarge(Exception):
    """A reply body exceeded MAX_RESPONSE_BYTES. The text is fixed; it never carries body bytes."""

    def __init__(self) -> None:
        super().__init__(f"upstream reply exceeded the {MAX_RESPONSE_BYTES}-byte read cap")


class AuthedClient:
    """Wrap any httpx-compatible client; merge fresh auth headers per call."""

    def __init__(self, inner: Any):
        self._inner = inner

    def _kw(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", None) or {})
        for key, value in auth_headers().items():
            headers.setdefault(key, value)
        kwargs["headers"] = headers
        return kwargs

    def _send(self, verb: str, url: str, kwargs: dict[str, Any]) -> Any:
        kw = self._kw(kwargs)
        stream = getattr(self._inner, "stream", None)
        if stream is None:  # injected client without streaming: best-effort check after the fact
            resp = getattr(self._inner, verb)(url, **kw)
            content = getattr(resp, "content", None)
            if isinstance(content, (bytes, bytearray)) and len(content) > MAX_RESPONSE_BYTES:
                raise ResponseTooLarge()
            return resp
        # Count decoded bytes while streaming: Content-Length may be absent or false.
        with stream(verb.upper(), url, **kw) as resp:
            chunks, total = [], 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ResponseTooLarge()
                chunks.append(chunk)
            headers = [(k, v) for k, v in resp.headers.multi_items() if k.lower() not in _FRAMING_HEADERS]
            return httpx.Response(resp.status_code, headers=headers, content=b"".join(chunks), request=resp.request)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._send("post", url, kwargs)

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._send("get", url, kwargs)

    def patch(self, url: str, **kwargs: Any) -> Any:
        return self._send("patch", url, kwargs)
