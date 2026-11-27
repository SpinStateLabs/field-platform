"""A wall-clock deadline on every socket operation of one outbound request.

httpx's timeout is per phase and restarts on every chunk received, so an endpoint that keeps sending a byte inside it
holds the connection for as long as it likes. Here each connect, TLS handshake, read and write is given at most the time
left until the deadline, and fails once it has passed: the request ends and its connection is closed. Not bounded by
this: the name lookup, and a connect that tries several addresses (each gets what was left when it began)."""
from __future__ import annotations

import time
from typing import Any

import httpcore


def _left(deadline: float, timeout: float | None, error: type[Exception]) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise error("the request's wall-clock deadline has passed")
    return left if timeout is None else min(timeout, left)


class DeadlineStream(httpcore.NetworkStream):
    def __init__(self, inner: httpcore.NetworkStream, deadline: float):
        self._inner, self._deadline = inner, deadline

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._inner.read(max_bytes, _left(self._deadline, timeout, httpcore.ReadTimeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._inner.write(buffer, _left(self._deadline, timeout, httpcore.WriteTimeout))

    def close(self) -> None:
        self._inner.close()

    def start_tls(self, ssl_context: Any, server_hostname: str | None = None,
                  timeout: float | None = None) -> httpcore.NetworkStream:
        inner = self._inner.start_tls(ssl_context, server_hostname,
                                      _left(self._deadline, timeout, httpcore.ConnectTimeout))
        return DeadlineStream(inner, self._deadline)

    def get_extra_info(self, info: str) -> Any:
        return self._inner.get_extra_info(info)


class DeadlineBackend(httpcore.NetworkBackend):
    def __init__(self, inner: httpcore.NetworkBackend, deadline: float):
        self._inner, self._deadline = inner, deadline

    def connect_tcp(self, host: str, port: int, timeout: float | None = None, local_address: str | None = None,
                    socket_options: Any = None) -> httpcore.NetworkStream:
        stream = self._inner.connect_tcp(host, port, timeout=_left(self._deadline, timeout, httpcore.ConnectTimeout),
                                         local_address=local_address, socket_options=socket_options)
        return DeadlineStream(stream, self._deadline)

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


def bound_client(client: Any, deadline: float) -> bool:
    """Put the deadline under ``client``'s own connection pool. False (and nothing changed) when the pool does not have
    the shape this relies on, which a test pins: a changed HTTP library must not stop a halt signal."""
    pool = getattr(getattr(client, "_transport", None), "_pool", None)
    inner = getattr(pool, "_network_backend", None)
    if inner is None:
        return False
    pool._network_backend = DeadlineBackend(inner, deadline)
    return True
