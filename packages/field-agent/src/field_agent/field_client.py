"""Stdlib-only, fail-closed FIELD client for an agent that cannot use the facade.

Lifted from ``SpinStateLabs/cost-optimizer`` ``src/cost_optimizer/field_client.py``
(with its ``safe_http.py`` helpers) at commit 817aace, decision P28(c), so that the
next FIELD-guarded gateway (pattern D of the Claude Platform deploy guide: an
MCP gateway that calls ``guard()`` before every tool it serves) does not
re-implement the five rules. Behaviour is unchanged from the source; the tests
in ``tests/test_field_client.py`` are the source's tests plus contract tests
against this repo's real sentinel, spend-governor and kill-switch apps.

``FieldAgent`` (``field_agent.agent``) remains the SDK's main path: httpx,
per-service URLs, the sentinel's own ``Governor`` classes. ``FieldClient`` is the
smaller alternative for a process that talks to one path-routed estate URL and
wants nothing but the standard library inside this module. It ports the five
rules every non-SDK client must implement
(``plugins/field-agent/skills/field-agent/rest-api.md``):

1. unreachable sentinel, or any non-200 on /check  -> BLOCK
2. unreachable kill-switch, or non-200 heartbeat    -> killed
3. failed usage POST (incl. the no-cap 404)         -> unmetered: stop, never continue silently
4. killed=true for an unknown agent id              -> halt
5. ESCALATE is never retried until ALLOW            -> a human has the item

Paths assume the estate's path-routed proxy (/sentinel, /governor, /killswitch), as on
the GB10 and Fly estates; override with ``prefixes`` if an estate differs.

Hardening: redirects are never followed (a 3xx is a failure); any transport or parse
error is a failure; an action that was escalated once is not re-checked by the same
client (rule 5 across calls); the shared secret is only sent over https, or plain http
to a loopback or private-network address (the GB10 LAN estate).

What this module does NOT do: it sends no operator identity headers, holds no
token beyond the opaque ``token_id`` it is given, never retries, never sleeps,
and makes no request other than the three it documents (``POST /check``,
``GET /heartbeat/{agent}``, ``POST /usage``), each only when the caller asks.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

__all__ = [
    "DECISIONS",
    "DEFAULT_PREFIXES",
    "NO_REDIRECT",
    "Blocked",
    "Escalated",
    "FieldClient",
    "FieldStop",
    "Halted",
    "Unmetered",
    "Verdict",
    "status_of",
]

DECISIONS = {"ALLOW", "BLOCK", "ESCALATE"}
DEFAULT_PREFIXES = {"sentinel": "/sentinel", "governor": "/governor", "killswitch": "/killswitch"}


# -- an opener that never follows redirects (source: cost_optimizer/safe_http.py) --
#
# urllib's default opener follows 3xx and re-sends request headers, so a redirect could
# carry the FIELD secret to another endpoint or host, or turn a refused check into an
# apparent ALLOW. FieldClient uses NO_REDIRECT by default: a 3xx surfaces as an
# HTTPError and is handled as a failure (fail closed).

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


# An empty ProxyHandler replaces urllib's default one, which reads http_proxy / HTTPS_PROXY /
# ALL_PROXY from the environment AT IMPORT: x-field-auth (the shared secret) must go to the
# FIELD estate only, never to a proxy configured for the process (reviewer C-41, proven).
NO_REDIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open

#: A reply larger than this is refused, not read into memory (reviewer C-41 finding 2).
MAX_RESPONSE_BYTES = 64 * 1024


def status_of(resp) -> int | None:
    code = getattr(resp, "status", None)
    if code is None and hasattr(resp, "getcode"):
        code = resp.getcode()
    return code if isinstance(code, int) else None


# -- verdicts and stops ---------------------------------------------------------

@dataclass(frozen=True)
class Verdict:
    decision: str
    clause_id: str | None = None
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"


class FieldStop(Exception):
    def __init__(self, message: str, verdict: Verdict | None = None):
        super().__init__(message)
        self.verdict = verdict


class Blocked(FieldStop):
    pass


class Escalated(FieldStop):
    """A human now holds the item. Do not retry (rule 5)."""


class Halted(FieldStop):
    pass


class Unmetered(FieldStop):
    pass


class _Unreachable(Exception):
    pass


class FieldClient:
    def __init__(self, base_url: str, agent_id: str, token_id: str, shared_secret: str | None = None,
                 timeout: float = 10.0, opener=NO_REDIRECT, prefixes: dict | None = None):
        if not (base_url and agent_id and token_id):
            raise ValueError("base_url, agent_id and token_id are required")
        u = urllib.parse.urlparse(base_url)
        if shared_secret and u.scheme != "https" and not _private_host(u.hostname):
            raise ValueError("the shared secret is only sent over https (or http to a loopback/private address)")
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self._token_id = token_id
        self._secret = shared_secret
        self.timeout = timeout
        self._open = opener
        self.prefixes = {**DEFAULT_PREFIXES, **(prefixes or {})}
        self._escalated: set[str] = set()

    def __repr__(self) -> str:  # never show the token or the secret
        return f"FieldClient(base_url={self.base_url!r}, agent_id={self.agent_id!r})"

    def _call(self, method: str, service: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        headers = {"content-type": "application/json"}
        if self._secret:
            headers["x-field-auth"] = self._secret
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base_url}{self.prefixes[service]}{path}", data=data, method=method,
                                     headers=headers)
        try:
            with self._open(req, timeout=self.timeout) as resp:
                status, raw = status_of(resp), resp.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raw = b""                      # refused: no body, so every rule fails closed
        except urllib.error.HTTPError as e:  # includes every 3xx: redirects are never followed
            e.close()
            return e.code, None
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError):
            raise _Unreachable(service) from None
        try:
            parsed = json.loads(raw) if raw else None
        except (ValueError, RecursionError):
            parsed = None
        return (status if status is not None else -1), parsed if isinstance(parsed, dict) else None

    def check(self, action: str) -> Verdict:
        """Rule 1: anything but a well-formed 200 verdict is BLOCK."""
        try:
            status, body = self._call("POST", "sentinel", "/check",
                                      {"agent_id": self.agent_id, "action": action, "token_id": self._token_id})
        except _Unreachable:
            return Verdict("BLOCK", reason="sentinel unreachable")
        if status != 200:
            return Verdict("BLOCK", reason=f"sentinel HTTP {status}")
        decision = (body or {}).get("decision")
        if not isinstance(decision, str) or decision not in DECISIONS:
            return Verdict("BLOCK", reason="unrecognised verdict")
        clause = (body or {}).get("clause_id")
        return Verdict(decision, clause[:80] if isinstance(clause, str) and clause.isprintable() else None)

    def killed(self) -> bool:
        """Rules 2 and 4: only an explicit killed=false from a 200 means alive."""
        try:
            status, body = self._call("GET", "killswitch", f"/heartbeat/{urllib.parse.quote(self.agent_id, safe='')}")
        except _Unreachable:
            return True
        return not (status == 200 and body is not None and body.get("killed") is False)

    def report_usage(self, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
                     note: str = "") -> None:
        """Rule 3: raise Unmetered unless the governor accepted the record."""
        counts = (input_tokens, output_tokens, cache_read_tokens)
        if not (isinstance(model, str) and model) or any(isinstance(c, bool) or not isinstance(c, int) or c < 0 for c in counts):
            raise Unmetered("invalid usage record: spend is unmetered")
        note = note if isinstance(note, str) else ""
        try:
            status, _ = self._call("POST", "governor", "/usage", {
                "agent_id": self.agent_id, "model": model, "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens), "cache_read_tokens": int(cache_read_tokens), "note": note[:200]})
        except _Unreachable:
            raise Unmetered("spend-governor unreachable: spend is unmetered") from None
        if status not in (200, 201):
            raise Unmetered(f"spend-governor HTTP {status}: spend is unmetered (404 = no cap)")

    def guard(self, action: str) -> Verdict:
        """Call before every write. Returns on ALLOW; raises otherwise. Never retries."""
        if self.killed():
            raise Halted("kill-switch says stop (or is unreachable)")
        if action in self._escalated:
            raise Escalated(f"already escalated: {action!r} waits for Don (not re-checked)")
        v = self.check(action)
        if v.decision == "ALLOW":
            return v
        if v.decision == "ESCALATE":
            self._escalated.add(action)
            raise Escalated(f"escalated: {action!r} waits for Don", v)
        raise Blocked(f"blocked: {action!r} ({v.clause_id or v.reason})", v)


_INTERNAL_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7"))


def _private_host(host: str | None) -> bool:
    """Copy of ``field_core.hosts.is_internal_host(host, allow_names=False)``: this client is standard-library
    only (C-489; tools/tests/test_internal_host_c489.py holds the copy equal to the one predicate)."""
    host = (host or "").lower()
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False        # not a canonical address (short, hex, octal, decimal forms are refused: C-880 C1)
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip.version == n.version and ip in n for n in _INTERNAL_NETWORKS)
