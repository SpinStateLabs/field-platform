"""The one constructor for a platform HTTP client (C-487; Lane 10 design note, reviewer C-55 and C-462).

Every secret-bearing call (the perimeter header ``x-field-auth``, an operator pair, a token) must go to the
host the caller named and nowhere else. A stock ``httpx.Client`` reads HTTP_PROXY / HTTPS_PROXY / ALL_PROXY
and NO_PROXY from the process environment and follows redirects only when asked; either default can send
those headers to a place nobody chose. :func:`client` and :func:`async_client` fix that in one place:

* ``trust_env=False``: no environment proxy. What else ``trust_env=False`` turns off, in the httpx 0.28.1
  source read for this change: ``SSL_CERT_FILE`` and ``SSL_CERT_DIR`` are no longer read when ``verify`` is
  left at its default (httpx/_config.py:34-37). A caller that needs a private CA passes ``verify=`` an
  ``ssl.SSLContext`` itself. Nothing else was found (a netrc is used only through an explicit
  ``NetRCAuth`` in that version).
* ``follow_redirects=False``: a 3xx is an answer, never a second request that carries the headers.
* ``timeout`` is REQUIRED (keyword only): ``None`` (httpx's "wait forever") and a non-positive number are
  refused. An ``httpx.Timeout`` object is accepted as given.
* a caller cannot override ``trust_env``, ``follow_redirects``, ``proxy``, ``proxies`` or ``mounts``.
* the ONE proxy is the explicit ``FIELD_EGRESS_PROXY`` (an http or https URL with a host; blank means
  none). A bad value is refused with a message that does not include it (it may carry credentials).

httpx is imported inside the functions, as the other field-core callers do, so importing this module needs
no HTTP library."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

ENV_EGRESS_PROXY = "FIELD_EGRESS_PROXY"

_PINNED = ("trust_env", "follow_redirects", "proxy", "proxies", "mounts")


def _egress_proxy() -> str | None:
    raw = os.environ.get("FIELD_EGRESS_PROXY", "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        ok = parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:
        ok = False
    if not ok:
        # never echo the value: a proxy URL may carry credentials
        raise ValueError(f"{ENV_EGRESS_PROXY} must be an http or https URL with a host")
    return raw


def _checked(timeout, kw: dict) -> dict:
    for key in _PINNED:
        if key in kw:
            raise ValueError(f"{key} is fixed by field_core.http and cannot be passed")
    import httpx

    if isinstance(timeout, httpx.Timeout):
        pass
    elif isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number of seconds or an httpx.Timeout")
    args = dict(kw, timeout=timeout)
    proxy = _egress_proxy()
    if proxy is not None:
        args["proxy"] = proxy
    return args


def client(*, timeout, **kw):
    """A synchronous ``httpx.Client`` with the pinned settings above."""
    import httpx

    # the two literals are on the call itself: tools/tests/test_http_env_proxy_lint_c57.py reads them there
    return httpx.Client(trust_env=False, follow_redirects=False, **_checked(timeout, kw))


def async_client(*, timeout, **kw):
    """An ``httpx.AsyncClient`` with the pinned settings above."""
    import httpx

    return httpx.AsyncClient(trust_env=False, follow_redirects=False, **_checked(timeout, kw))
