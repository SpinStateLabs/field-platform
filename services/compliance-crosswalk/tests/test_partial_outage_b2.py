"""B2: when one service does not answer, the report says it was not read. It never states "agent not in registry",
"no cap" or "0 token(s)" for data nothing read, and it never headlines "No gaps"."""
from __future__ import annotations

import httpx
import pytest

import field_core.clients as clients
from compliance_crosswalk import api as api_module
from compliance_crosswalk.engine import EvidenceSources, coverage_gaps, evaluate, render_markdown
from compliance_crosswalk.evidence_pack import generate_pack
from test_crosswalk import resolved_manifest

SIGNER = "Controller, Spin State Labs"
ALL = ["registry", "ledger events", "delegation", "spend governor"]
READERS = {"registry": {"FC-R-01", "FC-I-01"}, "ledger events": {"FC-E-01", "FC-E-03"},
           "delegation": {"FC-D-01"}, "spend governor": {"FC-E-02"}}
FINDINGS = ("agent not in registry", "no owner on record", "no cap in spend-governor", "0 delegation token(s)",
            "0 kill/drill event(s)")


class _NoStale:
    def active(self):
        return []

    def status(self):
        return {"active": [], "corpus_version": "test"}


def collect(monkeypatch, down=(), none=()):
    """Live collection against fakes: ``down`` sources do not answer, ``none`` sources answer that they have nothing."""

    class _Registry:
        def get_agent(self, agent_id):
            if "registry" in down:
                raise clients.RegistryUnreachableError("down")
            if "registry" in none:
                raise clients.AgentNotRegisteredError(agent_id)
            return {"owner": "x"}

    def fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        name = ("ledger verify" if url.endswith("/verify") else "ledger events" if "/events" in url
                else "delegation" if "/tokens" in url else "spend governor")
        if name in down:
            raise httpx.ConnectError("down", request=req)
        if name == "spend governor" and name in none:
            return httpx.Response(404, json={"detail": "no cap"}, request=req)
        if name == "ledger verify":
            return httpx.Response(200, json={"ok": True}, request=req)
        if name == "spend governor":
            return httpx.Response(200, json={"cap": 1}, request=req)
        if name in none:
            return httpx.Response(200, json=[], request=req)
        row = ({"event_type": "kill.drill.complete"} if name == "ledger events"
               else {"token_id": "t", "revoked": True})
        return httpx.Response(200, json=[row], request=req)

    monkeypatch.setattr(clients, "RegistryClient", _Registry)
    monkeypatch.setattr(httpx, "get", fake_get)
    return api_module.collect_evidence("a")


@pytest.mark.parametrize("source", ALL)
def test_a_source_that_does_not_answer_is_named_and_its_controls_are_not_checked(monkeypatch, source):
    sources = collect(monkeypatch, down={source})
    assert sources.not_answered == [source]
    report = evaluate(resolved_manifest(), agent_id="a", sources=sources)
    rows = {c.control_id: c for c in report.controls}
    gaps = {(g["control_id"], g["kind"]) for g in coverage_gaps(report)}
    for cid in READERS[source]:
        assert rows[cid].evidenced is None, cid
        assert rows[cid].evidence_detail == f"evidence not collected: {source} did not answer", cid
        assert (cid, "not-checked") in gaps, cid
    md = render_markdown(report)
    assert f"Evidence not collected from: {source}." in md and "No gaps recorded" not in md
    assert not [text for text in FINDINGS if text in md]


@pytest.mark.parametrize("source", ALL)
def test_the_pack_reads_partial_and_never_no_gaps(monkeypatch, source):
    sources = collect(monkeypatch, down={source})
    md, payload = generate_pack(resolved_manifest(), signer=SIGNER, stale_store=_NoStale(), agent_id="a",
                                sources=sources)
    assert payload["evidence_status"] == "partial" and payload["not_answered"] == [source]
    assert f"Evidence not collected from: {source}." in md and "No gaps recorded" not in md


def test_an_answer_of_none_is_still_a_finding(monkeypatch):
    sources = collect(monkeypatch, none={"registry", "spend governor", "delegation"})
    assert sources.not_answered == []
    rows = {c.control_id: c for c in evaluate(resolved_manifest(), agent_id="a", sources=sources).controls}
    assert rows["FC-R-01"].evidenced is False and rows["FC-R-01"].evidence_detail == "agent not in registry"
    assert rows["FC-E-02"].evidenced is False and rows["FC-D-01"].evidenced is False


def test_a_revocation_read_from_one_source_stands_when_the_other_is_down(monkeypatch):
    sources = collect(monkeypatch, down={"ledger events"})
    row = next(c for c in evaluate(resolved_manifest(), agent_id="a", sources=sources).controls
               if c.control_id == "FC-D-02")
    assert row.evidenced is True and row.evidence_detail.endswith("(ledger events did not answer)")
    sources = collect(monkeypatch, down={"delegation"}, none={"ledger events"})
    row = next(c for c in evaluate(resolved_manifest(), agent_id="a", sources=sources).controls
               if c.control_id == "FC-D-02")
    assert row.evidenced is None and row.evidence_detail == "evidence not collected: delegation did not answer"


def test_body_sources_cannot_fill_a_row_that_was_asked_and_not_answered(monkeypatch):
    live = collect(monkeypatch, down={"registry"})
    claim = EvidenceSources(registry_record={"owner": "Caller"})
    _, payload = generate_pack(resolved_manifest(), signer=SIGNER, stale_store=_NoStale(), agent_id="a",
                               sources=live, caller_sources=claim)
    row = next(c for c in payload["controls"] if c["control_id"] == "FC-R-01")
    assert row["evidence_detail"] == "evidence not collected: registry did not answer"
    assert ("FC-R-01", "not-checked") in {(g["control_id"], g["kind"]) for g in payload["gaps"]}


def test_a_full_outage_is_still_unknown(monkeypatch):
    class _Down:
        def get_agent(self, agent_id):
            raise clients.RegistryUnreachableError("down")

    def fail(url, **kwargs):
        raise httpx.ConnectError("down", request=httpx.Request("GET", url))

    monkeypatch.setattr(clients, "RegistryClient", _Down)
    monkeypatch.setattr(httpx, "get", fail)
    sources = api_module.collect_evidence("a")
    md, payload = generate_pack(resolved_manifest(), signer=SIGNER, stale_store=_NoStale(), agent_id="a",
                                sources=sources)
    assert payload["evidence_status"] == "unknown" and payload["not_answered"] == ALL
    assert "No gaps recorded" not in md


def test_an_unknown_source_name_is_refused():
    with pytest.raises(ValueError):
        EvidenceSources(not_answered=["anything else"])
