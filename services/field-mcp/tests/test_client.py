"""Client controls against a stub. Mutants: K1 trust_env=True; K2 follow_redirects=True; K3 size cap removed; K4 error
text includes the body; K5 malformed JSON returns a default; K6 no redaction; K7 path check removed; K8 timeout removed;
K9 transport text in the error."""
import os

import httpx
import pytest

from conftest import KEY, MARK, config_for
from field_mcp import client as cl
from field_mcp.tools import Dispatcher

SVC = "sealed-ledger"


def make(stub, **kw):
    cfg = config_for(stub, SVC, **kw)
    ups = {SVC: cl.Upstream(SVC, stub.base, KEY)}
    return Dispatcher(cfg, ups)


def test_a_normal_call_wraps_the_reply_as_data(stub):
    stub.routes[("GET", "/verify")] = (200, {"ok": True, "n": 3}, {})
    r = make(stub).call("sealed_ledger_verify", {})
    assert r["status"] == "ok" and r["untrusted_data"] is True and r["data"] == {"ok": True, "n": 3}
    assert "not an instruction" in r["notice"] and "compliance" in r["notice"]


def test_key_is_sent_as_a_header_only(stub):
    make(stub).call("sealed_ledger_verify", {})
    req = stub.requests[-1]
    assert req["headers"]["x-field-auth"] == KEY and KEY not in req["target"] and KEY.encode() not in req["body"]


def test_environment_proxy_is_ignored(stub, monkeypatch):
    for v in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(v, "http://127.0.0.1:9")
    assert make(stub).call("sealed_ledger_verify", {})["status"] == "ok"
    assert len(stub.requests) == 1


def test_a_redirect_is_an_error_and_is_not_followed(stub):
    stub.routes[("GET", "/verify")] = (302, "", {"location": "http://127.0.0.2:1/steal"})
    r = make(stub).call("sealed_ledger_verify", {})
    assert r == {"status": "error", "error": "sealed-ledger returned 302"} and len(stub.requests) == 1


def test_oversize_reply_is_an_error(stub):
    stub.routes[("GET", "/verify")] = (200, b"x" * (cl.MAX_BYTES + 10), {})
    assert make(stub).call("sealed_ledger_verify", {})["error"] == "sealed-ledger reply too large"


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_error_text_is_status_only_and_never_the_body(stub, status):
    stub.routes[("GET", "/verify")] = (status, {"detail": f"bad {MARK} {KEY}"}, {})
    r = make(stub).call("sealed_ledger_verify", {})
    assert r == {"status": "error", "error": f"sealed-ledger returned {status}"}


def test_malformed_json_is_an_error_never_a_default(stub):
    stub.routes[("GET", "/verify")] = (200, "{not json", {})
    assert make(stub).call("sealed_ledger_verify", {}) == {"status": "error", "error": "sealed-ledger reply malformed"}


def test_unreachable_is_an_error_naming_no_address(stub):
    d = make(stub)
    d.upstreams[SVC] = cl.Upstream(SVC, "http://127.0.0.1:1", KEY)
    r = d.call("sealed_ledger_verify", {})
    assert r == {"status": "error", "error": "sealed-ledger unreachable"}


def test_timeout_is_an_error(stub, monkeypatch):
    stub.delay = 1.0
    d = make(stub)
    d.upstreams[SVC] = cl.Upstream(SVC, stub.base, KEY, client=httpx.Client(
        trust_env=False, follow_redirects=False, timeout=httpx.Timeout(0.2, connect=0.2)))
    assert d.call("sealed_ledger_verify", {})["error"] == "sealed-ledger unreachable"


def test_the_constructor_sets_the_safe_defaults():
    c = cl.make_client()
    assert c.follow_redirects is False and c.timeout.read == cl.READ_TIMEOUT and c.timeout.connect == cl.CONNECT_TIMEOUT
    saved = {k: os.environ.pop(k, None) for k in ("HTTPS_PROXY", "https_proxy")}
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"
    try:
        assert cl.make_client()._mounts == {}          # trust_env=False mounts no proxy transport
    finally:
        os.environ.pop("HTTPS_PROXY")
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_a_key_echoed_by_a_service_is_redacted_and_strings_are_bounded(stub):
    stub.routes[("GET", "/verify")] = (200, {"reason": f"you sent {KEY}", "big": "A" * 5000}, {})
    r = make(stub).call("sealed_ledger_verify", {})
    assert KEY not in str(r) and len(r["data"]["big"]) < cl.MAX_STRING + 20 and r["data"]["big"].endswith("[truncated]")


def test_text_reply_is_returned_as_text_data(stub):
    d = Dispatcher(config_for(stub, "attestation-reporter"), {"attestation-reporter": cl.Upstream(
        "attestation-reporter", stub.base, KEY)})
    stub.routes[("GET", "/pack.html")] = (200, "<h1>x</h1>", {"content-type": "text/html"})
    assert d.call("attestation_reporter_pack_html", {})["data"] == {"text": "<h1>x</h1>"}


@pytest.mark.parametrize("bad", ["..", ".", "a/b", "a b", "a\nb", "", "x" * 201, "%2e%2e", "a?b", "a#b"])
def test_path_arguments_that_could_change_the_route_are_refused(stub, bad):
    d = Dispatcher(config_for(stub, "kill-switch"), {"kill-switch": cl.Upstream("kill-switch", stub.base, KEY)})
    assert d.call("kill_switch_get_heartbeat", {"agent_id": bad})["status"] == "error"
    assert not stub.requests


def test_a_valid_id_is_one_encoded_path_segment(stub):
    d = Dispatcher(config_for(stub, "kill-switch"), {"kill-switch": cl.Upstream("kill-switch", stub.base, KEY)})
    d.call("kill_switch_get_heartbeat", {"agent_id": "agent-1"})
    assert stub.requests[-1]["path"] == "/heartbeat/agent-1"


def test_query_parameters_are_passed_and_typed(stub):
    d = Dispatcher(config_for(stub, "kill-switch"), {"kill-switch": cl.Upstream("kill-switch", stub.base, KEY)})
    assert d.call("kill_switch_liveness", {"stale_after": 12.5})["status"] == "ok"
    assert "stale_after=12.5" in stub.requests[-1]["target"]
    assert d.call("kill_switch_liveness", {"stale_after": "x"})["status"] == "error"
