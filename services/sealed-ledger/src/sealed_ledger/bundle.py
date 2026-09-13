"""Auditor export bundle — write it, and re-verify it offline.

A bundle is a directory ``out_dir/<stamp>/`` holding four files:

- ``events.jsonl``: the exported events, one PURE ``LedgerEvent`` JSON object
  per line (no added keys; ``extra='forbid'`` and the hash recompute depend
  on that).
- ``summary.json``: counts, timestamps, the global ``indices`` of the
  exported events, ``first_index``/``last_index``/``head_index``, the
  verification of the FULL live chain at export time, and ``signed``.
- ``chain_proof.json``: ``first_index, last_index, head_index,
  first_prev_hash, head_hash, verification, filters, spine``, where ``spine``
  is ``[{index, event_id, prev_hash, hash}]`` for EVERY chain event from
  ``first_index`` to ``head_index``, exported or not.
- ``signature.json``: ``signed: false`` — or, when a private key is given
  (``ledger export --sign-key``; the served route never signs), an Ed25519
  signature over the canonical JSON of ``{"summary": <summary.json>,
  "chain_proof": <chain_proof.json>}`` plus the signer's ``key_fingerprint``.

What ``verify_bundle`` proves, and what it does not:

- Every exported event's hash is recomputed and must equal both its stored
  hash and the spine's hash at its index; the spine's links are walked from
  ``first_prev_hash`` to ``head_hash``; counts are recomputed.
- A bundle whose recorded filters are ALL null claims every event, so it must
  export every index from 0 to ``head_index`` with ``first_prev_hash`` equal
  to the genesis hash; a gap fails naming the first missing index. Whenever
  ``first_index`` is 0, ``first_prev_hash`` must be the genesis hash.
- Indices are global. On a rotated ledger whose oldest segments were archived
  (C2), the verification's ``length - verified_events`` is the archived
  prefix: an unfiltered bundle must then export every index from that prefix
  to ``head_index``, and its first event must be the rotation event that
  closed the last archived segment. The prefix is a claim of the verification
  dict, which an editor of an UNSIGNED bundle controls: dropping whole leading
  segments and claiming them archived is internally consistent (the verifier
  prints the archived prefix; a signature or the archive itself catches it).
- Every JSON file and every events.jsonl line is parsed with duplicate keys
  refused, so no reader can be shown a value other than the one verified.
  events.jsonl is split on ``\\n`` only (JSON strings may hold U+2028, U+2029
  or NEL raw; ``str.splitlines`` would cut a genuine event in two).
- UNSIGNED (or signed but checked without a public key): internal
  consistency only. Someone who edits the files can rebuild a consistent
  spine, because the spine carries only hashes for events that were not
  exported. The verifier says "spine unverified".
- SIGNED and checked with the signer's public key: the spine and counts are
  the ones the key holder attested; exported events are bound to it through
  their hashes.
- Neither proves the ledger's history to a third party: that needs
  ``head_hash`` compared with an anchor held off-box. For a CONTIGUOUS
  bundle (every index from ``first_index`` to ``head_index`` exported) every
  link is recomputed from event content, so an anchor match at
  ``head_index`` covers the exported events. For a FILTERED bundle the gaps
  are hash-only entries that cannot be recomputed: an anchor match proves the
  head, while the exported events' positions rest on the signature.
- Nothing proves a filtered export is complete (the spine has no
  agent_id/event_type/ts for the events it does not export).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ConfigDict, NonNegativeInt, ValidationError

from field_core.ledger import (
    GENESIS_HASH,
    ChainVerification,
    LedgerEvent,
    compute_event_hash,
    verify_chain,
)
from field_core.signing import key_fingerprint, sign_manifest, verify_manifest
from sealed_ledger.filters import EventFilter, InvalidTimeBound

EVENTS_FILE = "events.jsonl"
SUMMARY_FILE = "summary.json"
CHAIN_PROOF_FILE = "chain_proof.json"
SIGNATURE_FILE = "signature.json"
BUNDLE_FILES = (EVENTS_FILE, SUMMARY_FILE, CHAIN_PROOF_FILE, SIGNATURE_FILE)
SIGNED_PAYLOAD = (
    'canonical JSON (sorted keys, no whitespace, UTF-8) of '
    '{"summary": <summary.json>, "chain_proof": <chain_proof.json>}'
)


class InvalidSigningKey(ValueError):
    """The ``--sign-key`` PEM is not an Ed25519 private key."""


class ExportSummary(BaseModel):
    exported_at: str
    path: str  # the bundle's events.jsonl
    bundle_dir: str
    event_count: int
    head_hash: str
    first_ts: str | None = None
    last_ts: str | None = None
    first_index: NonNegativeInt | None = None
    last_index: NonNegativeInt | None = None
    head_index: NonNegativeInt | None = None
    indices: list[NonNegativeInt] = []
    event_types: dict[str, int]
    agents: dict[str, int]
    verification: ChainVerification  # of the FULL live chain at export time
    signed: bool = False


class SpineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: NonNegativeInt
    event_id: str
    prev_hash: str
    hash: str


class ExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: str | None = None
    until: str | None = None
    agent_id: str | None = None
    event_type: str | None = None


class ChainProof(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_index: NonNegativeInt | None
    last_index: NonNegativeInt | None
    head_index: NonNegativeInt | None
    first_prev_hash: str | None
    head_hash: str
    verification: ChainVerification
    filters: ExportFilters
    spine: list[SpineEntry]


class BundleSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signed: bool
    algorithm: str | None = None
    signed_payload: str | None = None
    key_fingerprint: str | None = None
    signature: str | None = None


class BundleVerification(BaseModel):
    ok: bool
    signed: bool = False
    signature_checked: bool = False
    spine_attested: bool = False  # signed AND the signature checked out
    # every index first_index..head_index exported, so every spine link was
    # recomputed from event content (a head_hash anchor match then covers them)
    contiguous: bool = False
    # the recorded filters are all null: verified to export every live index
    # archived_prefix..head
    unfiltered: bool = False
    # a rotated ledger's archived segments hold indices 0..archived_prefix-1;
    # they are not in the bundle (verify them from the archive)
    archived_prefix: int = 0
    filters: dict[str, str | None] | None = None
    event_count: int = 0
    first_index: int | None = None
    last_index: int | None = None
    head_index: int | None = None
    head_hash: str | None = None
    key_fingerprint: str | None = None
    first_failing_index: int | None = None
    reason: str | None = None


# --------------------------------------------------------------------- write


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _signer_public_pem(private_key_pem: str) -> str:
    try:
        private = serialization.load_pem_private_key(
            private_key_pem.encode("ascii"), password=None
        )
    except (TypeError, ValueError) as exc:
        raise InvalidSigningKey(f"signing key is not a readable PEM private key: {exc}") from exc
    if not isinstance(private, Ed25519PrivateKey):
        raise InvalidSigningKey("signing key is not Ed25519")
    return private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _new_bundle_dir(out_dir: Path, now: datetime) -> Path:
    """A fresh ``out_dir/<stamp>/``; an existing bundle is never reused."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    for attempt in range(1000):
        candidate = out_dir / (stamp if attempt == 0 else f"{stamp}-{attempt}")
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise FileExistsError(f"could not allocate a new bundle directory under {out_dir}")


def _write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_bundle(
    out_dir: str | Path,
    snapshot: Sequence[LedgerEvent],
    event_filter: EventFilter,
    private_key_pem: str | None = None,
    verification: ChainVerification | None = None,
    start_index: int = 0,
) -> ExportSummary:
    """Write one bundle for ``snapshot`` (the whole live chain as read once).

    ``start_index`` is the global index of ``snapshot[0]`` (a rotated ledger
    whose oldest segments are archived starts there); every index in the
    bundle is global. ``verification`` is the store's verification of the
    same read (default: ``verify_chain(snapshot)``, a single-file chain).
    ``private_key_pem`` is validated before anything is written, so a bad key
    never leaves a half-written bundle behind.
    """
    public_pem = _signer_public_pem(private_key_pem) if private_key_pem is not None else None
    indices = [
        start_index + k for k, event in enumerate(snapshot)
        if event_filter.matches(start_index + k, event)
    ]
    exported = [snapshot[i - start_index] for i in indices]
    now = _utcnow()
    bundle_dir = _new_bundle_dir(Path(out_dir), now)

    events_path = bundle_dir / EVENTS_FILE
    _write_text(events_path, "".join(e.model_dump_json() + "\n" for e in exported))

    type_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    for event in exported:
        type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
        key = event.agent_id or "<none>"
        agent_counts[key] = agent_counts.get(key, 0) + 1

    if verification is None:
        verification = verify_chain(snapshot)
    head_index = start_index + len(snapshot) - 1 if snapshot else None
    head_hash = snapshot[-1].hash if snapshot else GENESIS_HASH
    first_index = indices[0] if indices else None
    last_index = indices[-1] if indices else None

    summary = ExportSummary(
        exported_at=now.isoformat(),
        path=str(events_path),
        bundle_dir=str(bundle_dir),
        event_count=len(exported),
        head_hash=head_hash,
        first_ts=exported[0].ts if exported else None,
        last_ts=exported[-1].ts if exported else None,
        first_index=first_index,
        last_index=last_index,
        head_index=head_index,
        indices=indices,
        event_types=type_counts,
        agents=agent_counts,
        verification=verification,
        signed=private_key_pem is not None,
    )
    spine = (
        [
            SpineEntry(
                index=start_index + k,
                event_id=snapshot[k].event_id,
                prev_hash=snapshot[k].prev_hash,
                hash=snapshot[k].hash,
            )
            for k in range(first_index - start_index, len(snapshot))
        ]
        if first_index is not None
        else []
    )
    chain_proof = ChainProof(
        first_index=first_index,
        last_index=last_index,
        head_index=head_index,
        first_prev_hash=(
            snapshot[first_index - start_index].prev_hash if first_index is not None else None
        ),
        head_hash=head_hash,
        verification=verification,
        filters=ExportFilters(**event_filter.as_dict()),
        spine=spine,
    )

    summary_text = summary.model_dump_json(indent=2) + "\n"
    chain_text = chain_proof.model_dump_json(indent=2) + "\n"
    if private_key_pem is not None:
        # sign exactly what a verifier will parse back out of the files
        payload = {"summary": json.loads(summary_text), "chain_proof": json.loads(chain_text)}
        signature = BundleSignature(
            signed=True,
            algorithm="ed25519",
            signed_payload=SIGNED_PAYLOAD,
            key_fingerprint=key_fingerprint(public_pem),
            signature=sign_manifest(payload, private_key_pem),
        )
    else:
        signature = BundleSignature(signed=False)

    _write_text(bundle_dir / CHAIN_PROOF_FILE, chain_text)
    _write_text(bundle_dir / SUMMARY_FILE, summary_text)
    _write_text(bundle_dir / SIGNATURE_FILE, signature.model_dump_json(indent=2) + "\n")
    return summary


# -------------------------------------------------------------------- verify


class _Fail(Exception):
    def __init__(self, reason: str, index: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.index = index


class DuplicateKeyError(ValueError):
    """A JSON object names the same key twice."""


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise DuplicateKeyError(
                f"duplicate key {key!r} (readers disagree on which copy counts, so "
                "the value shown could differ from the value verified)"
            )
        obj[key] = value
    return obj


def _strict_json(text: str) -> Any:
    """``json.loads`` that refuses a duplicate key at any depth."""
    return json.loads(text, object_pairs_hook=_refuse_duplicate_keys)


def _load_json(bundle: Path, name: str) -> Any:
    try:
        return _strict_json((bundle / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise _Fail(f"{name} unreadable: {exc}") from exc


def _model(model: type[BaseModel], raw: Any, name: str) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ())) or "<root>"
        raise _Fail(f"{name} is not a valid bundle file ({where}: {first.get('msg')})") from exc


def verify_bundle(
    bundle_dir: str | Path, public_key_pem: str | None = None
) -> BundleVerification:
    """Re-verify a bundle offline. Returns ``ok=False`` with
    ``first_failing_index`` (when the failure has an index) and a reason."""
    context: dict[str, Any] = {}
    try:
        return _verify(Path(bundle_dir), public_key_pem, context)
    except _Fail as fail:
        return BundleVerification(
            ok=False, first_failing_index=fail.index, reason=fail.reason, **context
        )


def _verify(
    bundle: Path, public_key_pem: str | None, context: dict[str, Any]
) -> BundleVerification:
    if not bundle.is_dir():
        raise _Fail(f"{bundle} is not a bundle directory")
    for name in BUNDLE_FILES:
        if not (bundle / name).is_file():
            raise _Fail(f"bundle is missing {name}")

    summary_raw = _load_json(bundle, SUMMARY_FILE)
    proof_raw = _load_json(bundle, CHAIN_PROOF_FILE)
    summary: ExportSummary = _model(ExportSummary, summary_raw, SUMMARY_FILE)
    proof: ChainProof = _model(ChainProof, proof_raw, CHAIN_PROOF_FILE)
    sig: BundleSignature = _model(BundleSignature, _load_json(bundle, SIGNATURE_FILE), SIGNATURE_FILE)
    context.update(
        signed=sig.signed,
        key_fingerprint=sig.key_fingerprint,
        head_hash=proof.head_hash,
        head_index=proof.head_index,
        first_index=proof.first_index,
        last_index=proof.last_index,
    )

    # 1. signature — before anything else is trusted
    signature_checked = False
    if sig.signed and not (sig.signature and sig.key_fingerprint):
        raise _Fail("signature.json says signed but carries no signature or key_fingerprint")
    if sig.signed and sig.algorithm != "ed25519":
        raise _Fail(f"signature.json algorithm {sig.algorithm!r} is not supported (ed25519 only)")
    if public_key_pem is not None:
        if not sig.signed:
            raise _Fail(
                "bundle is unsigned but a public key was supplied — nothing binds "
                "this bundle to that key"
            )
        try:
            supplied = key_fingerprint(public_key_pem)
        except ValueError as exc:
            raise _Fail(f"supplied public key is not usable: {exc}") from exc
        if supplied != sig.key_fingerprint:
            raise _Fail(
                f"wrong key: supplied key fingerprint {supplied[:12]}… but the bundle "
                f"was signed by {sig.key_fingerprint[:12]}…"
            )
        payload = {"summary": summary_raw, "chain_proof": proof_raw}
        if not verify_manifest(payload, sig.signature, public_key_pem):
            raise _Fail(
                "signature invalid — summary.json or chain_proof.json was altered "
                "after signing"
            )
        signature_checked = True
    context["signature_checked"] = signature_checked
    if summary.signed != sig.signed:
        raise _Fail("summary.json and signature.json disagree about whether the bundle is signed")

    # 2. the exporter's own verification of the full live chain
    v = proof.verification
    if not v.ok:
        raise _Fail(
            f"the ledger chain was already broken when this bundle was exported: {v.reason}",
            v.first_break_index,
        )
    if summary.verification.model_dump() != v.model_dump():
        raise _Fail("summary.json and chain_proof.json carry different chain verifications")

    # 3. header consistency
    head_index, first_index, last_index = proof.head_index, proof.first_index, proof.last_index
    for field in ("first_index", "last_index", "head_index", "head_hash"):
        if getattr(summary, field) != getattr(proof, field):
            raise _Fail(f"summary.json and chain_proof.json disagree on {field}")
    expected_length = 0 if head_index is None else head_index + 1
    if v.length != expected_length:
        raise _Fail(
            f"verification covered {v.length} events but head_index implies {expected_length}"
        )
    if head_index is None and proof.head_hash != GENESIS_HASH:
        raise _Fail("empty chain must have the zero head_hash")
    indices = summary.indices
    if len(indices) != summary.event_count:
        raise _Fail(
            f"summary.json lists {len(indices)} indices but event_count {summary.event_count}"
        )
    for k in range(1, len(indices)):
        if indices[k] <= indices[k - 1]:
            raise _Fail("summary.json indices are not strictly increasing", indices[k])
    if indices:
        if indices[0] != first_index or indices[-1] != last_index:
            raise _Fail("summary.json indices do not start at first_index and end at last_index")
        if head_index is None:
            raise _Fail("summary.json lists exported events but head_index says the chain is empty")
    elif first_index is not None or last_index is not None or proof.spine:
        raise _Fail("no events exported but chain_proof.json claims a first/last index or spine")
    elif proof.first_prev_hash is not None:
        raise _Fail("no events exported but chain_proof.json claims a first_prev_hash")
    try:
        event_filter = EventFilter(**proof.filters.model_dump())
    except InvalidTimeBound as exc:
        raise _Fail(f"chain_proof.json filters unusable: {exc}") from exc
    # No filter recorded = the export claims EVERY live event: indices must be
    # exactly archived_prefix..head_index (checked in the event walk and after
    # it). A single-file chain has no archived prefix.
    unfiltered = all(value is None for value in proof.filters.model_dump().values())
    context["filters"] = proof.filters.model_dump()
    archived_prefix = 0
    if v.segments is not None:
        # a rotated ledger whose oldest segments were archived exports its live
        # part only; the verification hash-verified exactly those events
        if v.verified_events is None or not 0 <= v.verified_events <= v.length:
            raise _Fail("verification carries segments but no usable verified_events")
        archived_prefix = v.length - v.verified_events
        if (archived_prefix > 0) != bool(v.archived_segments):
            raise _Fail(
                f"verification claims {v.archived_segments} archived segment(s) but "
                f"{archived_prefix} archived event(s)"
            )
        if indices and indices[0] < archived_prefix:
            raise _Fail(
                f"index {indices[0]} is exported but the verification says indices "
                f"0..{archived_prefix - 1} are archived",
                indices[0],
            )
    context["archived_prefix"] = archived_prefix

    # 4. spine: contiguous from first_index to head_index, linked to head_hash
    spine_fail: _Fail | None = None
    spine_by_index: dict[int, SpineEntry] = {}
    if first_index is not None:
        expected = head_index - first_index + 1
        prev_hash = proof.first_prev_hash
        if first_index == 0 and prev_hash != GENESIS_HASH:
            spine_fail = _Fail(
                f"first_index is 0 but chain_proof.json first_prev_hash "
                f"{str(prev_hash)[:12]}… is not the genesis hash",
                0,
            )
            expected = 0  # nothing after a false start is worth walking
        for k in range(expected):
            index = first_index + k
            if k >= len(proof.spine):
                spine_fail = _Fail(f"spine ends before head_index: index {index} missing", index)
                break
            entry = proof.spine[k]
            if entry.index != index:
                spine_fail = _Fail(
                    f"spine is not contiguous: expected index {index}, found {entry.index}", index
                )
                break
            if entry.prev_hash != prev_hash:
                spine_fail = _Fail(
                    f"spine link break at index {index}: prev_hash {entry.prev_hash[:12]}… "
                    f"does not match previous hash {str(prev_hash)[:12]}…",
                    index,
                )
                break
            spine_by_index[index] = entry
            prev_hash = entry.hash
        if spine_fail is None and len(proof.spine) != expected:
            spine_fail = _Fail(
                f"spine runs past head_index {head_index} ({len(proof.spine)} entries, "
                f"expected {expected})",
                head_index,
            )
        if spine_fail is None and prev_hash != proof.head_hash:
            spine_fail = _Fail(
                f"spine ends at {str(prev_hash)[:12]}… but head_hash is {proof.head_hash[:12]}…",
                head_index,
            )

    # 5. exported events: parse, locate, recompute, match
    # Split on "\n" ONLY — the same boundary LedgerStore.iter_events reads. A
    # JSON string may carry U+2028, U+2029 or NEL raw, and str.splitlines()
    # would cut a genuine event line in two. (JSON cannot hold a raw "\r".)
    lines = [
        line.strip()
        for line in (bundle / EVENTS_FILE).read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]
    event_fail: _Fail | None = None
    events: list[LedgerEvent] = []
    for j in range(max(len(lines), len(indices))):
        if j >= len(indices):
            event_fail = _Fail(
                f"events.jsonl has {len(lines)} events but summary.json lists {len(indices)}"
            )
            break
        index = indices[j]
        if unfiltered and archived_prefix + j < index <= head_index:
            # indices are strictly increasing from >= archived_prefix, so
            # index > archived_prefix + j means that index was skipped. (An
            # index past head_index is left to the spine-coverage check below.)
            missing = archived_prefix + j
            event_fail = _Fail(
                f"index {missing} is missing from an unfiltered export: no filter was "
                f"recorded, so every index {archived_prefix}..{head_index} must be exported "
                "(an event was deleted)",
                missing,
            )
            break
        if spine_fail is not None and spine_fail.index is not None and spine_fail.index <= index:
            break
        if j >= len(lines):
            event_fail = _Fail(
                f"exported event at index {index} is missing from events.jsonl "
                f"(a line was deleted)",
                index,
            )
            break
        try:
            event = LedgerEvent.model_validate(_strict_json(lines[j]))
        except (ValueError, ValidationError) as exc:
            event_fail = _Fail(
                f"events.jsonl line {j + 1} (index {index}) is not a pure LedgerEvent: {exc}",
                index,
            )
            break
        entry = spine_by_index.get(index)
        if entry is None:
            event_fail = _Fail(f"exported event at index {index} is not covered by the spine", index)
            break
        if event.event_id != entry.event_id:
            event_fail = _Fail(
                f"events.jsonl line {j + 1} is event {event.event_id!r} but the spine has "
                f"{entry.event_id!r} at index {index} (a line was deleted, inserted or reordered)",
                index,
            )
            break
        recomputed = compute_event_hash(event)
        if recomputed != event.hash:
            event_fail = _Fail(
                f"hash mismatch at index {index}: stored {event.hash[:12]}… != recomputed "
                f"{recomputed[:12]}… (exported record was mutated)",
                index,
            )
            break
        if event.hash != entry.hash or event.prev_hash != entry.prev_hash:
            event_fail = _Fail(
                f"exported event at index {index} does not match the spine (record was "
                f"re-hashed or re-linked)",
                index,
            )
            break
        try:
            matches = event_filter.matches(index, event)
        except ValueError as exc:
            event_fail = _Fail(str(exc), index)
            break
        if not matches:
            event_fail = _Fail(
                f"exported event at index {index} does not match the export filters", index
            )
            break
        if unfiltered and archived_prefix and index == archived_prefix:
            # the first live event after an archived prefix is always the
            # hash-chained rotation event that closed the last archived segment
            payload = event.payload
            if (event.event_type != "ledger.segment.rotated"
                    or payload.get("end_index") != archived_prefix - 1
                    or payload.get("head_hash") != event.prev_hash
                    or payload.get("segment_closed") != v.archived_segments):
                event_fail = _Fail(
                    f"index {index} should be the rotation event closing archived segment "
                    f"{v.archived_segments} (global 0..{archived_prefix - 1}), but it is not",
                    index,
                )
                break
        events.append(event)

    tail_fail: _Fail | None = None
    if unfiltered and len(indices) < expected_length - archived_prefix:
        # the gap check above cannot see a missing TAIL (or an empty selection)
        missing = archived_prefix + len(indices)
        tail_fail = _Fail(
            f"index {missing} is missing from an unfiltered export: no filter was "
            f"recorded, so every index {archived_prefix}..{head_index} must be exported, but "
            f"only {len(indices)} are (events were deleted)",
            missing,
        )

    failures = [f for f in (event_fail, spine_fail, tail_fail) if f is not None]
    if failures:
        with_index = [f for f in failures if f.index is not None]
        raise min(with_index, key=lambda f: f.index) if with_index else failures[0]

    # 6. counts and timestamps recomputed from the events
    type_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    for event in events:
        type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
        key = event.agent_id or "<none>"
        agent_counts[key] = agent_counts.get(key, 0) + 1
    if type_counts != summary.event_types:
        raise _Fail(f"summary.json event_types {summary.event_types} != recomputed {type_counts}")
    if agent_counts != summary.agents:
        raise _Fail(f"summary.json agents {summary.agents} != recomputed {agent_counts}")
    first_ts = events[0].ts if events else None
    last_ts = events[-1].ts if events else None
    if (summary.first_ts, summary.last_ts) != (first_ts, last_ts):
        raise _Fail("summary.json first_ts/last_ts do not match events.jsonl")

    return BundleVerification(
        ok=True,
        signed=sig.signed,
        signature_checked=signature_checked,
        spine_attested=sig.signed and signature_checked,
        contiguous=bool(indices) and indices == list(range(first_index, head_index + 1)),
        unfiltered=unfiltered,
        archived_prefix=archived_prefix,
        filters=proof.filters.model_dump(),
        event_count=len(events),
        first_index=first_index,
        last_index=last_index,
        head_index=head_index,
        head_hash=proof.head_hash,
        key_fingerprint=sig.key_fingerprint,
    )
