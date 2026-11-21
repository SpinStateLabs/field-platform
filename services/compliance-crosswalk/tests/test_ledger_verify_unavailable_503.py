"""A busy or unreachable ledger is 'unavailable', never a failed FC-L-01 control.

collect_evidence() turns a /verify that is 503 (busy) or unreachable into None; engine used to
read None as a broken chain: 'ledger verify failed: None', evidenced False.

Any OTHER answer (401/403 bad shared secret, 404, 500, an unparseable 200) is a ledger that
answered and was NOT verified: evidenced False (a gap) with the HTTP status, mirroring
attestation-reporter ('answered HTTP n, chain NOT verified; investigate'). A /verify body that
lacks a true ``ok`` (empty, no ``ok``, ``"false"``) is a failed control, never unavailable/pass.
"""

from __future__ import annotations

import httpx
import pytest

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


# --- review conditions (PR 1093, R-PR1093-99167f6) ---------------------------------------


@pytest.mark.parametrize(
    "body",
    [{}, {"length": 3}, {"reason": "x"}, {"ok": None}, {"ok": "false"}, {"ok": "true"}, {"ok": 1}],
)
def test_verify_body_without_a_true_ok_is_failed_never_unavailable_or_pass(body):
    _, c = _fc_l01(EvidenceSources(ledger_verify=body))
    assert c.evidenced is False
    assert "None" not in c.evidence_detail
    assert "unavailable" not in c.evidence_detail


def _collect(monkeypatch, verify):
    """collect_evidence offline; verify is a status int, 'non-json-200', or an Exception to raise."""
    import field_core.clients as clients

    class _Registry:
        def get_agent(self, agent_id):
            return {"agent_id": agent_id, "owner": "x"}

    monkeypatch.setattr(clients, "RegistryClient", _Registry)

    def fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        if url.endswith("/verify"):
            if isinstance(verify, Exception):
                raise verify
            if verify == "non-json-200":
                return httpx.Response(200, content=b"<html>proxy</html>", request=req)
            return httpx.Response(verify, json={"detail": "x"}, request=req)
        return httpx.Response(200, json={} if "/caps/" in url else [], request=req)

    monkeypatch.setattr(httpx, "get", fake_get)
    return api_module.collect_evidence("a")


@pytest.mark.parametrize("status", [401, 403, 404, 500, 502])
def test_non_503_answer_is_failed_with_status_not_unavailable(monkeypatch, status):
    # Decision: only 503 (busy) and transport errors are 'unavailable; retry'. A 401/403 is a
    # misconfigured/rotated shared secret and a 500 a ledger fault: they must stay a gap.
    _, c = _fc_l01(_collect(monkeypatch, status))
    assert c.evidenced is False
    assert f"HTTP {status}" in c.evidence_detail
    assert "NOT verified" in c.evidence_detail and "investigate" in c.evidence_detail
    assert "busy" not in c.evidence_detail and "None" not in c.evidence_detail


def test_unparseable_200_is_failed_not_unavailable(monkeypatch):
    _, c = _fc_l01(_collect(monkeypatch, "non-json-200"))
    assert c.evidenced is False and "HTTP 200" in c.evidence_detail


def test_503_and_transport_error_stay_unavailable(monkeypatch):
    for verify in (503, httpx.ConnectError("refused"), httpx.ReadTimeout("slow")):
        s = _collect(monkeypatch, verify)
        assert s.ledger_verify is None
        assert _fc_l01(s)[1].evidenced is None


def test_collected_200_ok_true_still_passes_end_to_end(monkeypatch):
    import field_core.clients as clients

    class _Registry:
        def get_agent(self, agent_id):
            return {"owner": "x"}

    monkeypatch.setattr(clients, "RegistryClient", _Registry)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200,
            json={"ok": True} if url.endswith("/verify") else ({} if "/caps/" in url else []),
            request=httpx.Request("GET", url),
        ),
    )
    assert _fc_l01(api_module.collect_evidence("a"))[1].evidenced is True


# --- evidence pack: the 'no gap' claim -----------------------------------------------------


class _NoStale:
    corpus_version = "corpus-test"

    def active(self):
        return []

    def status(self):
        return {"corpus_version": "corpus-test"}


def _pack(sources):
    from compliance_crosswalk.evidence_pack import generate_pack

    return generate_pack(
        resolved_manifest(), signer="Test Signer 1", stale_store=_NoStale(), agent_id="a", sources=sources
    )


def _l01_gaps(payload):
    return [g for g in payload["gaps"] if g["control_id"] == "FC-L-01"]


def test_pack_unavailable_ledger_is_not_collected_with_no_gap():
    md, payload = _pack(EvidenceSources(registry_record={"owner": "x"}, ledger_verify=None))
    assert _l01_gaps(payload) == []
    row = next(c for c in payload["controls"] if c["control_id"] == "FC-L-01")
    assert row["evidenced"] is None
    line = next(ln for ln in md.splitlines() if ln.startswith("| FC-L-01 "))
    assert line.rstrip().endswith("| not-collected |")


def test_pack_failed_and_answered_not_verified_ledger_are_gaps():
    for body in ({"ok": False, "reason": "r"}, {}, {"http_status": 401}):
        _, payload = _pack(EvidenceSources(registry_record={"owner": "x"}, ledger_verify=body))
        gaps = _l01_gaps(payload)
        assert len(gaps) == 1 and gaps[0]["kind"] == "not-evidenced"


def test_pack_verified_ledger_has_no_gap_and_is_yes():
    md, payload = _pack(EvidenceSources(registry_record={"owner": "x"}, ledger_verify={"ok": True}))
    assert _l01_gaps(payload) == []
    line = next(ln for ln in md.splitlines() if ln.startswith("| FC-L-01 "))
    assert line.rstrip().endswith("| yes |")
