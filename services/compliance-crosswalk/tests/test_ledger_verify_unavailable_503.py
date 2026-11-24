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


@pytest.mark.parametrize("body", [[], [{"ok": True}], "ok", 7, None])
def test_non_object_200_is_a_gap_with_status_not_an_exception(monkeypatch, body):
    # Review N1: a 200 whose JSON is not an object (list, string, number, null) used to reach EvidenceSources
    # as-is and raise a pydantic ValidationError out of collect_evidence. It is an answered-not-verified gap.
    import field_core.clients as clients

    class _Registry:
        def get_agent(self, agent_id):
            return {"agent_id": agent_id, "owner": "x"}

    monkeypatch.setattr(clients, "RegistryClient", _Registry)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200,
            json=body if url.endswith("/verify") else ({} if "/caps/" in url else []),
            request=httpx.Request("GET", url),
        ),
    )
    _, c = _fc_l01(api_module.collect_evidence("a"))
    assert c.evidenced is False
    assert "HTTP 200" in c.evidence_detail and "NOT verified" in c.evidence_detail


def test_verify_request_carries_the_shared_secret_header(monkeypatch):
    # Review N3 (mutant survivor): /verify must be sent with auth_headers(); without it a secured ledger answers
    # 401 and the pack shows a gap. The secret is generated at runtime, never written to a file.
    import secrets

    import field_core.clients as clients
    from field_core.authn import ENV_VAR

    secret = secrets.token_hex(16)
    monkeypatch.setenv(ENV_VAR, secret)

    class _Registry:
        def get_agent(self, agent_id):
            return {"agent_id": agent_id, "owner": "x"}

    monkeypatch.setattr(clients, "RegistryClient", _Registry)
    seen = {}

    def fake_get(url, **kwargs):
        seen[url.rsplit("/", 1)[-1].split("?")[0]] = kwargs.get("headers") or {}
        body = {"ok": True} if url.endswith("/verify") else ({} if "/caps/" in url else [])
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    api_module.collect_evidence("a")
    assert seen["verify"].get("x-field-auth") == secret


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


def test_pack_unavailable_ledger_is_not_collected_and_a_not_checked_gap():
    """don.reviewer C1 (rebuild of PR 1093), flipped from the old no-gap pin (his mutant M8): not checked is not
    failed (evidenced stays None, no 'not-evidenced' gap), but it is a gap of its own kind, in the JSON and the
    Markdown alike."""
    from compliance_crosswalk.evidence_pack import LEDGER_NOT_CHECKED_GAP

    md, payload = _pack(EvidenceSources(registry_record={"owner": "x"}, ledger_verify=None))
    assert _l01_gaps(payload) == [{"control_id": "FC-L-01", "kind": "not-checked", "detail": LEDGER_NOT_CHECKED_GAP}]
    row = next(c for c in payload["controls"] if c["control_id"] == "FC-L-01")
    assert row["evidenced"] is None
    line = next(ln for ln in md.splitlines() if ln.startswith("| FC-L-01 "))
    assert line.rstrip().endswith("| not-collected |")
    assert f"- FC-L-01 — not checked: {LEDGER_NOT_CHECKED_GAP}" in md.splitlines()


_FULL = dict(
    registry_record={"agent_id": "a", "owner": "AP Team Lead"},
    ledger_event_types={"kill.drill.complete": 1, "delegation.revoke": 1},
    tokens=[{"token_id": "t", "revoked": True}],
    governor_cap={"agent_id": "a", "limit_cents": 50000},
)


def test_an_unanswered_verify_can_never_head_the_pack_no_gaps():
    """A provoked 503 on /verify must not read like a verified chain: with every other artifact the same, the
    unanswered run has exactly one more gap (FC-L-01 not-checked) and never the 'No gaps recorded' headline."""
    md_ok, ok = _pack(EvidenceSources(ledger_verify={"ok": True, "length": 10}, **_FULL))
    md_un, un = _pack(EvidenceSources(ledger_verify=None, **_FULL))
    assert ("No gaps recorded" in md_ok) == (ok["gaps"] == [])      # the headline follows the gaps list
    assert "No gaps recorded" not in md_un
    extra = [g for g in un["gaps"] if g not in ok["gaps"]]
    assert [(g["control_id"], g["kind"]) for g in extra] == [("FC-L-01", "not-checked")]
    assert [g for g in ok["gaps"] if g not in un["gaps"]] == []


def test_an_offline_pack_has_no_not_checked_gap():
    # nothing requested at all (manifest-only, no agent_id): FC-L-01 is "evidence not collected", not "not checked"
    from compliance_crosswalk.evidence_pack import generate_pack

    _, payload = generate_pack(resolved_manifest(), signer="Test Signer 1", stale_store=_NoStale())
    assert not [g for g in payload["gaps"] if g["kind"] == "not-checked"]
    assert payload["evidence_status"] == "not-requested"


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


# --- delta review R-PR1093-2b8be0c: N2 (TLS certificate failure is a gap) and the null nit ----------


def _tls_error(kind: str) -> Exception:
    import ssl

    if kind == "chain-cert-verify":
        # what httpx raises for a bad certificate: ConnectError with the ssl error as its cause
        err = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        err.__cause__ = ssl.SSLCertVerificationError(1, "certificate verify failed")
        return err
    if kind == "message-only":
        return httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    if kind == "chain-ssl-error":
        err = httpx.ConnectError("handshake failed")
        err.__cause__ = ssl.SSLError("[SSL: WRONG_VERSION_NUMBER] wrong version number")
        return err
    return ssl.SSLError("bare ssl error")  # kind == "bare-ssl"


@pytest.mark.parametrize("kind", ["chain-cert-verify", "message-only", "chain-ssl-error", "bare-ssl"])
def test_tls_failure_is_a_gap_not_unavailable(monkeypatch, kind):
    # A bad/expired/mismatched certificate is a standing misconfiguration (or an interposer); it does
    # not clear on retry, so it must be a gap, like a 401.
    s = _collect(monkeypatch, _tls_error(kind))
    _, c = _fc_l01(s)
    assert c.evidenced is False
    assert "ledger TLS failed" in c.evidence_detail
    assert "chain NOT verified" in c.evidence_detail and "investigate" in c.evidence_detail
    assert "retry" not in c.evidence_detail and "None" not in c.evidence_detail


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("connection refused"),
        httpx.ConnectTimeout("slow connect"),
        httpx.ReadTimeout("slow"),
        httpx.ReadError("reset"),
        httpx.RemoteProtocolError("peer closed"),
        OSError("network unreachable"),
    ],
)
def test_every_non_tls_transport_error_stays_unavailable(monkeypatch, exc):
    s = _collect(monkeypatch, exc)
    assert s.ledger_verify is None
    _, c = _fc_l01(s)
    assert c.evidenced is None
    assert "unavailable" in c.evidence_detail and "TLS" not in c.evidence_detail


def test_literal_json_null_200_is_a_gap(monkeypatch):
    # json=None sends an EMPTY body in httpx; a literal `null` body is its own case.
    import field_core.clients as clients

    class _Registry:
        def get_agent(self, agent_id):
            return {"agent_id": agent_id, "owner": "x"}

    monkeypatch.setattr(clients, "RegistryClient", _Registry)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200,
            content=b"null" if url.endswith("/verify") else (b"{}" if "/caps/" in url else b"[]"),
            request=httpx.Request("GET", url),
        ),
    )
    _, c = _fc_l01(api_module.collect_evidence("a"))
    assert c.evidenced is False and "HTTP 200" in c.evidence_detail


# --- delta review R-PR1093-de81144: walk both __cause__ and __context__, exact match, cycle guard ------


def test_ssl_error_only_in_context_is_a_gap(monkeypatch):
    import ssl

    err = httpx.ConnectError("handshake failed")
    err.__context__ = ssl.SSLError("[SSL: WRONG_VERSION_NUMBER] wrong version number")
    _, c = _fc_l01(_collect(monkeypatch, err))
    assert c.evidenced is False and "ledger TLS failed" in c.evidence_detail


def test_ssl_error_in_context_is_found_when_cause_is_a_non_ssl_oserror(monkeypatch):
    import ssl

    err = httpx.ConnectError("handshake failed")
    err.__cause__ = OSError("network unreachable")
    err.__context__ = ssl.SSLError("[SSL: WRONG_VERSION_NUMBER] wrong version number")
    _, c = _fc_l01(_collect(monkeypatch, err))
    assert c.evidenced is False and "ledger TLS failed" in c.evidence_detail


def test_certificate_word_without_the_verify_failure_marker_stays_unavailable(monkeypatch):
    err = httpx.ConnectError("could not load client certificate file")
    s = _collect(monkeypatch, err)
    assert s.ledger_verify is None
    _, c = _fc_l01(s)
    assert c.evidenced is None and "TLS" not in c.evidence_detail


def test_cyclic_cause_chain_without_ssl_terminates_and_is_unavailable(monkeypatch):
    a = httpx.ConnectError("a")
    b = OSError("b")
    a.__cause__ = b
    b.__cause__ = a
    b.__context__ = a
    a.__context__ = b
    s = _collect(monkeypatch, a)
    assert s.ledger_verify is None
    _, c = _fc_l01(s)
    assert c.evidenced is None


def test_ok_in_the_answer_takes_precedence_over_tls_failed():
    _, c = _fc_l01(EvidenceSources(ledger_verify={"ok": True, "tls_failed": True}))
    assert c.evidenced is True
    _, c = _fc_l01(EvidenceSources(ledger_verify={"ok": False, "tls_failed": True}))
    assert c.evidenced is False and "TLS" not in c.evidence_detail
