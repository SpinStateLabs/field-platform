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
* ``timeout`` is REQUIRED (keyword only): ``None`` (httpx's "wait forever"), a non-positive or non-finite
  number and a bool are refused. An ``httpx.Timeout`` object is accepted only when its connect, read, write
  and pool values are all positive finite numbers (a ``Timeout(None)``, or one with any None part, is the
  same "wait forever" and is refused too; reviewer C-746 F-C746-1).
* a caller cannot pass ``trust_env``, ``follow_redirects``, ``proxy``, ``proxies``, ``mounts``,
  ``transport``, ``event_hooks`` or ``cert``, and ``verify`` only as ``True`` or an ``ssl.SSLContext`` the
  caller built (a private CA goes in that way; ``verify=False`` or a path string is refused; C-746 F-C746-2).
  Everything else (``headers``, ``base_url``, ``auth``, ``limits``, ...) passes through unchanged: the pinned
  list is the contract, not "nothing else can be set".
* a timeout (or any part of an ``httpx.Timeout``) above ``MAX_TIMEOUT_S`` (3600 s) is refused: a finite but absurd
  value is "wait forever" in practice (C-778 F-C778-1); an ``ssl.SSLContext`` passed as ``verify`` must require the
  certificate and check the host name (a context that does neither is ``verify=False`` by another route, F-C778-2);
  a ``base_url`` must be an http(s) URL with a host, no userinfo and no link-local address (F-C778-3).
* ``FIELD_EGRESS_PROXY`` may be an ``http://`` proxy: everything the client sends, the perimeter header included,
  then crosses that hop in clear. That is the operator's explicit choice, so it is allowed and stated here, not
  refused (F-C778-4); an https proxy keeps the header encrypted to the proxy.
* there is NO response size cap here: a caller that needs one bounds its own reads (FieldClient and the canary
  do, with ``MAX_RESPONSE_BYTES``; C-746 F-C746-3).
* the ONE proxy is the explicit ``FIELD_EGRESS_PROXY`` (an http or https URL with a host; blank means
  none). A bad value is refused with a message that does not include it (it may carry credentials).

httpx is imported inside the functions, as the other field-core callers do, so importing this module needs
no HTTP library."""

from __future__ import annotations

import ipaddress
import math
import os
import ssl
from urllib.parse import urlsplit

ENV_EGRESS_PROXY = "FIELD_EGRESS_PROXY"

#: the longest a platform call may wait for any part of a request, in seconds (reviewer C-778 F-C778-1: a
#: finite but absurd timeout is the same "wait forever" in practice)
MAX_TIMEOUT_S = 3600

_PINNED = ("trust_env", "follow_redirects", "proxy", "proxies", "mounts", "transport", "event_hooks", "cert")


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


def _positive(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 < value <= MAX_TIMEOUT_S)


def _checked_base_url(value) -> None:
    """``base_url`` is the caller's declared target; it must still be an http(s) URL with a host, carry no
    userinfo (a credential in the URL is sent as a header and logged), and not name a link-local address
    (the cloud metadata address and its kin; reviewer C-778 F-C778-3). The value is never echoed."""
    try:
        parts = urlsplit(str(value))
        host = parts.hostname
        ok = parts.scheme in ("http", "https") and bool(host) and not parts.username and not parts.password
        if ok:
            try:
                ok = not ipaddress.ip_address(host.split("%", 1)[0]).is_link_local
            except ValueError:
                pass                                     # a name, not an address
    except ValueError:
        ok = False
    if not ok:
        raise ValueError("base_url must be an http or https URL with a host, no userinfo and no link-local address")


def _checked(timeout, kw: dict) -> dict:
    for key in _PINNED:
        if key in kw:
            raise ValueError(f"{key} is fixed by field_core.http and cannot be passed")
    if "verify" in kw:
        v = kw["verify"]
        if not (v is True or (isinstance(v, ssl.SSLContext) and v.verify_mode == ssl.CERT_REQUIRED
                              and v.check_hostname)):
            # a context that does not verify the certificate and the host name is verify=False by another route
            # (reviewer C-778 F-C778-2)
            raise ValueError("verify must be True or an ssl.SSLContext that requires and checks the certificate")
    if "base_url" in kw and kw["base_url"] not in (None, ""):
        _checked_base_url(kw["base_url"])
    import httpx

    if isinstance(timeout, httpx.Timeout):
        parts = (timeout.connect, timeout.read, timeout.write, timeout.pool)
        if not all(_positive(v) for v in parts):
            raise ValueError("timeout parts (connect, read, write, pool) must all be positive numbers "
                             f"of at most {MAX_TIMEOUT_S} seconds")
    elif not _positive(timeout):
        raise ValueError(f"timeout must be a positive number of at most {MAX_TIMEOUT_S} seconds, "
                         "or an httpx.Timeout")
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
