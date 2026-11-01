"""C-642 (reviewer C-584 F-C584-1): the field-agent SDK's own exceptions never carry an upstream reply body.

Sites: LivenessClient (heartbeat and checkin), UsageClient (report and spend, 500 and the 404 no-cap path),
FederationClient.cross. Each is driven against an upstream that answers with a made-up marker plus 5,000 characters.

DELIBERATE WORDING CHANGES (listed so a reviewer can judge each):
  heartbeat   "heartbeat returned 500 - liveness unknown, halting: <body>"      -> "heartbeat returned 500 - liveness unknown, halting"
  usage       "usage report returned 500: <body>"                              -> "usage report returned 500"
  spend       "spend report returned 500: <body>"                              -> "spend report returned 500"
  no cap      NoSpendCapError(<governor's detail or body>)                      -> "usage report returned 404: no spend cap configured for this agent"
  federation  "federation-broker answered HTTP 500 - ...failing closed: <300>" -> "federation-broker returned 500 - no crossing decision, failing closed"
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest

from field_agent.errors import HeartbeatUnreachable, NoSpendCapError, UsageReportError
from field_agent.federation import CrossingBlocked, FederationClient
from field_agent.liveness import LivenessClient
from field_agent.usage import UsageClient

from test_federation_sdk import COUNTERPARTY, DATA_CLASS, OUR_AGENT, SCOPE, Canned, our_manifest

MARK = "CANARY-8f31-zq"          # made up; stands in for a value an upstream echoes back
BIG = MARK + "x" * 5000


class Upstream:
    """Answers every request with a fixed status and a hostile body (a JSON detail, plain text, or both)."""

    def __init__(self, status: int, body: str = BIG, as_json: bool = False):
        content = json.dumps({"detail": body}).encode() if as_json else body.encode()
        self.status, self.content = status, content

    def _reply(self, verb, url):
        return httpx.Response(self.status, content=self.content, request=httpx.Request(verb, url))

    def get(self, url, **kw):
        return self._reply("GET", url)

    def post(self, url, **kw):
        return self._reply("POST", url)


def chain(exc):
    seen, todo = [], [exc]
    while todo:
        e = todo.pop()
        if e is None or any(e is x for x in seen):
            continue
        seen.append(e)
        todo += [e.__cause__, e.__context__]
    return seen


def assert_no_body(exc, caplog):
    for e in chain(exc):
        for text in (str(e), repr(e), repr(e.args), repr(getattr(e, "__dict__", {}))):
            assert MARK not in text and "x" * 200 not in text, (type(e).__name__, text[:120])
    info = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.INFO)
    assert MARK not in info and "x" * 200 not in info


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_a_heartbeat_failure_names_the_status_and_no_body(caplog, verb, as_json):
    client = LivenessClient(client=Upstream(500, as_json=as_json), base_url="http://kill.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(HeartbeatUnreachable) as exc:
        getattr(client, verb)("a")
    assert str(exc.value) == "heartbeat returned 500 — liveness unknown, halting"
    assert_no_body(exc.value, caplog)


@pytest.mark.parametrize("as_json", [False, True])
def test_a_usage_report_failure_names_the_status_and_no_body(caplog, as_json):
    client = UsageClient(client=Upstream(500, as_json=as_json), base_url="http://gov.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(UsageReportError) as exc:
        client.report("a", "claude-haiku-4-5", 10, 10)
    assert str(exc.value) == "usage report returned 500" and not isinstance(exc.value, NoSpendCapError)
    assert_no_body(exc.value, caplog)


@pytest.mark.parametrize("as_json", [False, True])
def test_a_spend_report_failure_names_the_status_and_no_body(caplog, as_json):
    client = UsageClient(client=Upstream(503, as_json=as_json), base_url="http://gov.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(UsageReportError) as exc:
        client.spend("a", cents=5)
    assert str(exc.value) == "spend report returned 503" and not isinstance(exc.value, NoSpendCapError)
    assert_no_body(exc.value, caplog)


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("call,what", [
    (lambda c: c.report("a", "claude-haiku-4-5", 10, 10), "usage report"),
    (lambda c: c.spend("a", cents=5), "spend report"),
])
def test_the_no_cap_404_is_still_no_spend_cap_and_carries_no_body(caplog, call, what, as_json):
    client = UsageClient(client=Upstream(404, as_json=as_json), base_url="http://gov.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(NoSpendCapError) as exc:
        call(client)
    assert str(exc.value) == f"{what} returned 404: no spend cap configured for this agent"
    assert_no_body(exc.value, caplog)


@pytest.mark.parametrize("status", [500, 503, 422])
def test_a_crossing_failure_names_the_status_and_no_body(caplog, status):
    client = FederationClient(client=Canned(status, BIG), base_url="http://broker.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(CrossingBlocked) as exc:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert str(exc.value) == f"federation-broker returned {status} — no crossing decision, failing closed"
    assert exc.value.verdict is None
    assert_no_body(exc.value, caplog)


# ---- C-729: the 200 paths and the federation BLOCK text ---------------------------------------------------------------

class Raw:
    """A 200 reply with an arbitrary body (bytes), for the shapes a hostile or broken upstream can send."""

    def __init__(self, content: bytes):
        self.content = content

    def _reply(self, verb, url):
        return httpx.Response(200, content=self.content, request=httpx.Request(verb, url))

    def get(self, url, **kw):
        return self._reply("GET", url)

    def post(self, url, **kw):
        return self._reply("POST", url)


BAD_200 = {
    "not json": (BIG).encode(),
    "wrong shape": json.dumps({"agent_id": BIG, "status": BIG, "killed": "not-a-bool"}).encode(),
    "wrong type": json.dumps([BIG]).encode(),
    "bad utf-8": b"\xff\xfe" + BIG.encode(),
}


@pytest.mark.parametrize("shape", sorted(BAD_200))
@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_a_200_with_an_unusable_body_is_the_sdk_type_and_carries_no_body(caplog, verb, shape):
    client = LivenessClient(client=Raw(BAD_200[shape]), base_url="http://kill.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(HeartbeatUnreachable) as exc:   # the fail-closed type, not a library error
        getattr(client, verb)("a")
    assert "unusable reply" in str(exc.value) and "halting" in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert_no_body(exc.value, caplog)


def test_a_non_json_200_from_the_broker_leaves_no_body_on_the_chain(caplog):
    client = FederationClient(client=Raw(BIG.encode()), base_url="http://broker.invalid")
    with caplog.at_level(logging.INFO), pytest.raises(CrossingBlocked) as exc:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert "returned no verdict" in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None
    assert_no_body(exc.value, caplog)


def test_a_block_verdict_message_is_bounded_and_escaped_and_the_verdict_stays_on_the_exception(caplog):
    verdict = {"decision": "BLOCK", "clause_id": "X.\nq\x00" + "c" * 5000, "reasons": ["first\nline\x00" + "r" * 5000]}
    client = FederationClient(client=Canned(200, verdict), base_url="http://broker.invalid")
    with pytest.raises(CrossingBlocked) as exc:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    msg = str(exc.value)
    assert msg.startswith("crossing BLOCK by X.") and len(msg) <= 303
    assert "\n" not in msg and "\x00" not in msg
    assert exc.value.verdict == verdict                # the whole explanation is still available to a caller who wants it


def test_a_short_block_verdict_reads_as_before():
    verdict = {"decision": "BLOCK", "clause_id": "F.2", "reasons": ["counterparty manifest unsigned"]}
    client = FederationClient(client=Canned(200, verdict), base_url="http://broker.invalid")
    with pytest.raises(CrossingBlocked) as exc:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert str(exc.value) == "crossing BLOCK by F.2: counterparty manifest unsigned"


# ---- C-785: the 201 success paths of usage and bootstrap -------------------------------------------------------------

import traceback

from field_agent import bootstrap
from field_agent.errors import BootstrapError

BAD_201 = {
    "not json": BIG.encode(),
    "wrong shape": json.dumps({"agent_id": BIG, "model": BIG, "state": BIG, "spent_cents": BIG}).encode(),
    "list": json.dumps([BIG]).encode(),
    "string": json.dumps(BIG).encode(),
    "bad utf-8": b"\xff\xfe" + BIG.encode(),
}


class Raw201:
    def __init__(self, content: bytes):
        self.content = content

    def post(self, url, **kw):
        return httpx.Response(201, content=self.content, request=httpx.Request("POST", url))


def assert_clean(exc, caplog):
    assert_no_body(exc, caplog)
    assert exc.__cause__ is None and exc.__context__ is None
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert MARK not in tb and "x" * 200 not in tb


SITES = {
    "usage report": (lambda c: UsageClient(client=c, base_url="http://gov.invalid").report("a", "m", 1, 1), UsageReportError),
    "spend report": (lambda c: UsageClient(client=c, base_url="http://gov.invalid").spend("a", cents=5), UsageReportError),
    "mint": (lambda c: bootstrap.mint("a", "me", ["draft"], ttl_seconds=60, client=c, delegation_url="http://d.invalid"),
             BootstrapError),
    "register": (lambda c: bootstrap.register("a", "n", "o", client=c, registry_url="http://r.invalid"), BootstrapError),
}


@pytest.mark.parametrize("shape", sorted(BAD_201))
@pytest.mark.parametrize("site", sorted(SITES))
def test_a_201_with_an_unusable_body_is_the_sdk_error_and_carries_no_body(caplog, site, shape):
    if site == "register" and shape == "wrong shape":
        pytest.skip("register requires a JSON object only; an object with odd field values is returned as is (stated in the PR)")
    call, sdk_error = SITES[site]
    with caplog.at_level(logging.INFO), pytest.raises(sdk_error) as exc:      # the SDK type, not a library error
        call(Raw201(BAD_201[shape]))
    assert "unusable reply" in str(exc.value)
    assert_clean(exc.value, caplog)


def test_register_returns_a_valid_201_record_unchanged():
    record = {"agent_id": "a", "status": "active"}
    assert bootstrap.register("a", "n", "o", client=Raw201(json.dumps(record).encode()),
                              registry_url="http://r.invalid") == record


@pytest.mark.parametrize("body,kind", [
    (BIG.encode(), "JSONDecodeError"),
    (json.dumps([BIG]).encode(), "not a JSON object"),
    (json.dumps(BIG).encode(), "not a JSON object"),
    (b"\xff\xfe" + BIG.encode(), "JSONDecodeError"),
])
def test_register_names_only_the_kind_of_failure(body, kind):
    """C-855 C2: the message is exactly the fixed phrase plus the kind; no library text, no chain."""
    with pytest.raises(BootstrapError) as exc:
        bootstrap.register("a", "n", "o", client=Raw201(body), registry_url="http://r.invalid")
    assert str(exc.value) == f"register returned an unusable reply ({kind})"
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_register_returns_an_object_as_received_without_validating_its_fields():
    """C-855 C1, stated and pinned: any JSON object is the registration (documented in register's docstring)."""
    odd = {"anything": "goes"}
    assert bootstrap.register("a", "n", "o", client=Raw201(json.dumps(odd).encode()), registry_url="http://r.invalid") == odd
