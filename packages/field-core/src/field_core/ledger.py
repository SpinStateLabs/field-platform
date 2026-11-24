"""Ledger event model and sha-256 hash-chain primitives.

ENFORCED in code: every event's ``hash`` is sha-256 over the canonical JSON
of the event minus its own hash, and carries ``prev_hash`` linking it to the
previous event (genesis links to 64 zero chars unless ``verify_chain`` is
given another ``genesis``). ``verify_chain`` walks the chain and reports the
first break. ``ChainVerification`` carries four extra keys only for a
segmented (rotated) ledger; the global index offset lives in the ledger
store, not here.

DECLARED only: durability of the underlying store. A hash chain proves
tampering happened; it cannot prevent deletion of the whole file. WORM
storage is the deployment's responsibility.

Per-event signatures (v1.2 F2, additive): an event MAY carry ``signature``
(base64 of the raw 64-byte Ed25519 signature over ``event_signing_bytes``:
the canonical record INCLUDING ``hash`` and EXCLUDING ``signature`` — hash
first, sign second) and MAY carry ``signing_failed: true`` (stamped by the
ledger, INSIDE the hash, on a stop-type event it accepted unsigned because no
key was loaded). Both are None by default and OMITTED from every
serialisation when None, so an unsigned event's JSON line is byte-identical
to a pre-F2 line and every pre-F2 hash is unchanged. The Ed25519 helpers
live in ``field_core.signing`` (``sign_event``, ``verify_event_signature``).

Caller signatures (v1.2 F2b, additive, GB10): an event MAY carry
``caller_id``, ``caller_ts`` and ``caller_signature`` (the CALLER's Ed25519
signature over ``field_core.signing.caller_signing_bytes`` — the canonical
bytes of ``event_type``, ``agent_id``, ``payload``, ``caller_id``,
``caller_ts``; verified by the ledger against ``<caller_id>.pub.pem`` in its
keyring before the append) and MAY carry ``caller_unsigned: true`` (stamped
by the ledger on a stop-type event it accepted without caller fields under
FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1). All four are INSIDE the hash and
under the ledger's own F2 ``signature`` (hash first, ledger-sign second),
None by default and OMITTED from every serialisation when None — the same
additive-compat rule as F2.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_serializer

GENESIS_HASH = "0" * 64

#: F2b keys, INSIDE the hash, left out of a serialised event (and of the
#: hashed record) when None.
_CALLER_KEYS = ("caller_id", "caller_ts", "caller_signature", "caller_unsigned")
#: Optional keys that are hashed when set and omitted when None: a dict may
#: spell the omission as None and must hash like the omission.
_HASHED_OPTIONAL_KEYS = ("signing_failed", *_CALLER_KEYS)
#: F2/F2b keys left OUT of a serialised event when None (pre-F2 readers are
#: ``extra="forbid"`` and must keep parsing unsigned lines).
_OMIT_WHEN_NONE = ("signature", *_HASHED_OPTIONAL_KEYS)


def _refuse(self, *args, **kwargs):
    raise TypeError(f"a LedgerEvent payload is read-only ({type(self).__name__}): copy it first")


class _FrozenDict(dict):
    """A read-only dict (still ``== dict`` and still JSON-serialisable). Every mutator raises TypeError;
    a copy or deepcopy is an ordinary mutable ``dict``."""

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _refuse
    __ior__ = __init__ = _refuse   # __init__: ``d.__init__(k=v)`` rewrites a dict subclass in place
    __hash__ = None  # type: ignore[assignment]

    def __reduce__(self):
        return (dict, (dict(self),))

    def copy(self):
        return dict(self)


class _FrozenList(list):
    """A read-only list (still ``== list`` and JSON-serialisable); a copy is an ordinary ``list``."""

    __setitem__ = __delitem__ = __iadd__ = __imul__ = __init__ = _refuse
    append = clear = extend = insert = pop = remove = reverse = sort = _refuse
    __hash__ = None  # type: ignore[assignment]

    def __reduce__(self):
        return (list, (list(self),))

    def copy(self):
        return list(self)


def _deep_freeze(value: Any) -> Any:
    """``value`` with every dict/list at any depth replaced by a read-only copy (the input is not touched,
    so a caller's own dict is never aliased)."""
    t = type(value)
    if t is dict or t is _FrozenDict:
        out = dict.__new__(_FrozenDict)
        dict.update(out, value)
        for k, v in value.items():
            tv = type(v)
            if tv is not str and tv is not int and tv is not float and tv is not bool and v is not None:
                dict.__setitem__(out, k, _deep_freeze(v))
        return out
    if t is list or t is _FrozenList:
        out = list.__new__(_FrozenList)
        list.extend(out, value)
        for i, v in enumerate(value):
            tv = type(v)
            if tv is not str and tv is not int and tv is not float and tv is not bool and v is not None:
                list.__setitem__(out, i, _deep_freeze(v))
        return out
    if isinstance(value, dict):          # another dict/list subclass: same treatment, as plain read-only copies
        return _deep_freeze(dict(value))
    if isinstance(value, list):
        return _deep_freeze(list(value))
    return value


class LedgerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    ts: str  # ISO 8601 UTC — stored as string so hashing is byte-stable
    event_type: str
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    hash: str
    # F2 (additive). ``signature``: base64 Ed25519 over ``event_signing_bytes``
    # (outside the hash). ``signing_failed``: True on a stop-type event the
    # ledger accepted unsigned under FIELD_LEDGER_REQUIRE_SIGNING=1 with no
    # key loaded (inside the hash). Both omitted from JSON when None.
    signature: str | None = None
    signing_failed: bool | None = None
    # F2b (additive, all inside the hash, omitted from JSON when None).
    # ``caller_id`` / ``caller_ts`` / ``caller_signature``: the caller's claim,
    # stored only after the ledger verified it against its keyring.
    # ``caller_unsigned``: True on a stop-type event the ledger accepted
    # without caller fields under FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1.
    caller_id: str | None = None
    caller_ts: str | None = None
    caller_signature: str | None = None
    caller_unsigned: bool | None = None

    # No return annotation on purpose (see ChainVerification below).
    @model_serializer(mode="wrap")
    def _omit_f2_keys_when_none(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for key in _OMIT_WHEN_NONE:
                if data.get(key) is None:
                    data.pop(key, None)
        return data


def _plain_event(data: dict[str, Any]) -> "LedgerEvent":
    return LedgerEvent.model_validate(data)


class ReadOnlyLedgerEvent(LedgerEvent):
    """A ``LedgerEvent`` a caller cannot change: attribute assignment raises, and ``payload`` is a deep read-only
    copy (``dict``/``list`` subclasses whose every mutator, ``__init__`` included, raises ``TypeError``; still
    ``==`` a plain dict/list and still JSON-serialisable). It is what the sealed-ledger parse cache hands out
    (B-GL-ledger-cache-immutable): the cache keeps its own, plain ``LedgerEvent`` objects private, so a caller
    cannot corrupt them. Build one with ``ReadOnlyLedgerEvent.of(event)``; ``LedgerEvent`` itself is unchanged
    (plain, mutable, validated exactly as before). Equal to a ``LedgerEvent`` with the same fields (either side
    of ``==``); unhashable, as a ``LedgerEvent`` is. A ``model_dump()``, ``LedgerEvent(**event.model_dump())``,
    a pickle round trip (which yields a plain ``LedgerEvent``) are ordinary mutable data. ``copy.deepcopy`` is NOT: it
    returns a ``ReadOnlyLedgerEvent`` (fields still refuse assignment) whose payload is a plain, detached, mutable
    ``dict``/``list`` tree.

    Refused (``TypeError``/``ValidationError``): field assignment, any ``_name`` assignment including
    ``__dict__``, ``__init__`` after construction (re-initialisation), ``__setstate__``, assigning ``__class__``
    (``ev.__class__ = X`` and ``object.__setattr__(ev, "__class__", X)``), and every payload mutator at any depth.

    NOT stopped (a deliberate low-level bypass): ``vars(ev)[k] = ...`` / ``ev.__dict__[k] = ...`` (the dict
    itself), ``object.__setattr__(ev, field, ...)``, the unbound base calls ``LedgerEvent.__init__(ev, ...)``, ``BaseModel.__init__(ev, ...)`` and
    ``BaseModel.__setstate__(ev, state)``, ``validate_assignment`` (``model_config`` flipped), ``gc`` (finding and
    rewriting the objects), the unbound ``dict.`` / ``list.`` methods on a payload container (``dict.__setitem__``,
    ``dict.update``, ``list.sort``, ``list.append``, ... not only ``__setitem__``), ``type.__setattr__``,
    descriptor ``__set__`` calls, ctypes, ``model_construct``.
    CONSEQUENCE: the sealed-ledger hands every caller the SAME twin of an event (built once, kept beside the
    parse cache), so a bypass on a handed-out event changes what every LATER caller of ``events()`` /
    ``snapshot()`` / the API receives, in this process, until the file changes; that includes ``verify_anchors``,
    ``verify_witness`` and the CLI F2 check, which all read ``snapshot()``, so a bypass can make them report ok. ``verify()`` is unaffected (it
    reads the private plain events, never the twin). No in-repo caller does this."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, /, **data: Any) -> None:
        # Constructing is fine, RE-initialising a live (possibly shared) event is not: ``ev.__init__(**forged)``
        # rewrites it in place through the ordinary Python API. ``of`` fills the slots directly, never via here.
        if hasattr(self, "__pydantic_fields_set__"):
            raise TypeError("a ReadOnlyLedgerEvent cannot be re-initialised: build a new one")
        super().__init__(**data)

    def __setstate__(self, state: Any) -> None:
        raise TypeError("a ReadOnlyLedgerEvent cannot be rewritten through __setstate__")

    def __reduce__(self):
        # pickle / copy.copy-by-reduce rebuild a DETACHED, plain, mutable LedgerEvent, never this shared one.
        return (_plain_event, (self.model_dump(),))

    def __setattr__(self, name: str, value: Any) -> None:
        # pydantic sends ``_name`` assignments (``__dict__`` too) past ``frozen`` to ``object.__setattr__``.
        if name.startswith("_"):
            raise TypeError(f"a ReadOnlyLedgerEvent is read-only: cannot set {name!r}")
        super().__setattr__(name, value)

    @property  # type: ignore[misc]
    def __class__(self):
        return type(self)

    @__class__.setter
    def __class__(self, value):
        raise TypeError("the class of a ReadOnlyLedgerEvent cannot be reassigned")

    @classmethod
    def of(cls, event: LedgerEvent) -> "ReadOnlyLedgerEvent":
        """A read-only copy of ``event`` (a LedgerEvent that was already validated; nothing is re-validated,
        and ``event``, payload included, is not aliased or touched)."""
        # What ``model_construct`` does, minus its per-field defaulting loop (about 2x cheaper per event; it is
        # on the first hand-out of every cached event). Pinned against ``model_construct`` by a test, because it
        # sets pydantic's own four instance slots.
        fields = dict(event.__dict__)
        fields["payload"] = _deep_freeze(fields["payload"])
        new = cls.__new__(cls)
        setter = object.__setattr__
        setter(new, "__dict__", fields)
        setter(new, "__pydantic_fields_set__", set(event.__pydantic_fields_set__))
        setter(new, "__pydantic_extra__", None)
        setter(new, "__pydantic_private__", None)
        return new

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LedgerEvent):
            return self.__dict__ == other.__dict__
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]


def _canonical_bytes(record: dict[str, Any]) -> bytes:
    """Deterministic serialization: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def reject_non_finite(value: Any) -> None:
    """Raise ``ValueError`` if a NaN or infinite float sits anywhere in ``value``.

    A payload with one cannot be re-verified: the seal hashes a ``NaN`` token but
    the served JSON carries ``null``, so the chain reads as tampered. Iterative,
    so a deep payload cannot hit the recursion limit. The message never carries
    the value or a key (both are caller data). It has no depth or visit bound of
    its own (it loops on a cycle): call ``reject_too_deep`` first.
    """
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, float):
            if not math.isfinite(v):
                raise ValueError("payload carries a non-finite number")
        elif isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, (list, tuple)):
            stack.extend(v)


#: The deepest payload an append accepts, counted in NODES with the payload itself as level 1 (``{}`` is 1, ``{"a": {}}``
#: is 2, ``{"a": 1}`` is 2: a scalar value is a node one level below its container). Dicts, lists and tuples all count a
#: level. The serializer's own limit is version-dependent: pydantic-core's JSON serializer raises
#: ``PydanticSerializationError`` ("Circular reference detected (depth exceeded)") at ``model_dump_json``, an unmapped
#: 500 over HTTP, at 99 levels on 2.46.4 (an off-pin build, measured: 98 seals and 99 fails in every dict/list/mixed
#: shape) and at about 252 payload levels on the pinned 2.50.1 (integration/constraints.txt). Our bound is the FLOOR of
#: every version seen: it always fires first, before anything is written, and a sealed event can be re-serialised
#: (served, exported) on any host. A test probes the installed serializer and fails if its limit ever drops below ours.
MAX_PAYLOAD_DEPTH = 98

#: The walk visits PATHS, not distinct objects, so a shared sub-object (a DAG: two references per level) is walked once
#: per path, 2**depth times: a visit budget, counted in containers (a flat list of a million scalars is one), refuses
#: it with the same fixed text. No real payload comes near it (the deepest and largest in the repo's writers and
#: fixtures is a handful of containers).
MAX_PAYLOAD_CONTAINERS = 1_000_000


def reject_too_deep(value: Any, limit: int = MAX_PAYLOAD_DEPTH) -> None:
    """Raise ``ValueError("payload nests too deeply")`` if a node of ``value`` lies deeper than ``limit`` levels (the
    value itself is level 1; every node counts, a scalar too; dicts, lists and tuples nest), or if the walk would visit
    more than ``MAX_PAYLOAD_CONTAINERS`` containers (a shared sub-object is walked once per path). Iterative, so
    neither a deep payload nor a self-referencing one can hit the recursion limit (a cycle is deeper than any limit
    and is refused). The message never carries the value.

    Run this BEFORE ``reject_non_finite`` wherever both are needed: that walk has no depth or visit bound of its own
    and would loop on a cycle (every caller in the repo does: ``make_event``, ``store._append``, ``AppendRequest``)."""
    stack: list[tuple[Any, int]] = [(value, 1)]
    containers = 0
    while stack:
        v, level = stack.pop()
        if level > limit:       # every node counts, a scalar too: the serializer's own counter walks values, not only containers
            raise ValueError("payload nests too deeply")
        if isinstance(v, dict):
            containers += 1
            children: Any = v.values()
        elif isinstance(v, (list, tuple)):
            containers += 1
            children = v
        else:
            continue
        if containers > MAX_PAYLOAD_CONTAINERS:
            raise ValueError("payload nests too deeply")
        stack.extend((child, level + 1) for child in children)


def compute_event_hash(event: LedgerEvent | dict[str, Any]) -> str:
    """sha-256 over the canonical record minus ``hash`` and minus ``signature``
    (F2: the signature is taken over the hash, so it cannot be inside it).
    ``signing_failed`` stays inside the hash."""
    record = event.model_dump() if isinstance(event, LedgerEvent) else dict(event)
    record.pop("hash", None)
    record.pop("signature", None)
    for key in _HASHED_OPTIONAL_KEYS:  # a dict may spell the omission as None
        if record.get(key) is None:
            record.pop(key, None)
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def event_signing_bytes(event: LedgerEvent | dict[str, Any]) -> bytes:
    """F2: the bytes a per-event signature covers — the canonical record
    INCLUDING ``hash`` (and ``signing_failed`` when set) and EXCLUDING
    ``signature``. Pure (no cryptography import): signing and verification
    are ``field_core.signing.sign_event`` / ``verify_event_signature``."""
    record = event.model_dump() if isinstance(event, LedgerEvent) else dict(event)
    record.pop("signature", None)
    for key in _HASHED_OPTIONAL_KEYS:
        if record.get(key) is None:
            record.pop(key, None)
    return _canonical_bytes(record)


def flag_signing_failed(event: LedgerEvent) -> LedgerEvent:
    """F2: stamp ``signing_failed: true`` on an UNSIGNED event and re-seal it
    (the flag is inside the hash, so removing it later breaks the chain).
    The ledger applies this to a stop-type event it accepts without a key;
    a signed event is never flagged (``ValueError``)."""
    if event.signature is not None:
        raise ValueError("a signed event cannot be flagged signing_failed")
    record = event.model_dump(exclude={"hash", "signature"})
    record["signing_failed"] = True
    return LedgerEvent(**record, hash=compute_event_hash(record))


def make_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    prev_hash: str = GENESIS_HASH,
    agent_id: str | None = None,
    ts: str | None = None,
    event_id: str | None = None,
) -> LedgerEvent:
    """Build a sealed event linked to ``prev_hash``."""
    reject_too_deep(payload)      # first: it also refuses a self-referencing payload before the walk below could loop
    reject_non_finite(payload)
    partial = {
        "event_id": event_id or str(uuid.uuid4()),
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "agent_id": agent_id,
        "payload": payload or {},
        "prev_hash": prev_hash,
    }
    return LedgerEvent(**partial, hash=compute_event_hash(partial))


_SEGMENT_KEYS = ("segments", "archived_segments", "verified_events", "break_segment")


class ChainVerification(BaseModel):
    ok: bool
    length: int
    first_break_index: int | None = None
    reason: str | None = None
    # Segmented (rotated) ledgers only. All None on a single-file chain, and
    # then left OUT of every serialisation, so a ledger that never rotated
    # serialises to exactly the four keys above (the C1 export bundle pins
    # that dict). ``length`` and ``first_break_index`` are global indices.
    segments: int | None = None  # live segments walked (closed + open)
    archived_segments: int | None = None  # verified by journal link only
    verified_events: int | None = None  # live events whose hashes were recomputed
    break_segment: int | None = None  # the segment holding first_break_index

    # No return annotation on purpose: with one, pydantic (and so FastAPI's
    # OpenAPI) describes the response as a bare object instead of these fields.
    @model_serializer(mode="wrap")
    def _omit_segment_keys_on_single_file(self, handler):
        data = handler(self)
        if self.segments is None and isinstance(data, dict):
            for key in _SEGMENT_KEYS:
                data.pop(key, None)
        return data


def verify_chain(
    events: Iterable[LedgerEvent], genesis: str = GENESIS_HASH
) -> ChainVerification:
    """Walk the chain; report the first break (index + reason).

    ``genesis`` is the ``prev_hash`` the first event must carry. It defaults
    to 64 zeros (a chain that starts at the beginning of history); pass a
    previous head hash to verify a chain segment that continues it.
    ``first_break_index`` is always the index within ``events``.
    """
    prev_hash = genesis
    count = 0
    for i, event in enumerate(events):
        count = i + 1
        if event.prev_hash != prev_hash:
            return ChainVerification(
                ok=False,
                length=count,
                first_break_index=i,
                reason=(
                    f"link break at index {i}: prev_hash {event.prev_hash[:12]}… "
                    f"does not match previous event hash {prev_hash[:12]}…"
                ),
            )
        try:
            recomputed = compute_event_hash(event)
        except ValueError:
            # text that cannot be UTF-8 encoded (a lone surrogate): no hash for it ever existed, so this is a
            # break, reported with a fixed text and never the value (no surrogatepass: that would be a new form)
            return ChainVerification(
                ok=False,
                length=count,
                first_break_index=i,
                reason=f"hash cannot be recomputed at index {i} (text that cannot be encoded)",
            )
        if recomputed != event.hash:
            return ChainVerification(
                ok=False,
                length=count,
                first_break_index=i,
                reason=(
                    f"hash mismatch at index {i}: stored {event.hash[:12]}… "
                    f"!= recomputed {recomputed[:12]}… (record was mutated)"
                ),
            )
        prev_hash = event.hash
    return ChainVerification(ok=True, length=count)
