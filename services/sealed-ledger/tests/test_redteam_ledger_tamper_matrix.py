"""Red-team CI plan M9 / T8: ledger tamper matrix.

Every case builds a fresh ledger with the real ``LedgerStore`` (ephemeral
``tmp_path``, no key, no estate), copies the file, damages the COPY the way an
attacker with write access to the file would, and asks three independent
verifiers: ``LedgerStore.verify()``, the served ``GET /verify`` and the
``ledger verify`` CLI. Oracles are deterministic (ok flag, first_break_index,
reason text, exit code); there is no LLM judge.

Positive control: the untouched copy passes on all three.

Documented limits, pinned rather than hidden: a plain chain walk cannot see a
truncated tail, a self-consistent rewrite of the last event, or a wholesale
re-chain (a chain proves self-consistency, not completeness). The closing
control is the signed anchor file (``sealed_ledger.anchors``); the last tests
show the anchor catches what the plain walk is blind to.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.ledger import GENESIS_HASH, compute_event_hash
from field_core.signing import generate_keypair
from sealed_ledger.anchors import verify_anchors, write_anchor
from sealed_ledger.api import create_app
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

N = 6
runner = CliRunner()


@pytest.fixture()
def original(tmp_path):
    """A pristine 6-event ledger; tests only ever damage a COPY of it."""
    path = tmp_path / "orig" / "events.jsonl"
    path.parent.mkdir()
    store = LedgerStore(path)
    for i in range(N):
        store.append("action", {"seq": i, "amount": 100 + i}, agent_id="rt-agent")
    assert store.verify().ok
    return path


@pytest.fixture()
def copy(original, tmp_path):
    dest = tmp_path / "copy" / "events.jsonl"
    dest.parent.mkdir()
    shutil.copyfile(original, dest)
    return dest


def read_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_bytes().decode("utf-8").split("\n") if ln.strip()]


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def dump(rec: dict) -> str:
    return json.dumps(rec, sort_keys=True, separators=(",", ":"))


def edit(path: Path, index: int, mutate, rehash: bool = False) -> None:
    lines = read_lines(path)
    rec = json.loads(lines[index])
    mutate(rec)
    if rehash:
        rec["hash"] = compute_event_hash(rec)
    lines[index] = dump(rec)
    write_lines(path, lines)


def rechain(path: Path) -> None:
    """Attacker without any key rewrites the whole chain consistently."""
    prev = GENESIS_HASH
    out = []
    for ln in read_lines(path):
        rec = json.loads(ln)
        rec["prev_hash"] = prev
        rec["hash"] = compute_event_hash(rec)
        prev = rec["hash"]
        out.append(dump(rec))
    write_lines(path, out)


def verdicts(path: Path, store: LedgerStore | None = None) -> dict:
    """Run all three verifiers on the file at ``path``. ``store`` is a store
    that was opened BEFORE the file was damaged (a running service)."""
    store = store or LedgerStore(path)
    direct = store.verify()
    http = TestClient(create_app(store=store)).get("/verify")
    assert http.status_code == 200
    cli = runner.invoke(cli_app, ["verify", "--path", str(path)])
    return {"direct": direct, "http": http.json(), "cli": cli}


def assert_detected(v: dict, index: int, reason_has: str) -> None:
    d, h, c = v["direct"], v["http"], v["cli"]
    assert d.ok is False
    assert d.first_break_index == index
    assert reason_has in (d.reason or "")
    assert h["ok"] is False
    assert h["first_break_index"] == index
    assert reason_has in (h["reason"] or "")
    assert c.exit_code == 1, c.output
    assert c.stdout.startswith("TAMPERED"), c.output
    assert reason_has in c.stdout


def assert_cli_fails_closed_on_unparseable(cli) -> None:
    """DISCREPANCY vs the plan ('clear reason'): for a line that does not parse,
    ``ledger verify`` does not print a ``TAMPERED`` line. It exits 1 with the
    parser exception escaping (``cli.exception``). Failure is detected (fail
    closed); the message is just not curated. Pinned to actual behaviour."""
    assert cli.exit_code == 1
    assert isinstance(cli.exception, ValueError)  # JSONDecodeError / ValidationError
    assert not cli.stdout.startswith("OK")


# --- positive control ---------------------------------------------------------


def test_untouched_copy_passes_all_three_verifiers(copy):
    v = verdicts(copy)
    assert v["direct"].ok is True and v["direct"].length == N
    assert v["http"]["ok"] is True and v["http"]["length"] == N
    assert v["http"]["first_break_index"] is None
    assert v["cli"].exit_code == 0, v["cli"].output
    assert v["cli"].stdout.startswith("OK")


# --- detected tampers ---------------------------------------------------------


@pytest.mark.parametrize("target", [0, 2, N - 1])
def test_edit_payload_without_rehash_is_detected_at_that_event(copy, target):
    edit(copy, target, lambda r: r["payload"].update(amount=999_999))
    assert_detected(verdicts(copy), target, "hash mismatch")


@pytest.mark.parametrize("field", ["agent_id", "event_type", "ts", "event_id"])
def test_edit_envelope_field_without_rehash_is_detected(copy, field):
    edit(copy, 3, lambda r: r.update({field: "forged-" + field}))
    assert_detected(verdicts(copy), 3, "hash mismatch")


def test_edit_with_local_rehash_is_detected_at_the_next_link(copy):
    edit(copy, 2, lambda r: r["payload"].update(amount=1), rehash=True)
    assert_detected(verdicts(copy), 3, "link break")


def test_edit_of_the_last_event_with_local_rehash_is_not_detected_by_chain_alone(copy):
    """Pinned limit: nothing follows the tail, so a self-consistent rewrite of
    the LAST event leaves a valid chain. Closed only by an anchor of the old
    head (see the anchor tests below)."""
    edit(copy, N - 1, lambda r: r["payload"].update(amount=1), rehash=True)
    v = verdicts(copy)
    assert v["direct"].ok and v["http"]["ok"] and v["cli"].exit_code == 0


@pytest.mark.parametrize("target", [0, 2, N - 2])
def test_delete_event_is_detected_at_the_successor(copy, target):
    lines = read_lines(copy)
    del lines[target]
    write_lines(copy, lines)
    assert_detected(verdicts(copy), target, "link break")


def test_reorder_adjacent_events_is_detected(copy):
    lines = read_lines(copy)
    lines[2], lines[3] = lines[3], lines[2]
    write_lines(copy, lines)
    assert_detected(verdicts(copy), 2, "link break")


def test_reverse_whole_file_is_detected(copy):
    write_lines(copy, list(reversed(read_lines(copy))))
    assert_detected(verdicts(copy), 0, "link break")


@pytest.mark.parametrize("target", [0, 2, N - 1])
def test_duplicate_event_line_is_detected(copy, target):
    lines = read_lines(copy)
    lines.insert(target + 1, lines[target])
    write_lines(copy, lines)
    assert_detected(verdicts(copy), target + 1, "link break")


def test_bad_genesis_prev_hash_is_detected_at_index_zero(copy):
    edit(copy, 0, lambda r: r.update(prev_hash="f" * 64))
    assert_detected(verdicts(copy), 0, "link break")


def test_bad_prev_hash_in_the_middle_is_detected(copy):
    edit(copy, 4, lambda r: r.update(prev_hash="a" * 64))
    assert_detected(verdicts(copy), 4, "link break")


def test_forged_hash_value_is_detected(copy):
    edit(copy, 1, lambda r: r.update(hash="0" * 64))
    assert_detected(verdicts(copy), 1, "hash mismatch")


def test_invalid_json_line_is_detected_with_a_clear_reason(copy):
    """A store already serving when the file is damaged reports it on /verify."""
    store = LedgerStore(copy)
    lines = read_lines(copy)
    lines[3] = lines[3][: len(lines[3]) // 2]  # cut mid-record
    write_lines(copy, lines)
    v = verdicts(copy, store)
    assert v["direct"].ok is False and v["direct"].first_break_index == 3
    assert "JSONDecodeError" in v["direct"].reason
    assert v["http"]["ok"] is False and v["http"]["first_break_index"] == 3
    assert "JSONDecodeError" in v["http"]["reason"]
    assert_cli_fails_closed_on_unparseable(v["cli"])


@pytest.mark.parametrize("junk", ["[1, 2, 3]", "42", '"a string"', "null"])
def test_non_dict_record_is_detected_with_a_clear_reason(copy, junk):
    store = LedgerStore(copy)
    lines = read_lines(copy)
    lines[2] = junk
    write_lines(copy, lines)
    v = verdicts(copy, store)
    assert v["direct"].ok is False and v["direct"].first_break_index == 2
    assert v["direct"].reason  # non-empty, human-readable
    assert v["http"]["ok"] is False and v["http"]["first_break_index"] == 2
    assert_cli_fails_closed_on_unparseable(v["cli"])


def test_extra_unknown_field_is_detected(copy):
    store = LedgerStore(copy)
    edit(copy, 2, lambda r: r.update(injected="x"))
    v = verdicts(copy, store)
    assert v["direct"].ok is False and v["direct"].first_break_index == 2
    assert v["http"]["ok"] is False and v["http"]["first_break_index"] == 2
    assert_cli_fails_closed_on_unparseable(v["cli"])


@pytest.mark.parametrize("damage", ["cut-json", "non-dict", "extra-field"])
def test_opening_a_store_on_an_unparseable_file_fails_closed(copy, damage):
    """A cold start on a damaged file refuses to open (raises) instead of
    appending after a corrupt tail: loud, not silent."""
    lines = read_lines(copy)
    if damage == "cut-json":
        lines[3] = lines[3][:50]
    elif damage == "non-dict":
        lines[3] = "[1, 2, 3]"
    else:
        rec = json.loads(lines[3])
        rec["injected"] = "x"
        lines[3] = dump(rec)
    write_lines(copy, lines)
    with pytest.raises(ValueError):  # JSONDecodeError / pydantic ValidationError
        LedgerStore(copy)


# --- documented limits: undetected by a plain walk, closed by the anchor ----------


def test_tail_truncation_is_not_detected_by_chain_alone(copy):
    """Pinned limit (T8): dropping trailing events leaves a valid shorter
    chain. A green plain /verify means 'internally consistent', never
    'complete'."""
    write_lines(copy, read_lines(copy)[:3])
    v = verdicts(copy)
    assert v["direct"].ok is True and v["direct"].length == 3
    assert v["http"]["ok"] is True and v["http"]["length"] == 3
    assert v["cli"].exit_code == 0


def test_full_rechain_is_not_detected_by_chain_alone(copy):
    edit(copy, 1, lambda r: r["payload"].update(amount=1))
    rechain(copy)
    v = verdicts(copy)
    assert v["direct"].ok is True and v["http"]["ok"] is True and v["cli"].exit_code == 0


@pytest.fixture()
def anchored(original, tmp_path):
    private_pem, public_pem = generate_keypair()
    anchors = tmp_path / "anchors.jsonl"
    write_anchor(LedgerStore(original), anchors, private_key_pem=private_pem)
    return anchors, public_pem


def test_anchor_positive_control_untouched_copy_verifies(copy, anchored):
    anchors, pub = anchored
    assert verify_anchors(LedgerStore(copy), anchors, public_key_pem=pub).ok


def test_anchor_closes_tail_truncation(copy, anchored):
    anchors, pub = anchored
    write_lines(copy, read_lines(copy)[:3])
    result = verify_anchors(LedgerStore(copy), anchors, public_key_pem=pub)
    assert not result.ok
    assert "shrank" in result.first_failure


def test_anchor_closes_full_rechain(copy, anchored):
    anchors, pub = anchored
    edit(copy, 1, lambda r: r["payload"].update(amount=1))
    rechain(copy)
    result = verify_anchors(LedgerStore(copy), anchors, public_key_pem=pub)
    assert not result.ok
    assert result.first_failure  # names the mismatch


def test_anchor_closes_last_event_rewrite(copy, anchored):
    anchors, pub = anchored
    edit(copy, N - 1, lambda r: r["payload"].update(amount=1), rehash=True)
    result = verify_anchors(LedgerStore(copy), anchors, public_key_pem=pub)
    assert not result.ok
    assert result.first_failure
