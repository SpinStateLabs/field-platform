#!/usr/bin/env python3
"""operator_rotate - the FIELD operator key rotator (key rotation slice R4a).

    operator_rotate.py --config rotator.json --once
    operator_rotate.py --config rotator.json --dry-run
    operator_rotate.py --config rotator.json --now <operator_id> --reason incident

Plain code, no model, run from the estate image (design 4.5): the core is
``field_core.rotation``; this file adds the HTTP estate (the eight services'
``/operator/rotation-state`` and ``/operator/verify-hash``, their open
``/health`` for ``build_sha``, ledger appends and refusal reads) and the
command line. One run rotates at most one identity, or resumes the one in
flight, and prints ONE line of JSON: ids, phases, 16-hex fingerprints and
generations only. A key is generated on this host, written 0600 next to the
key file it replaces, and never printed, logged or sent anywhere; probes send
only key HASHES.

* ``--once``: preflight, lock, precheck, then rotate the most overdue
  identity (or resume the in-flight one; or migrate a format 1 operators file
  to format 2, alone in its run).
* ``--dry-run``: the same checks; says what ``--once`` would do; writes
  nothing (no file, no journal, no status, no ledger event).
* ``--now ID --reason incident``: rotate ID now (design 4.2), shortening the
  compromised current key's expiry to PUBLISH + soak + 1 h (design 2.4).

Exit codes: 0 done / in progress / nothing due; 1 failed (the event and the
status say which phase, and whether the file was reverted); 2 usage or
config error; 3 the estate lock is held (nothing written); 4 skipped (freeze,
precheck, foreign edit, clock; nothing written).

Config (JSON; paths on the host or in the container; never a secret)::

    {"estate": "gb10",
     "operators_file": "/estate/operators/operators.json",
     "state_dir": "/estate/rotation",
     "rotator_id": "svc-rotator-gb10",
     "ledger_url": "http://sealed-ledger:8002",
     "services": {"sealed-ledger": "http://sealed-ledger:8002", ... all eight ...},
     "identities": [{"operator_id": "svc-killswitch", "kind": "daemon",
                     "service": "kill-switch",
                     "key_file": "/estate/keys/svc-killswitch/svc-killswitch.key"}, ...],
     "observer_tick_s": 60,
     "unmanaged": {"rotation": "remote", "not_after": "2027-02-25T00:00:00Z"}}

The perimeter secret is read per call from ``FIELD_SHARED_SECRET``; the
rotator's own ledger identity from ``FIELD_OPERATOR`` /
``FIELD_OPERATOR_KEY_FILE`` (per request, so its own rotation needs no
restart). Probes carry only ``x-field-auth``, never an operator key.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "field-core" / "src"))
from field_core import authn, buildinfo, operator_health  # noqa: E402
from field_core import operator_auth as oa  # noqa: E402
from field_core import rotation as rot  # noqa: E402
from field_core import rotation_events as ev  # noqa: E402

TIMEOUT_S = 5.0
REFUSAL_TYPES = ("operator.unauthenticated", "operator.refused")
REFUSAL_LIMIT = 10_000


class ConfigError(Exception):
    pass


class HttpEstate:
    """The estate over HTTP. ``client``: an httpx-compatible client (tests
    pass one with a mock transport); ``ledger``: a ``LedgerClient`` for
    appends (built per estate; it adds the rotator's operator headers per
    request)."""

    def __init__(self, services: dict[str, str], ledger_url: str, *, client: Any = None,
                 ledger: Any = None):
        if client is None:
            import httpx

            client = httpx.Client(timeout=TIMEOUT_S, trust_env=False)
        if ledger is None:
            from field_core.clients import LedgerClient

            ledger = LedgerClient(base_url=ledger_url)
        self._c = client
        self._ledger = ledger
        self._services = {k: v.rstrip("/") for k, v in services.items()}
        self._ledger_url = ledger_url.rstrip("/")

    @staticmethod
    def _headers() -> dict[str, str]:
        secret = authn.shared_secret()
        return {authn.HEADER: secret} if secret else {}

    def _get(self, url: str, **params: Any) -> Any:
        try:
            r = self._c.get(url, headers=self._headers(), params=params or None)
        except Exception as exc:
            raise rot.EstateError(type(exc).__name__) from None
        if r.status_code != 200:
            raise rot.EstateError(f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise rot.EstateError("not JSON") from None

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))

    def clock_synced(self) -> bool | None:
        return operator_health.clock_synced()

    def build_sha(self, service: str) -> str | None:
        body = self._get(f"{self._services[service]}/health")
        return body.get("build_sha") if isinstance(body, dict) else None

    def rotation_state(self, service: str) -> dict[str, Any]:
        body = self._get(f"{self._services[service]}{operator_health.ROTATION_STATE_PATH}")
        if not isinstance(body, dict):
            raise rot.EstateError("not an object")
        return body

    def verify_hash(self, service: str, operator_id: str, key_sha256: str) -> dict[str, Any]:
        url = f"{self._services[service]}{operator_health.VERIFY_HASH_PATH}"
        try:
            r = self._c.post(url, headers=self._headers(),
                             json={"operator_id": operator_id, "key_sha256": key_sha256})
        except Exception as exc:
            raise rot.EstateError(type(exc).__name__) from None
        if r.status_code != 200:
            raise rot.EstateError(f"HTTP {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            raise rot.EstateError("not JSON") from None
        if not isinstance(body, dict):
            raise rot.EstateError("not an object")
        return body

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self._ledger.append(event_type, payload)
        except Exception as exc:
            raise rot.EstateError(type(exc).__name__) from None

    def refusals(self, operator_id: str, since: float) -> int:
        n = 0
        for event_type in REFUSAL_TYPES:
            rows = self._get(f"{self._ledger_url}/events", event_type=event_type,
                             since=oa.format_time(int(since)), limit=REFUSAL_LIMIT)
            for row in rows if isinstance(rows, list) else []:
                p = row.get("payload") if isinstance(row, dict) else None
                if isinstance(p, dict) and operator_id in (p.get("claimed_id"),
                                                           p.get("operator_claimed")):
                    n += 1
        return n


def load_config(path: Path) -> tuple[rot.Settings, dict[str, str], str]:
    """(settings, service URLs, ledger URL). Every problem is ConfigError."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"config unreadable ({type(exc).__name__})") from None
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")
    known = {"estate", "operators_file", "state_dir", "rotator_id", "ledger_url", "services",
             "identities", "observer_tick_s", "unmanaged", "publish_wait_s", "max_wait_s"}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown config field(s): {sorted(unknown)}")
    services = raw.get("services")
    if not isinstance(services, dict) or set(services) != set(ev.SERVICES) or \
            not all(isinstance(v, str) and v for v in services.values()):
        raise ConfigError("services must map each of the eight operator-block services to a URL")
    identities = []
    for item in raw.get("identities") or []:
        if not isinstance(item, dict) or set(item) - {"operator_id", "kind", "service",
                                                      "key_file", "soak_s"}:
            raise ConfigError("an identity is {operator_id, kind, service, key_file[, soak_s]}")
        try:
            identities.append(rot.Identity(
                operator_id=item.get("operator_id"), key_path=str(item.get("key_file") or ""),
                kind=item.get("kind", "daemon"), service=item.get("service"),
                soak_s=int(item.get("soak_s", rot.MIN_SOAK_S))))
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"identity: {exc}") from None
        if not identities[-1].key_path:
            raise ConfigError("an identity needs key_file")
    unmanaged = raw.get("unmanaged") or {}
    if not isinstance(unmanaged, dict) or set(unmanaged) - {"rotation", "not_after"}:
        raise ConfigError("unmanaged is {rotation, not_after}")
    not_after = None
    if "not_after" in unmanaged:
        not_after = oa.parse_time(unmanaged["not_after"])
        if not_after is None:
            raise ConfigError("unmanaged.not_after must be YYYY-MM-DDTHH:MM:SSZ")
    ledger_url = raw.get("ledger_url")
    if not isinstance(ledger_url, str) or not ledger_url:
        raise ConfigError("ledger_url is required")
    for name in ("estate", "operators_file", "state_dir", "rotator_id"):
        if not isinstance(raw.get(name), str) or not raw.get(name):
            raise ConfigError(f"{name} is required")
    try:
        settings = rot.Settings(
            estate=raw["estate"], operators_file=raw["operators_file"],
            state_dir=raw["state_dir"], issued_by=raw["rotator_id"],
            identities=tuple(identities), build_sha=buildinfo.build_sha(),
            observer_tick_s=int(raw.get("observer_tick_s", 60)),
            publish_wait_s=raw.get("publish_wait_s"),
            max_wait_s=int(raw.get("max_wait_s", rot.MIN_SOAK_S + 300)),
            unmanaged_rotation=unmanaged.get("rotation", "remote"),
            unmanaged_not_after=not_after)
    except (ValueError, TypeError) as exc:
        raise ConfigError(str(exc)) from None
    return settings, dict(services), ledger_url


def main(argv: list[str] | None = None, *, estate: Any = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--now", metavar="OPERATOR_ID")
    ap.add_argument("--reason", choices=["incident"])
    a = ap.parse_args(argv)
    if (a.now is None) != (a.reason is None):
        print(json.dumps({"result": "usage", "detail": "--now and --reason incident go together"}))
        return rot.EXIT_USAGE
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="operator_rotate: %(levelname)s %(message)s")
    try:
        settings, services, ledger_url = load_config(Path(a.config))
    except ConfigError as exc:
        print(json.dumps({"result": "usage", "detail": str(exc)}))
        return rot.EXIT_USAGE
    if estate is None:
        estate = HttpEstate(services, ledger_url)
    rotator = rot.Rotator(settings, estate)
    code, summary = rotator.run_once(now_id=a.now, reason=a.reason or "schedule",
                                     dry_run=a.dry_run)
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
