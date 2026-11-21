"""A busy or unreachable ledger is 'unavailable', never a failed FC-L-01 control.

collect_evidence() turns a non-200 /verify (503 busy, refused, unreachable) into None; engine
used to read None as a broken chain: 'ledger verify failed: None', evidenced False.
"""

from __future__ import annotations

import httpx

from compliance_crosswalk import api as api_module
from compliance_crosswalk.engine import EvidenceSources, evaluate
from test_crosswalk import resolved_manifest


def _fc_l01(sources: EvidenceSources):
    report = evaluate(resolved_manifest(), agent_id="a", sources=sources)
    return report, next(c for c in report.controls if c.control_id == "FC-L-01")


def test_missing_verify_result_is_unavailable_not_failed():
    # other artifacts were collected, only the ledger /verify answer is missing
    report, c = _fc_l01(EvidenceSources(registry_record={"owner": "x"}, ledger_verify=None))
    assert c.evidenced is None
    assert "None" not in c.evidence_detail
    assert "unavailable" in c.evidence_detail
    assert "not verified" in c.evidence_detail
    assert "failed" not in c.evidence_detail
    assert not any(x.control_id == "FC-L-01" and x.evidenced is False for x in report.controls)


def test_unavailable_ledger_does_not_count_as_evidenced():
    r_un, c = _fc_l01(EvidenceSources(registry_record={"owner": "x"}))
    r_ok, ok = _fc_l01(EvidenceSources(registry_record={"owner": "x"}, ledger_verify={"ok": True}))
    assert ok.evidenced is True and c.evidenced is None
    assert r_ok.evidenced_count == r_un.evidenced_count + 1


def test_real_broken_chain_still_fails():
    _, c = _fc_l01(EvidenceSources(ledger_verify={"ok": False, "reason": "hash mismatch at index 2"}))
    assert c.evidenced is False
    assert "ledger verify failed: hash mismatch at index 2" in c.evidence_detail


def test_verified_chain_still_passes():
    _, c = _fc_l01(EvidenceSources(ledger_verify={"ok": True, "length": 3}))
    assert c.evidenced is True and c.evidence_detail == "ledger chain verified"


def test_collect_evidence_503_reads_unavailable_end_to_end(monkeypatch):
    """Offline: httpx.get is faked; /verify answers 503, everything else 200."""
    import field_core.clients as clients

    class _Registry:
        def get_agent(self, agent_id):
            return {"agent_id": agent_id, "owner": "x"}

    monkeypatch.setattr(clients, "RegistryClient", _Registry)

    def fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        if url.endswith("/verify"):
            return httpx.Response(503, json={"detail": "busy"}, request=req)
        return httpx.Response(200, json={} if "/caps/" in url else [], request=req)

    monkeypatch.setattr(httpx, "get", fake_get)
    sources = api_module.collect_evidence("a")
    assert sources.ledger_verify is None
    _, c = _fc_l01(sources)
    assert c.evidenced is None
    assert "None" not in c.evidence_detail and "unavailable" in c.evidence_detail
