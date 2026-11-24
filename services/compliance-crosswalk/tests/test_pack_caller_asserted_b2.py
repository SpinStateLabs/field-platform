"""Backlog B2: ``POST /pack`` body sources are caller-asserted, and a full outage is "unknown", never "No gaps".

Before B2 an authenticated caller could post ``sources`` claiming a verified chain, a registry record, tokens and a
cap, and the pack printed every control "evidenced" with no ledger contact; and a run whose live collection got no
answer from any service still headlined "No gaps recorded". These tests pin the replacement rules:

* a positive verdict from body sources is evidenced only when this run's live collection gives the same control a
  positive verdict too; otherwise the row reads ``caller-asserted`` (evidenced None) and a ``caller-asserted`` gap
  is recorded;
* without an ``agent_id`` nothing can confirm body sources, so every positive verdict from them is caller-asserted;
* a negative caller verdict stands (over-conservative is survivable);
* an ``agent_id`` whose live collection gets no answer at all is ``evidence_status: unknown``, carries the FC-L-01
  ``not-checked`` gap and the UNKNOWN headline, and never says "No gaps recorded".
"""

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk import api as api_module
from compliance_crosswalk.api import create_app
from compliance_crosswalk.engine import EvidenceSources
from compliance_crosswalk.evidence_pack import (
    CALLER_ASSERTED_GAP,
    EVIDENCE_UNKNOWN_HEADLINE,
    LEDGER_NOT_CHECKED_GAP,
    generate_pack,
)
from compliance_crosswalk.staleness import StaleStore
from field_core.templates_api import template_data

SIGNER = "Controller, Spin State Labs"

#: everything a caller would need to claim to make every estate-evidenced control read "yes"
FORGED = {
    "registry_record": {"owner": "Controller"},
    "ledger_verify": {"ok": True},
    "ledger_event_types": {"kill.drill.complete": 1, "delegation.revoke": 1},
    "tokens": [{"token_id": "t1", "revoked": True}],
    "governor_cap": {"cap": 10},
}
#: controls whose positive verdict reads one of the sources above (or the "something was collected" rule)
SOURCE_BACKED = {"FC-R-01", "FC-I-01", "FC-L-01", "FC-E-01", "FC-E-02", "FC-D-01", "FC-D-02",
                 "FC-E-03", "FC-F-01", "FC-L-02"}


def resolved_manifest():
    data = template_data("default")
    data["agent"]["name"] = "b2-test-agent"
    data["agent"]["description"] = "exercises caller-asserted evidence"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = ["generate evidence packs"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(stale_store=StaleStore(tmp_path / "stale_flags.json")))


def _rows(body):
    return {c["control_id"]: c for c in body["pack"]["controls"]}


def _gap_kinds(body):
    return {(g["control_id"], g["kind"]) for g in body["pack"]["gaps"]}


def _live(monkeypatch, sources: EvidenceSources):
    calls: list[str] = []

    def fake_collect(agent_id):
        calls.append(agent_id)
        return sources

    monkeypatch.setattr(api_module, "collect_evidence", fake_collect)
    return calls


def test_forged_body_sources_without_agent_id_are_never_evidenced(client, monkeypatch):
    calls = _live(monkeypatch, EvidenceSources(ledger_verify={"ok": True}))
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(), "sources": FORGED})
    assert r.status_code == 200, r.text
    body = r.json()
    assert calls == []  # no agent_id: nothing to collect, so nothing can confirm the claim
    rows = _rows(body)
    assert not [cid for cid, row in rows.items() if row["evidenced"] is True]
    for cid in SOURCE_BACKED:
        assert rows[cid]["evidenced"] is None, cid
        assert rows[cid]["evidence_detail"].startswith("caller-asserted"), cid
        assert (cid, "caller-asserted") in _gap_kinds(body), cid
    assert body["pack"]["evidence_status"] == "caller-asserted"
    assert "No gaps recorded" not in body["markdown"]
    assert "| FC-L-01 | ledger.cryptographic_seal | yes | caller-asserted |" in body["markdown"]
    assert CALLER_ASSERTED_GAP in body["markdown"]


def test_forged_body_sources_during_a_full_outage_are_never_evidenced(client, monkeypatch):
    calls = _live(monkeypatch, EvidenceSources())  # every service unreachable
    r = client.post(
        "/pack",
        json={"signer": SIGNER, "manifest": resolved_manifest(), "agent_id": "agent-1", "sources": FORGED},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert calls == ["agent-1"]
    assert not [cid for cid, row in _rows(body).items() if row["evidenced"] is True]
    assert {("FC-L-01", "caller-asserted"), ("FC-R-01", "caller-asserted")} <= _gap_kinds(body)
    assert "No gaps recorded" not in body["markdown"]


def test_live_collection_confirms_only_what_it_saw(client, monkeypatch):
    # the ledger answered and verified; nothing else did. Every live verdict stands (F1): FC-L-01 True from the live
    # row, and the controls whose source the live run did not get read False (a live finding), not caller-asserted
    _live(monkeypatch, EvidenceSources(ledger_verify={"ok": True, "length": 7}))
    r = client.post(
        "/pack",
        json={"signer": SIGNER, "manifest": resolved_manifest(), "agent_id": "agent-1", "sources": FORGED},
    )
    body = r.json()
    rows = _rows(body)
    assert rows["FC-L-01"]["evidenced"] is True
    assert rows["FC-L-01"]["evidence_detail"] == "ledger chain verified"  # the live row, not the caller's
    for cid in ("FC-R-01", "FC-I-01", "FC-E-02", "FC-D-01"):
        assert rows[cid]["evidenced"] is False, cid               # the caller's True never upgrades a live False
        assert (cid, "not-evidenced") in _gap_kinds(body), cid
    assert not [g for g in body["pack"]["gaps"] if g["kind"] == "caller-asserted"]


def test_a_negative_caller_verdict_fills_an_unknown_row_as_a_gap(client, monkeypatch):
    calls = _live(monkeypatch, EvidenceSources(ledger_verify={"ok": True}))
    r = client.post(          # no agent_id: nothing is collected, so the caller's negative fills the unknown row
        "/pack",
        json={"signer": SIGNER, "manifest": resolved_manifest(),
              "sources": {"ledger_verify": {"ok": False, "reason": "hash mismatch"}}},
    )
    body = r.json()
    assert calls == []
    assert _rows(body)["FC-L-01"]["evidenced"] is False
    assert _rows(body)["FC-L-01"]["evidence_detail"].startswith("caller-asserted")
    assert ("FC-L-01", "not-evidenced") in _gap_kinds(body)


# ---- F1 (review of d8561c8): a caller's body can never hide what the live collection found -----------------------

def test_f1_live_failed_verify_with_an_empty_body_is_a_gap_not_no_gaps(client, monkeypatch):
    _live(monkeypatch, EvidenceSources(registry_record={"owner": "Controller"},
                                       ledger_verify={"ok": False, "reason": "hash mismatch at 3"}))
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(),
                                   "agent_id": "agent-1", "sources": {}})
    body = r.json()
    assert _rows(body)["FC-L-01"]["evidenced"] is False
    assert ("FC-L-01", "not-evidenced") in _gap_kinds(body)
    assert "No gaps recorded" not in body["markdown"]
    assert body["pack"]["evidence_status"] == "collected"        # N3: {} asserts nothing


def test_f1_partial_outage_keeps_the_not_checked_gap_with_an_empty_body(client, monkeypatch):
    _live(monkeypatch, EvidenceSources(registry_record={"owner": "Controller"}))      # ledger 503, registry up
    for sources in ({}, {"ledger_verify": None}, {"ledger_verify": {"ok": True}}):
        r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(),
                                       "agent_id": "agent-1", "sources": sources})
        body = r.json()
        assert ("FC-L-01", "not-checked") in _gap_kinds(body), sources
        assert _rows(body)["FC-L-01"]["evidenced"] is None, sources
        assert "No gaps recorded" not in body["markdown"], sources


def test_f1_live_false_beats_caller_true(client, monkeypatch):
    _live(monkeypatch, EvidenceSources(registry_record={"owner": "Controller"},
                                       ledger_verify={"ok": False, "reason": "broken"}))
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(),
                                   "agent_id": "agent-1", "sources": FORGED})
    body = r.json()
    row = _rows(body)["FC-L-01"]
    assert row["evidenced"] is False
    assert "caller-asserted" not in row["evidence_detail"] and "broken" in row["evidence_detail"]
    assert ("FC-L-01", "not-evidenced") in _gap_kinds(body)


def test_n1_an_empty_agent_id_requests_nothing(client, monkeypatch):
    calls = _live(monkeypatch, EvidenceSources())
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(), "agent_id": ""})
    assert r.status_code == 200, r.text
    assert calls == []
    assert r.json()["pack"]["evidence_status"] == "not-requested"
    assert EVIDENCE_UNKNOWN_HEADLINE not in r.json()["markdown"]


def test_n3_an_empty_body_without_agent_id_is_not_requested(client, monkeypatch):
    _live(monkeypatch, EvidenceSources())
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(), "sources": {}})
    assert r.json()["pack"]["evidence_status"] == "not-requested"


def test_full_outage_with_agent_id_is_unknown_not_no_gaps(client, monkeypatch):
    _live(monkeypatch, EvidenceSources())
    r = client.post("/pack", json={"signer": SIGNER, "manifest": resolved_manifest(), "agent_id": "agent-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack"]["evidence_status"] == "unknown"
    assert "- Evidence status: unknown" in body["markdown"]
    assert EVIDENCE_UNKNOWN_HEADLINE in body["markdown"]
    assert "No gaps recorded" not in body["markdown"]
    assert {"control_id": "FC-L-01", "kind": "not-checked", "detail": LEDGER_NOT_CHECKED_GAP} in body["pack"]["gaps"]


#: B1 (review of c66d9711): the outage is a property of the LIVE collection alone, whatever the caller's body holds
_OUTAGE_BODIES = [
    pytest.param({"sources": {}}, id="empty-sources-object"),
    pytest.param({"sources": {"ledger_verify": None}}, id="caller-object-with-no-verdict"),
    pytest.param({"sources": {"tokens": []}}, id="caller-object-no-negative-verdict"),
    pytest.param(None, id="duplicate-sources-key-last-is-empty"),
]


@pytest.mark.parametrize("extra", _OUTAGE_BODIES)
def test_full_outage_stays_unknown_whatever_the_caller_sources_hold(client, monkeypatch, extra):
    import json

    calls = _live(monkeypatch, EvidenceSources())  # collect_evidence answers nothing
    base = {"signer": SIGNER, "manifest": resolved_manifest(), "agent_id": "agent-1"}
    if extra is None:
        # a duplicate ``sources`` key: the parser keeps the last value ({}); sent as raw JSON text
        raw = json.dumps(base)[:-1] + ', "sources": ' + json.dumps(FORGED) + ', "sources": {}}'
        r = client.post("/pack", content=raw, headers={"content-type": "application/json"})
    else:
        r = client.post("/pack", json={**base, **extra})
    assert r.status_code == 200, r.text
    body = r.json()
    assert calls == ["agent-1"]
    assert body["pack"]["evidence_status"] == "unknown"
    assert "- Evidence status: unknown" in body["markdown"]
    assert EVIDENCE_UNKNOWN_HEADLINE in body["markdown"]
    assert "No gaps recorded" not in body["markdown"]
    assert {"control_id": "FC-L-01", "kind": "not-checked", "detail": LEDGER_NOT_CHECKED_GAP} in body["pack"]["gaps"]


def test_caller_asserted_gap_label_text_is_pinned():
    from compliance_crosswalk.evidence_pack import PACK_GAP_LABELS

    assert PACK_GAP_LABELS["caller-asserted"] == "caller-asserted, not verified"
    md, _ = generate_pack(
        resolved_manifest(), signer=SIGNER, stale_store=_NoStale(), caller_sources=EvidenceSources(**FORGED)
    )
    assert "- FC-L-01 — caller-asserted, not verified: " + CALLER_ASSERTED_GAP in md


def test_full_outage_is_unknown_on_the_cli_path_too():
    # generate_pack is what ``crosswalk pack --agent-id`` calls with collect_evidence's (all-None) result
    md, payload = generate_pack(
        resolved_manifest(), signer=SIGNER, stale_store=_NoStale(),
        agent_id="agent-1", sources=EvidenceSources(),
    )
    assert payload["evidence_status"] == "unknown"
    assert "No gaps recorded" not in md


def test_a_healthy_collected_run_can_still_say_no_gaps():
    # the unknown/caller-asserted rules do not turn a genuinely clean run into a gap list
    live = EvidenceSources(**FORGED)
    md, payload = generate_pack(resolved_manifest(), signer=SIGNER, stale_store=_NoStale(),
                                agent_id="agent-1", sources=live)
    assert payload["evidence_status"] == "collected"
    assert not [g for g in payload["gaps"] if g["kind"] in ("caller-asserted", "not-checked")]


def test_manifest_only_pack_is_not_requested_not_unknown():
    md, payload = generate_pack(resolved_manifest(), signer=SIGNER, stale_store=_NoStale())
    assert payload["evidence_status"] == "not-requested"
    assert EVIDENCE_UNKNOWN_HEADLINE not in md


class _NoStale:
    def active(self):
        return []

    def status(self):
        return {"active": [], "corpus_version": "test"}
