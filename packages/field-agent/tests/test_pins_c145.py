"""C-145 (reviewer R-17 F-R17-1/-2/-3): survivors pinned.

* the canary's `POST /halt` body guards (`_drain`): a chunked body, a non-positive or oversized
  Content-Length, the exact MAX_BODY_BYTES boundary (raw sockets, so the framing is ours);
* `x3_check` refuses a non-canary agent before any call, whatever its registry record says;
* the heartbeat-age boundary in `FieldAgent.check` and `.cross` (`>`, not `>=`);
* `FederationClient.request_body` argument checks, and the `x3-check` CLI's unset-URL refusal;
* the canary's request log line.
"""

from __future__ import annotations

import json
import socket
import threading
from types import SimpleNamespace

import pytest

from field_agent import agent as agent_mod
from field_agent import canary as canary_mod
from field_agent.agent import FieldAgent
from field_agent.canary import (CANARY_DOMAIN, MAX_BODY_BYTES, ORIGIN_HEADER, ORIGIN_VALUE,
                                CanaryAgent, CanaryState)
from field_agent.federation import FederationClient


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("FIELD_SHARED_SECRET", "FIELD_KILL_ENDPOINT_ALLOWLIST", "FIELD_KILLSWITCH_URL",
                 "FIELD_REGISTRY_URL", "FIELD_LEDGER_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def running():
    agent = CanaryAgent("canary-gb10", host="127.0.0.1", port=0, work_every=0.5)
    thread = threading.Thread(target=agent.serve_forever, daemon=True)
    thread.start()
    try:
        yield agent
    finally:
        agent.shutdown()
        thread.join(timeout=5)


def raw_post(port: int, headers: list[str], body: bytes = b"", *, read_timeout: float = 3.0):
    """Send one POST /halt with exactly these headers and body. Returns (status, closed, text):
    ``closed`` is True when the server closed the connection after answering (EOF), False when it
    kept the socket open (the read timed out)."""
    request = ("POST /halt HTTP/1.1\r\nHost: t\r\n" + "".join(h + "\r\n" for h in headers) + "\r\n"
               ).encode() + body
    with socket.create_connection(("127.0.0.1", port), timeout=read_timeout) as s:
        s.sendall(request)
        chunks = b""
        closed = False
        try:
            while True:
                data = s.recv(65536)
                if not data:
                    closed = True
                    break
                chunks += data
                if b"\r\n\r\n" in chunks and len(chunks.split(b"\r\n\r\n", 1)[1]) >= int(
                        next((l.split(b":")[1] for l in chunks.split(b"\r\n\r\n", 1)[0].split(b"\r\n")
                              if l.lower().startswith(b"content-length")), b"0")):
                    # the answer is complete; wait briefly for the server to close or not
                    s.settimeout(0.5)
        except (socket.timeout, TimeoutError):
            closed = False
    text = chunks.decode("utf-8", "replace")
    status = int(text.split(" ", 2)[1]) if text.startswith("HTTP/") else None
    return status, closed, text


ORIGIN = f"{ORIGIN_HEADER}: {ORIGIN_VALUE}"


def snapshot(agent):
    return agent.state.snapshot()


# --- F-R17-1: _drain ---------------------------------------------------------------------


def test_a_chunked_halt_is_answered_and_the_connection_is_closed(running):
    status, closed, text = raw_post(running.port, [ORIGIN, "Transfer-Encoding: chunked",
                                                "x-field-kill-reason: x3-chunky"],
                                 b"5\r\nhello\r\n0\r\n\r\n")
    assert status == 200 and closed is True                    # never left half-read, kept alive
    assert text.count("HTTP/1.") == 1, text                    # no second answer to the unread chunk
    assert snapshot(running)["nonce"] == "chunky"


def test_a_negative_content_length_does_not_block_the_handler(running):
    status, _, _ = raw_post(running.port, [ORIGIN, "Content-Length: -5", "x-field-kill-reason: x3-neg"],
                            read_timeout=2.0)
    assert status == 200 and snapshot(running)["nonce"] == "neg"


def test_a_non_numeric_content_length_is_treated_as_no_body(running):
    status, _, _ = raw_post(running.port, [ORIGIN, "Content-Length: abc", "x-field-kill-reason: x3-abc"])
    assert status == 200 and snapshot(running)["nonce"] == "abc"


def test_an_oversized_body_is_not_read_and_the_connection_is_closed(running):
    status, closed, _ = raw_post(
        running.port, [ORIGIN, f"Content-Length: {MAX_BODY_BYTES + 1}"],
        b'{"reason": "x3-toobig"}')                              # claims more than it sends
    assert status == 200 and closed is True
    assert snapshot(running)["nonce"] is None                    # the body was never parsed


def exact_body(size: int, reason: str) -> bytes:
    head = json.dumps({"reason": reason, "pad": ""})
    body = json.dumps({"reason": reason, "pad": "a" * (size - len(head))}).encode()
    assert len(body) == size
    return body


def test_a_body_of_exactly_the_maximum_is_read(running):
    body = exact_body(MAX_BODY_BYTES, "x3-edge")
    status, _, _ = raw_post(running.port, [ORIGIN, f"Content-Length: {MAX_BODY_BYTES}"], body)
    assert status == 200 and snapshot(running)["nonce"] == "edge"    # the reason came from the body


def test_a_body_one_below_the_maximum_is_read(running):
    body = exact_body(MAX_BODY_BYTES - 1, "x3-below")
    status, _, _ = raw_post(running.port, [ORIGIN, f"Content-Length: {MAX_BODY_BYTES - 1}"], body)
    assert status == 200 and snapshot(running)["nonce"] == "below"


def test_a_zero_length_body_is_no_body(running):
    status, _, _ = raw_post(running.port, [ORIGIN, "Content-Length: 0"])
    assert status == 200 and snapshot(running)["nonce"] is None and snapshot(running)["halted"] is True


# --- F-R17-3: the log line ---------------------------------------------------------------


def test_the_log_line_is_one_line_with_the_status_code_when_present(capsys):
    handler = canary_mod._handler_for(CanaryState("canary-gb10"))
    fake = SimpleNamespace(command="POST", path="/halt?x=1")
    handler.log_message(fake, '"%s" %s %s', "POST /halt HTTP/1.1", "200", "-")
    assert capsys.readouterr().out == "canary-agent POST /halt 200\n"
    handler.log_message(fake, '"%s"', "only one arg")                   # no code: no IndexError
    assert capsys.readouterr().out == "canary-agent POST /halt \n"
    handler.log_message(fake, "%s %s", "a", "b")                          # fmt not a request line
    assert capsys.readouterr().out == "canary-agent POST /halt \n"


# --- F-R17-2: x3_check -------------------------------------------------------------------


def test_x3_check_refuses_a_non_canary_before_any_call_even_with_a_canary_domain_record():
    calls = []

    def platform(method, url, body=None):
        calls.append((method, url))
        return 200, {"agent_id": "invoicing-agent", "domain": CANARY_DOMAIN, "status": "active"}

    out: list[str] = []
    code = canary_mod.x3_check(
        "invoicing-agent", killswitch_url="http://ks", registry_url="http://reg", ledger_url="http://led",
        canary_url="http://canary-agent:8090", platform=platform,
        canary=lambda *a, **k: pytest.fail("the canary must not be called"), out=out.append)
    assert code == 2 and "is not one of" in out[0] and out[0].startswith("refusing:")
    assert calls == []                                            # rule 7: refused before the registry


def test_x3_check_refuses_a_canary_whose_record_is_not_an_active_canary_domain_agent():
    def platform_with(rec):
        return lambda method, url, body=None: (200, rec)

    for rec in ({"agent_id": "canary-gb10", "domain": "finance", "status": "active"},
                {"agent_id": "canary-gb10", "domain": CANARY_DOMAIN, "status": "killed"},
                {"agent_id": "someone-else", "domain": CANARY_DOMAIN, "status": "active"}):
        out: list[str] = []
        code = canary_mod.x3_check(
            "canary-gb10", killswitch_url="http://ks", registry_url="http://reg", ledger_url="http://led",
            canary_url="http://canary-agent:8090", platform=platform_with(rec),
            canary=lambda *a, **k: pytest.fail("the canary must not be called"), out=out.append)
        assert code == 2 and "is not an active" in out[0], (rec, out)


def test_the_x3_check_cli_refuses_when_a_url_is_unset(capsys):
    code = canary_mod.main(["x3-check", "--agent", "canary-gb10"])
    out = capsys.readouterr().out
    assert code == 2 and out.startswith("refusing: FIELD_KILLSWITCH_URL, FIELD_REGISTRY_URL, FIELD_LEDGER_URL unset")


def test_the_x3_check_cli_names_only_the_unset_urls(monkeypatch, capsys):
    monkeypatch.setenv("FIELD_KILLSWITCH_URL", "http://ks")
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://led")
    assert canary_mod.main(["x3-check", "--agent", "canary-gb10"]) == 2
    assert capsys.readouterr().out.startswith("refusing: FIELD_REGISTRY_URL unset")


# --- F-R17-3: the heartbeat-age boundary --------------------------------------------------


class Down:
    def post(self, *a, **k):
        raise ConnectionError("down")

    get = post


def make_agent():
    agent = FieldAgent("invoicing-agent", sentinel_client=Down(), governor_client=Down(),
                       killswitch_client=Down(), federation_client=Down(),
                       federation_url="http://t", heartbeat_max_age=30.0)
    agent.alive_calls = 0

    def ensure_alive():
        agent.alive_calls += 1

    agent.ensure_alive = ensure_alive
    agent._sentinel = SimpleNamespace(check=lambda *a, **k: {"decision": "ALLOW"})
    agent._federation = SimpleNamespace(cross=lambda *a, **k: {"decision": "ALLOW"})
    return agent


def call(agent, which):
    if which == "check":
        return agent.check("draft invoices")
    return agent.cross("Borealis", "scope", "data", {"a": 1})


@pytest.mark.parametrize("which", ["check", "cross"])
@pytest.mark.parametrize(("elapsed", "refreshed"), [(29.999, False), (30.0, False), (30.001, True)])
def test_the_heartbeat_is_refreshed_only_when_older_than_the_max_age(monkeypatch, which, elapsed, refreshed):
    agent = make_agent()
    agent._alive_at = 100.0
    monkeypatch.setattr(agent_mod.time, "monotonic", lambda: 100.0 + elapsed)
    assert call(agent, which) == {"decision": "ALLOW"}
    assert agent.alive_calls == (1 if refreshed else 0)


@pytest.mark.parametrize("which", ["check", "cross"])
def test_a_never_checked_agent_refreshes_first(which):
    agent = make_agent()
    assert agent._alive_at is None
    call(agent, which)
    assert agent.alive_calls == 1


@pytest.mark.parametrize("which", ["check", "cross"])
def test_without_a_max_age_the_heartbeat_is_never_forced(which):
    agent = make_agent()
    agent._heartbeat_max_age = None
    call(agent, which)
    assert agent.alive_calls == 0


# --- F-R17-3: FederationClient.request_body ------------------------------------------------


MANIFEST = {"agent": {"name": "a"}}


def body(**kw):
    args = dict(agent_id="ours", counterparty_org="Borealis", scope="s", data_class="d", manifest=MANIFEST)
    args.update(kw)
    return FederationClient.request_body(**args)


@pytest.mark.parametrize("manifest", [["a"], "", 5, None, ("a",)])
def test_a_non_mapping_manifest_is_refused_before_any_request(manifest, tmp_path):
    if manifest == "":
        manifest = tmp_path / "missing.yaml"        # a path is loaded, never mistaken for a mapping
        with pytest.raises(Exception):
            body(manifest=manifest)
        return
    with pytest.raises(ValueError, match="manifest must be a mapping"):
        body(manifest=manifest)


@pytest.mark.parametrize("agent_id", [None, ""])
def test_an_outbound_crossing_needs_our_agent_id(agent_id):
    with pytest.raises(ValueError, match="needs our agent_id"):
        body(agent_id=agent_id)


def test_an_inbound_crossing_needs_the_counterparty_agent_id_and_a_good_direction():
    with pytest.raises(ValueError, match="needs counterparty_agent_id"):
        body(direction="inbound", agent_id=None)
    with pytest.raises(ValueError, match="direction must be"):
        body(direction="sideways")


def test_an_outbound_crossing_refuses_a_signature():
    with pytest.raises(ValueError, match="not signature-checked"):
        body(manifest_signature="sig")


def test_a_valid_outbound_body_names_the_agent_and_manifest():
    b = body()
    assert b["agent_id"] == "ours" and b["manifest"] == MANIFEST and b["direction"] == "outbound"
