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

# Upper bound on the reply body any SDK client will read. A peer that streams more is refused. The SDK asks for an
# uncompressed reply (Accept-Encoding: identity) and refuses any other Content-Encoding, so the bytes counted on the wire
# are the bytes held in memory: a compressed reply is never decoded, so a gzip bomb cannot expand past the cap.
MAX_RESPONSE_BYTES = 1_048_576

_FRAMING_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


class ResponseTooLarge(Exception):
    """A reply body exceeded MAX_RESPONSE_BYTES. The text is fixed; it never carries body bytes."""

    def __init__(self) -> None:
        super().__init__(f"upstream reply exceeded the {MAX_RESPONSE_BYTES}-byte read cap")


class UnexpectedContentEncoding(ResponseTooLarge):
    """A streamed reply carried a Content-Encoding other than ``identity`` although the SDK asked for ``identity``.
    Refused before any body byte is read or decoded (a compressed reply can decode to far more than the cap). A
    subclass of ResponseTooLarge so every caller that handles the cap handles this too. The text is fixed."""

    def __init__(self) -> None:
        Exception.__init__(self, "upstream reply used a Content-Encoding the client did not ask for (identity only)")


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
        # The SDK never accepts a compressed reply (see MAX_RESPONSE_BYTES): any caller spelling of Accept-Encoding is
        # replaced by identity.
        headers = {k: v for k, v in headers.items() if _lower(k) != "accept-encoding"}
        headers["Accept-Encoding"] = "identity"
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
        # Count RAW bytes while streaming (Content-Length may be absent or false). Only an identity reply is read, so
        # raw bytes are the body: iter_bytes() would decode each raw read in full before the count could stop it.
        # R2 C4: never follow a redirect here (an injected client that follows them would read 3xx bodies itself)
        with stream(verb.upper(), url, **{**kw, "follow_redirects": False}) as resp:
            encoding = (resp.headers.get("content-encoding") or "identity").strip().lower()
            if encoding not in ("", "identity"):
                raise UnexpectedContentEncoding()
            if resp.is_stream_consumed:
                # Already buffered (an in-process client such as a starlette TestClient, or a mock reply read before it
                # was handed back): iter_raw() would raise StreamConsumed. The bytes are already in memory, so the cap
                # can only refuse them, not bound the read; real network streams are never consumed here.
                body = resp.content
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ResponseTooLarge()
                chunks = [body]
            else:
                chunks, total = [], 0
                for chunk in resp.iter_raw():
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
