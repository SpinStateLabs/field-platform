"""Fakes for the key rotation slice R4a tests (not collected: no test_ prefix).

``FakeEstate`` models the eight operator-block services the way R1/R2 make
them behave, with the REAL parser: every service re-reads the operators file
on each call (F5), parses it with ``operator_auth.parse_registry_doc`` and
applies the REAL retired-hash memory (``operator_auth._apply_retired_memory``)
under its own key, so a file published at or below a generation that removed
a hash refuses that hash on that service exactly as a verifier does (design
2.4; R1 review F2, F6). ``verify_hash`` answers as R2's ``/operator/verify-hash``
(matched current / next / none, matchable_now by ``operator_auth._key_matches``,
retired). A daemon service reads its key file on every call (F9) and shows its
16-hex fingerprint. The ledger validates every event against the frozen R2
schema. Every key here is a fake test value made in a temp directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from field_core import operator_auth as oa
from field_core import rotation as rot
from field_core import rotation_events as ev

T0 = oa.parse_time("2026-11-20T03:00:00Z")
BUILD = "r4a-test-build"
ESTATE = "gb10"
ROTATOR_ID = "svc-rotator-gb10"
DAEMONS = {"svc-killswitch": "kill-switch", "svc-registry": "agent-registry"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Crash(BaseException):
    """A simulated process death at a hook point (not an Exception, so the
    rotator's own error handling never sees it)."""


class FakeService:
    def __init__(self, name: str, estate: "FakeEstate"):
        self.name = name
        self.e = estate
        self.frozen: bytes | None = None       # serve a stale view
        self.daemon: tuple[str, Path] | None = None
        self.stuck_fp: str | None = None        # a daemon that never re-reads its key
        self.answer_hook: Callable[[str, str, dict], dict] | None = None
        self.force_error: str | None = None     # report last_registry_error

    def _bytes(self) -> bytes:
        return self.frozen if self.frozen is not None else self.e.ops.read_bytes()

    def _parse(self):
        data = self._bytes()
        raw = json.loads(data.decode("utf-8-sig"))
        doc = oa.parse_registry_doc(raw, require_active=True)
        rows = oa._apply_retired_memory(f"{self.e.ops}#{self.name}", doc)
        return data, doc, rows

    def identity_fp(self) -> str | None:
        if self.daemon is None:
            return None
        if self.stuck_fp is not None:
            return self.stuck_fp
        key = oa._key_from_file(str(self.daemon[1]))
        return oa.key_sha256(key)[:16] if key else None

    def rotation_state(self) -> dict[str, Any]:
        out = {"operator_mode": self.e.operator_mode,
               "registry_sha256_prefix": None, "last_registry_error": None,
               "registry_format": None, "registry_generation": None,
               "identity_id": self.daemon[0] if self.daemon else None,
               "identity_key_fp": self.identity_fp()}
        try:
            data, doc, _rows = self._parse()
        except (oa.RegistryUnavailable, ValueError) as exc:
            out["registry_sha256_prefix"] = hashlib.sha256(self._bytes()).hexdigest()[:16]
            out["last_registry_error"] = str(exc)
            return out
        out.update({"registry_sha256_prefix": hashlib.sha256(data).hexdigest()[:16],
                    "registry_format": doc.format, "registry_generation": doc.generation})
        if self.force_error is not None:
            out["last_registry_error"] = self.force_error
        return out

    def verify_hash(self, operator_id: str, key_sha: str) -> dict[str, Any]:
        _data, doc, rows = self._parse()
        matched, matchable, retired = "none", False, False
        for r in rows:
            nk = r.get("next_key")
            cur_eq = r["key_sha256"] == key_sha
            next_eq = nk is not None and nk["key_sha256"] == key_sha
            if r["operator_id"] == operator_id and (cur_eq or next_eq):
                matched = "current" if cur_eq else "next"
                matchable = r["status"] == "active" and oa._key_matches(key_sha, r, self.e.t)
                retired = key_sha in r.get("refused_hashes", ())
        answer = {"operator_id": operator_id, "matched": matched, "matchable_now": matchable,
                  "retired": retired, "registry_generation": doc.generation}
        if self.answer_hook is not None:
            answer = self.answer_hook(operator_id, key_sha, answer)
        return answer


class FakeEstate:
    def __init__(self, ops: Path):
        self.ops = Path(ops)
        self.t = float(T0)
        self.synced: bool | None = True
        self.builds: dict[str, str] = {}
        self.services = {name: FakeService(name, self) for name in rot.SERVICES}
        self.events: list[tuple[str, dict]] = []
        self.fail_append: set[str] = set()
        self.refusal_log: list[tuple[str, float]] = []
        self.verify_calls: list[tuple[str, str, str]] = []
        self.sleeps = 0.0
        #: the guards' operator mode as rotation-state shows it
        self.operator_mode = oa.LOG_ONLY
        #: the key file the rotator's ledger client reads (the self identity);
        #: an append returns the stored event with operator_key_fp set when
        #: that key authenticates against the ledger's current parse, as R1's
        #: OperatorAuth.payload_fields does
        self.self_key: tuple[str, Path] | None = None

    # Estate protocol
    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds
        self.sleeps += seconds

    def clock_synced(self):
        return self.synced

    def build_sha(self, service: str):
        return self.builds.get(service, BUILD)

    def rotation_state(self, service: str):
        return self.services[service].rotation_state()

    def verify_hash(self, service: str, operator_id: str, key_sha256: str):
        self.verify_calls.append((service, operator_id, key_sha256))
        return self.services[service].verify_hash(operator_id, key_sha256)

    def append(self, event_type: str, payload: dict):
        if event_type in self.fail_append:
            raise rot.EstateError("ledger down")
        ev.validate(event_type, payload)
        self.events.append((event_type, dict(payload)))
        stored = dict(payload)
        fp = self._authenticated_fp()
        if fp is not None:
            stored["operator_key_fp"] = fp
        return {"event_type": event_type, "payload": stored}

    def _authenticated_fp(self) -> str | None:
        if self.self_key is None or self.operator_mode == oa.OFF:
            return None
        oid, path = self.self_key
        key = oa._key_from_file(str(path))
        if not key:
            return None
        h = oa.key_sha256(key)
        try:
            ans = self.services["sealed-ledger"].verify_hash(oid, h)
        except (oa.RegistryUnavailable, ValueError):
            return None
        if ans["matched"] in ("current", "next") and ans["matchable_now"] and not ans["retired"]:
            return h[:8]
        return None

    def refusals(self, operator_id: str, since: float) -> int:
        return sum(1 for op, t in self.refusal_log if op == operator_id and t >= since)

    # helpers
    def types(self) -> list[str]:
        return [t for t, _ in self.events]

    def of(self, event_type: str) -> list[dict]:
        return [p for t, p in self.events if t == event_type]


class Bed:
    """A temp estate: operators file, key files, state dir, settings, fakes."""

    def __init__(self, root: Path, *, fmt: int = 2, extra_rows: list[dict] | None = None):
        self.root = Path(root)
        self.opsdir = self.root / "operators"
        self.keys = self.root / "keys"
        self.state = self.root / "rotation"
        for d in (self.opsdir, self.keys, self.state):
            d.mkdir(parents=True, exist_ok=True)
        self.ops = self.opsdir / "operators.json"
        self.key_values: dict[str, str] = {}
        ids = [("svc-killswitch", "daemon"), ("svc-registry", "daemon"),
               (ROTATOR_ID, "self"), ("job-provision-gb10", "job")]
        self.identities = []
        for oid, kind in ids:
            kdir = self.keys / oid
            kdir.mkdir()
            kp = kdir / f"{oid}.key"
            value = f"fok_test-{oid}-initial-not-a-real-key"
            kp.write_text(value + "\n", encoding="utf-8")
            self.key_values[oid] = value
            self.identities.append(rot.Identity(operator_id=oid, key_path=str(kp), kind=kind,
                                                service=DAEMONS.get(oid)))
        self.key_values["don"] = "fok_test-don-not-a-real-key"
        self.key_values["don-breakglass"] = "fok_test-breakglass-not-a-real-key"
        created = oa.format_time(T0 - 40 * rot.DAY)
        rows = []
        for oid, kind in ids:
            scopes = {"svc-killswitch": ["kill", "revive", "bypass_operator_list"],
                      "svc-registry": ["registry_edit"],
                      ROTATOR_ID: ["ledger_attribute"],
                      "job-provision-gb10": ["mint"]}[oid]
            row = {"operator_id": oid, "status": "active", "scopes": scopes, "names": [],
                   "event_prefixes": ["keyrotation."] if oid == ROTATOR_ID else [],
                   "created_at": created, "rotation": "auto",
                   "key_sha256": sha(self.key_values[oid]), "key_created_at": created,
                   "key_not_after": oa.format_time(T0 + 35 * rot.DAY)}
            rows.append(row)
        rows.append({"operator_id": "don", "status": "active", "scopes": ["*"],
                     "names": ["Don Hagell"], "event_prefixes": [], "created_at": created,
                     "rotation": "remote", "key_sha256": sha(self.key_values["don"]),
                     "key_not_after": oa.format_time(T0 + 100 * rot.DAY)})
        rows.append({"operator_id": "don-breakglass", "status": "active",
                     "scopes": ["kill", "revive"], "names": [], "event_prefixes": [],
                     "created_at": created, "rotation": "sealed",
                     "key_sha256": sha(self.key_values["don-breakglass"])})
        rows += extra_rows or []
        self.doc = {"format": 2, "generation": 10, "issued_at": oa.format_time(T0 - 3600),
                    "issued_by": ROTATOR_ID, "operators": rows}
        self.ops.write_bytes(rot.encode_doc(self.doc))
        self.estate = FakeEstate(self.ops)
        self.estate.services["kill-switch"].daemon = (
            "svc-killswitch", Path(self.identity("svc-killswitch").key_path))
        self.estate.services["agent-registry"].daemon = (
            "svc-registry", Path(self.identity("svc-registry").key_path))
        self.estate.self_key = (ROTATOR_ID, Path(self.identity(ROTATOR_ID).key_path))

    def identity(self, oid: str) -> rot.Identity:
        return next(i for i in self.identities if i.operator_id == oid)

    def settings(self, **kw) -> rot.Settings:
        base = dict(estate=ESTATE, operators_file=str(self.ops), state_dir=str(self.state),
                    issued_by=ROTATOR_ID, identities=tuple(self.identities), build_sha=BUILD,
                    observer_tick_s=60, publish_wait_s=60, poll_s=5,
                    max_wait_s=rot.MIN_SOAK_S + 300)
        base.update(kw)
        return rot.Settings(**base)

    def rotator(self, hook=None, **kw) -> rot.Rotator:
        return rot.Rotator(self.settings(**kw), self.estate, hook=hook)

    def live(self) -> dict:
        return json.loads(self.ops.read_text(encoding="utf-8"))

    def row(self, oid: str) -> dict:
        return next(r for r in self.live()["operators"] if r["operator_id"] == oid)

    def key_sha(self, oid: str) -> str | None:
        return rot.key_file_sha(Path(self.identity(oid).key_path))
