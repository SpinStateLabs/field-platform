"""S9-6 (the part PR 372 leaves): `FederationClient.cross`'s unreachable message names the exception type only.

#372 already keeps the broker's response body out of the non-200 message (`upstream_error`: status only), makes the "no verdict"
message type-only, and bounds and escapes the BLOCK message to one line of 300 characters while `.verdict` holds the whole object.
It leaves `f"{UNREACHABLE_REASON} ({type(exc).__name__}: {exc})"`: a transport exception's text can carry the URL, a proxy or an address
(the reason liveness.py gives for its type-only message). The message is now `UNREACHABLE_REASON (<ExceptionType>)` and the
original is not chained (`from None`). The other S9-6 cases are pinned too, so this file stands on its own."""

import httpx
import pytest

from field_agent.federation import UNREACHABLE_REASON, CrossingBlocked, FederationClient

from test_federation_sdk import COUNTERPARTY, DATA_CLASS, OUR_AGENT, SCOPE, Canned, our_manifest

URL = "http://10.9.8.7:8010/crossing/secret-host"
MARK = "UPSTREAM-BODY-MARKER-7714"


class Raises:
    def __init__(self, exc):
        self.exc = exc

    def post(self, *a, **k):
        raise self.exc


def cross(client):
    return FederationClient(client=client, base_url="http://t").cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())


@pytest.mark.parametrize("exc", [httpx.ConnectError(f"refused {URL}"), httpx.ReadTimeout(f"timed out {URL}"),
                                 ConnectionError(URL), OSError(f"proxy 192.0.2.7 {URL}")],
                         ids=["connect", "timeout", "connection", "oserror"])
def test_a_transport_error_names_the_type_and_never_the_text(exc):
    with pytest.raises(CrossingBlocked) as caught:
        cross(Raises(exc))
    msg = str(caught.value)
    assert msg == f"{UNREACHABLE_REASON} ({type(exc).__name__})"
    assert "10.9.8.7" not in msg and "192.0.2.7" not in msg and "secret-host" not in msg
    assert caught.value.verdict is None and caught.value.clause_id is None
    assert caught.value.__cause__ is None                      # the original text is not reachable through the chain


def test_the_unreachable_prefix_is_unchanged():
    with pytest.raises(CrossingBlocked) as caught:
        cross(Raises(ConnectionError("x")))
    assert str(caught.value).startswith(UNREACHABLE_REASON)


@pytest.mark.parametrize("status", [400, 401, 500, 503])
def test_a_non_200_never_carries_the_broker_body(status):
    with pytest.raises(CrossingBlocked) as caught:
        cross(Canned(status, {"detail": ("x" * 5000) + MARK}))
    assert MARK not in str(caught.value) and str(status) in str(caught.value)


@pytest.mark.parametrize("decision", ["X" * 100_000, {"a": "b" * 5000}, ["x"] * 1000, 7], ids=["long-str", "dict", "list", "int"])
def test_an_odd_decision_keeps_the_message_bounded_and_the_verdict_whole(decision):
    body = {"decision": decision, "agent_id": "x", "action": SCOPE, "clause_id": "C" * 100_000, "reasons": ["r" * 5000]}
    with pytest.raises(CrossingBlocked) as caught:
        cross(Canned(200, body))
    assert len(str(caught.value)) < 400 and "\n" not in str(caught.value)
    assert caught.value.verdict == body


def test_allow_is_untouched():
    body = {"decision": "ALLOW", "agent_id": "x", "action": SCOPE, "reasons": []}
    assert cross(Canned(200, body)) == body
