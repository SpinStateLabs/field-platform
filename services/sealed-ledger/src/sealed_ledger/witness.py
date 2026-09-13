"""X4 — cross-estate witnessing, GB10-initiated in both directions.

Direction 1 (live, no cross-estate secret): each tick GETs Fly's OPEN
``/ledger/health`` over https (timeout, redirects never followed) and appends
ONE ``anchor.remote{estate: "fly", length, head_hash, observed_at, observer,
key_fingerprint, signature}`` to the LOCAL ledger through its served route
(``FIELD_LEDGER_URL`` + the local perimeter header). ``signature`` is Ed25519
over the canonical JSON of every other payload field, signed IN THIS PROCESS
with the key at ``FIELD_LEDGER_ANCHOR_KEY`` (mounted read-only into the
witness container). No served route signs anything for anyone.

Direction 2 (needs D5): only when ``FIELD_WITNESS_FLY_SECRET_FILE`` names a
readable, non-empty file, the local head is POSTed the same way, as
``anchor.remote{estate: <local estate>}``, to Fly's ``/ledger/events`` with that
secret as ``x-field-auth``. Unset ⇒ one log line per tick, "direction 2 not
live (D5)".

What an ``anchor.remote{estate: fly}`` proves: what THIS process read from
Fly's open ``/health`` over TLS at ``observed_at``, signed with the on-box
anchor key. Fly did not sign it. A failed read appends nothing (never a fake
anchor); a key that cannot be loaded appends nothing and the loop keeps
running (never a process exit, never an unsigned anchor). The key is loaded
BEFORE Fly is contacted, so a keyless witness (every CI stack) makes no
outbound call at all.

``verify_witness`` checks every anchor of one estate it is GIVEN (``GET /events``
serves only the witnessing ledger's live segments) against a local chain: the
hash at global index ``length - 1`` must equal ``head_hash``; an archived index,
a missing one or a length beyond the local chain is an explicit failure; with a
public key each signature must verify. At least one anchor with length >= 1 must
hold: length-0 anchors alone are "nothing witnessed".
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import serialization

from field_core.authn import HEADER as AUTH_HEADER
from field_core.authn import auth_headers, shared_secret
from field_core.ledger import GENESIS_HASH
from field_core.signing import key_fingerprint, sign_manifest, verify_manifest
from sealed_ledger.api import load_anchor_key
from sealed_ledger.store import NoAnchorKey, Snapshot

ANCHOR_REMOTE = "anchor.remote"
REMOTE_ESTATE = "fly"
FLY_SECRET_FILE_ENV = "FIELD_WITNESS_FLY_SECRET_FILE"
DIRECTION_2_NOT_LIVE = "direction 2 not live (D5)"
HTTP_TIMEOUT_S = 10.0
BODY_LOG_CHARS = 200
PAYLOAD_FIELDS = ("estate", "length", "head_hash", "observed_at", "observer", "key_fingerprint",
                  "signature")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

log = logging.getLogger("sealed_ledger.witness")


class WitnessError(ValueError):
    """A remote answer that cannot be believed (not a head)."""


class DuplicateKey(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKey(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _no_constants(name: str) -> Any:
    raise WitnessError(f"non-standard JSON constant {name}")


def strict_json_loads(text: str | bytes) -> Any:
    """``json.loads`` that refuses a repeated key (a decoy value) and NaN/Infinity."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=_no_constants)


def require_https(url: str) -> str:
    """The remote estate is only ever read over TLS."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(f"--fly-url must be an https:// URL (got {url!r})")
    return url.rstrip("/")


def parse_head(body: bytes) -> tuple[int, str]:
    """``(event_count, head_hash)`` from a ledger ``/health`` body, or WitnessError."""
    try:
        data = strict_json_loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WitnessError(f"not JSON ({type(exc).__name__}: {exc})") from None
    if not isinstance(data, dict):
        raise WitnessError("not a JSON object")
    length, head = data.get("event_count"), data.get("head_hash")
    if type(length) is not int or length < 0:
        raise WitnessError(f"event_count {length!r} is not a non-negative integer")
    if not isinstance(head, str) or not _HEX64.match(head):
        raise WitnessError("head_hash is not 64 lowercase hex")
    return length, head


def signing_view(payload: dict[str, Any]) -> dict[str, Any]:
    """The bytes the signature covers: every payload field except ``signature``."""
    return {k: v for k, v in payload.items() if k != "signature"}


def sign_anchor(fields: dict[str, Any], private_key_pem: str) -> dict[str, Any]:
    body = signing_view(fields)
    return {**body, "signature": sign_manifest(body, private_key_pem)}


def private_key_fingerprint(private_key_pem: str) -> str:
    private = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return key_fingerprint(public_pem)


def build_fly_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The REMOTE client: no local perimeter header (the GB10 secret never goes to
    Fly), a timeout, and redirects never followed."""
    return httpx.Client(timeout=HTTP_TIMEOUT_S, follow_redirects=False, transport=transport)


def build_ledger_client(base_url: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The LOCAL served ledger, with the local perimeter header from the environment."""
    return httpx.Client(base_url=base_url, headers=auth_headers(), timeout=HTTP_TIMEOUT_S,
                        follow_redirects=False, transport=transport)


def observer_record(started_at: str, host: str | None = None) -> dict[str, str]:
    return {"role": "witness", "host": host or socket.gethostname(), "started_at": started_at}


@dataclass
class TickOutcome:
    direction1: str  # appended | no-key | fly-unreadable | ledger-refused
    direction2: str  # not-live | secret-unreadable | no-key | local-unreadable | posted | refused
    anchor: dict[str, Any] | None = None
    remote: dict[str, Any] | None = None


@dataclass
class Witness:
    local_estate: str
    fly_url: str
    fly: httpx.Client
    ledger: httpx.Client
    observer: dict[str, str]
    clock: Callable[[], str] = utc_now
    remote_estate: str = REMOTE_ESTATE
    _secrets: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.fly_url = require_https(self.fly_url)

    # -- logging: every line goes through here, and no secret survives it ------------------

    def _redact(self, text: str) -> str:
        for secret in [shared_secret(), *self._secrets]:
            if secret:
                text = text.replace(secret, "***")
        return text

    def _log(self, level: int, message: str) -> None:
        log.log(level, self._redact(message))

    def _body(self, resp: httpx.Response) -> str:
        """A refusal body for a log line: redacted IN FULL, then truncated, so a secret
        that straddles the cut never leaves its prefix behind."""
        return self._redact(resp.text)[:BODY_LOG_CHARS]

    # -- one tick ----------------------------------------------------------------------------

    def tick(self) -> TickOutcome:
        try:
            pem = load_anchor_key()
            fingerprint = private_key_fingerprint(pem)
        except (NoAnchorKey, ValueError, TypeError) as exc:
            detail = str(exc) if isinstance(exc, NoAnchorKey) else type(exc).__name__
            self._log(logging.ERROR, f"witness tick: no usable anchor key ({detail}); nothing appended, "
                      "nothing sent; the loop keeps running")
            return TickOutcome("no-key", self._direction2(None, None))
        outcome = TickOutcome(*self._direction1(pem, fingerprint))
        outcome.direction2 = self._direction2(pem, fingerprint, outcome)
        return outcome

    def _direction1(self, pem: str, fingerprint: str) -> tuple[str, str, dict | None]:
        url = f"{self.fly_url}/ledger/health"
        try:
            resp = self.fly.get(url)
        except httpx.HTTPError as exc:
            self._log(logging.WARNING, f"direction 1: {self.remote_estate} read failed "
                      f"({type(exc).__name__}: {exc}); nothing appended")
            return "fly-unreadable", "", None
        if resp.status_code != 200:
            self._log(logging.WARNING, f"direction 1: {url} answered {resp.status_code} "
                      "(redirects are never followed); nothing appended")
            return "fly-unreadable", "", None
        try:
            length, head = parse_head(resp.content)
        except WitnessError as exc:
            self._log(logging.WARNING, f"direction 1: {url} is not a ledger head ({exc}); nothing appended")
            return "fly-unreadable", "", None
        payload = sign_anchor({
            "estate": self.remote_estate, "length": length, "head_hash": head,
            "observed_at": self.clock(), "observer": dict(self.observer), "key_fingerprint": fingerprint,
        }, pem)
        try:
            appended = self.ledger.post("events", json={"event_type": ANCHOR_REMOTE, "payload": payload,
                                                        "agent_id": None})
        except httpx.HTTPError as exc:
            self._log(logging.WARNING, f"direction 1: local ledger unreachable ({type(exc).__name__}: {exc}); "
                      "nothing appended")
            return "ledger-refused", "", None
        if appended.status_code != 201:
            self._log(logging.WARNING, f"direction 1: local ledger refused the anchor "
                      f"({appended.status_code}: {self._body(appended)})")
            return "ledger-refused", "", None
        self._log(logging.INFO, f"direction 1: anchor.remote{{estate: {self.remote_estate}, length {length}, "
                  f"head {head[:16]}}} appended to the local ledger")
        return "appended", "", payload

    def _direction2(self, pem: str | None, fingerprint: str | None,
                    outcome: TickOutcome | None = None) -> str:
        path = os.environ.get(FLY_SECRET_FILE_ENV, "").strip()
        if not path:
            self._log(logging.INFO, f"{DIRECTION_2_NOT_LIVE}: {FLY_SECRET_FILE_ENV} is unset")
            return "not-live"
        try:
            secret = Path(path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            self._log(logging.WARNING, f"direction 2 not sent: {FLY_SECRET_FILE_ENV} unreadable "
                      f"({type(exc).__name__})")
            return "secret-unreadable"
        if not secret:
            self._log(logging.WARNING, f"direction 2 not sent: {FLY_SECRET_FILE_ENV} is empty")
            return "secret-unreadable"
        if secret not in self._secrets:
            self._secrets.append(secret)
        if pem is None or fingerprint is None:
            self._log(logging.WARNING, "direction 2 not sent: no usable anchor key")
            return "no-key"
        try:
            local = self.ledger.get("health")
            if local.status_code != 200:
                raise WitnessError(f"answered {local.status_code}")
            length, head = parse_head(local.content)
        except (httpx.HTTPError, WitnessError) as exc:
            self._log(logging.WARNING, f"direction 2 not sent: local ledger head unreadable "
                      f"({type(exc).__name__}: {exc})")
            return "local-unreadable"
        payload = sign_anchor({
            "estate": self.local_estate, "length": length, "head_hash": head,
            "observed_at": self.clock(), "observer": dict(self.observer), "key_fingerprint": fingerprint,
        }, pem)
        url = f"{self.fly_url}/ledger/events"
        try:
            resp = self.fly.post(url, json={"event_type": ANCHOR_REMOTE, "payload": payload, "agent_id": None},
                                 headers={AUTH_HEADER: secret})
        except httpx.HTTPError as exc:
            self._log(logging.WARNING, f"direction 2: POST {url} failed ({type(exc).__name__}: {exc})")
            return "refused"
        if resp.status_code != 201:
            self._log(logging.WARNING, f"direction 2: {url} refused ({resp.status_code}: {self._body(resp)})")
            return "refused"
        if outcome is not None:
            outcome.remote = payload
        self._log(logging.INFO, f"direction 2: anchor.remote{{estate: {self.local_estate}, length {length}, "
                  f"head {head[:16]}}} appended to {self.remote_estate}")
        return "posted"


def run_loop(tick: Callable[[], Any], every: float, stop: threading.Event,
             sleep: Callable[[float], Any] | None = None) -> int:
    """First tick immediately, then one every ``every`` seconds until ``stop``.
    A raising tick is logged by type and the loop continues. Returns ticks run."""
    wait = sleep if sleep is not None else stop.wait
    ticks = 0
    while not stop.is_set():
        ticks += 1
        try:
            tick()
        except Exception as exc:  # noqa: BLE001 — a tick never ends the witness
            log.error("witness tick raised %s; the loop keeps running", type(exc).__name__)
        if stop.is_set():
            break
        wait(every)
    return ticks


# --------------------------------------------------------------------------------------------
# verify-witness
# --------------------------------------------------------------------------------------------


def load_events(raw: bytes) -> list[Any]:
    """A GET /events JSON array, or JSONL (one event per line). Duplicate keys refused."""
    text = raw.decode("utf-8")
    if text.lstrip().startswith("["):
        data = strict_json_loads(text)
        if not isinstance(data, list):
            raise WitnessError("events source is not a JSON array")
        return data
    return [strict_json_loads(line) for line in text.splitlines() if line.strip()]


def fetch_events(url: str, secret: str | None, transport: httpx.BaseTransport | None = None) -> list[Any]:
    """GET ``url?event_type=anchor.remote`` (a ledger's /events route)."""
    if secret and urlsplit(url).scheme != "https":
        raise ValueError("refusing to send a secret to a non-https --events-url")
    headers = {AUTH_HEADER: secret} if secret else {}
    with httpx.Client(timeout=30.0, follow_redirects=False, transport=transport) as client:
        resp = client.get(url, params={"event_type": ANCHOR_REMOTE}, headers=headers)
    if resp.status_code != 200:
        raise WitnessError(f"{url} answered {resp.status_code}")
    return load_events(resp.content)


def select_anchors(events: list[Any], estate: str) -> list[dict[str, Any]]:
    return [
        e for e in events
        if isinstance(e, dict) and e.get("event_type") == ANCHOR_REMOTE
        and isinstance(e.get("payload"), dict) and e["payload"].get("estate") == estate
    ]


def check_anchor(payload: dict[str, Any], snap: Snapshot, local_length: int,
                 public_key_pem: str | None, public_fingerprint: str | None) -> str | None:
    """None if the anchor holds against the local chain, else why not."""
    length, head = payload.get("length"), payload.get("head_hash")
    if type(length) is not int or length < 0:
        return f"malformed: length {length!r} is not a non-negative integer"
    if not isinstance(head, str) or not _HEX64.match(head):
        return "malformed: head_hash is not 64 lowercase hex"
    if public_key_pem is not None:
        signature = payload.get("signature")
        if not isinstance(signature, str) or not signature:
            return "unsigned, but --pubkey was given"
        if not verify_manifest(signing_view(payload), signature, public_key_pem):
            return "signature invalid under --pubkey (a signed field was edited, or another key signed it)"
        if payload.get("key_fingerprint") != public_fingerprint:
            return (f"key_fingerprint {str(payload.get('key_fingerprint'))[:16]}… is not the --pubkey "
                    f"fingerprint {public_fingerprint[:16]}…")
    if length == 0:
        return None if head == GENESIS_HASH else "length 0 but head_hash is not the genesis hash"
    if length > local_length:
        return f"witnessed a future head: length {length} > local length {local_length}"
    index = length - 1
    actual = snap.hash_at(index)
    if actual == "archived":
        entry = snap.archived_entry_for(index) or {}
        return (f"global index {index} is in archived segment {entry.get('n')} (archived_to "
                f"{entry.get('archived_to')}) — NOT checked against the live chain; verify it with "
                "ledger verify --path <archived file>")
    if actual is None:
        return f"global index {index} is missing from the live chain (segment file absent)"
    if actual != head:
        return (f"hash at global index {index} is {actual[:16]}… but the witness saw {head[:16]}… — "
                "history was rewritten, or this is not the witnessed ledger")
    return None


@dataclass
class WitnessVerification:
    ok: bool
    checked: int
    failed: int
    signatures_checked: int
    lines: list[str]


def verify_witness(snap: Snapshot, anchors: list[dict[str, Any]], estate: str,
                   public_key_pem: str | None = None,
                   verified_length: int | None = None) -> WitnessVerification:
    """``verified_length``: the length the caller's chain verification covered. An
    anchor is never checked against events appended after that verification."""
    fingerprint = key_fingerprint(public_key_pem) if public_key_pem is not None else None
    local_length = snap.global_length if verified_length is None else min(snap.global_length, verified_length)
    lines: list[str] = []
    failed = signatures = compared = 0
    first_failure = None
    for k, event in enumerate(anchors):
        payload = event["payload"]
        problem = check_anchor(payload, snap, local_length, public_key_pem, fingerprint)
        name = (f"anchor {k} (event {str(event.get('hash'))[:12]}…, ts {event.get('ts')}, "
                f"observed_at {payload.get('observed_at')})")
        if problem is None:
            if public_key_pem is not None:
                signatures += 1
            if payload["length"] >= 1:  # a length-0 anchor compares nothing: it holds against ANY chain
                compared += 1
            lines.append(f"HOLDS — {name}: length {payload['length']} head {payload['head_hash'][:16]}…"
                         + ("; signature verified" if public_key_pem is not None else ""))
        else:
            failed += 1
            first_failure = first_failure or f"{name}: {problem}"
            lines.append(f"FAILS — {name}: {problem}")
    checked = len(anchors)
    if checked == 0:
        lines.append(f"WITNESS FAILED — nothing witnessed: 0 anchor.remote events with payload.estate "
                     f"== {estate!r}")
        return WitnessVerification(False, 0, 0, 0, lines)
    if failed:
        lines.append(f"WITNESS FAILED — {failed} of {checked} anchor.remote{{estate: {estate}}} do not hold "
                     f"(first: {first_failure})")
    elif compared == 0:
        lines.append(f"WITNESS FAILED — nothing witnessed: {checked} anchor.remote{{estate: {estate}}} hold, but "
                     "every one has length 0 (the genesis head), which compares nothing against the local chain")
        return WitnessVerification(False, checked, 0, signatures, lines)
    else:
        lines.append(f"OK — {checked} of {checked} anchor.remote{{estate: {estate}}} hold against the local "
                     f"chain (length {local_length}); {signatures} signature(s) verified"
                     + ("" if public_key_pem is not None else " — pass --pubkey to check them"))
    return WitnessVerification(failed == 0, checked, failed, signatures, lines)
