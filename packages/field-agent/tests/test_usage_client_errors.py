"""S9-4 (the part PR 372 leaves): UsageClient's transport-failure message carries the exception type only.

#372 already makes `report` and `spend` use `upstream_error` for a non-201/404 status, keeps the governor's body out of a 404, and
turns a bad 201 body into `UsageReportError`. It leaves `f"spend-governor unreachable — ... NOT metered: {exc}"`: the text of a
transport exception can carry the URL, a proxy or an address (the reason liveness.py already gives for its type-only message).
Both messages now say `spend-governor unreachable (<ExceptionType>) — ... NOT metered`; the original is not chained (`from None`),
so it cannot surface through __cause__ either. The other S9-4 cases are pinned here too, so this file stands on its own."""

import httpx
import pytest

from field_agent.usage import NoSpendCapError, UsageClient, UsageReportError

URL = "http://10.9.8.7:8006/usage/secret-host"
MARK = "UPSTREAM-BODY-MARKER-5521"


class Fake:
    def __init__(self, status=201, body=None, text=None, exc=None):
        self.status, self.body, self.text, self.exc = status, body, text, exc

    def post(self, url, **kw):
        if self.exc:
            raise self.exc
        content = (self.text or "").encode() if self.text is not None else __import__("json").dumps(self.body).encode()
        return httpx.Response(self.status, content=content, request=httpx.Request("POST", url))


def usage(fake):
    return UsageClient(client=fake, base_url="http://governor.invalid")


def call(verb, client):
    if verb == "report":
        return client.report("a1", model="claude-opus-4-8", input_tokens=1, output_tokens=1)
    return client.spend("a1", cents=1)


@pytest.mark.parametrize("verb", ["report", "spend"])
@pytest.mark.parametrize("exc", [httpx.ConnectError(f"connection refused to {URL}"), httpx.ReadTimeout(f"timed out {URL}"),
                                 ConnectionError(URL), OSError(f"proxy 192.0.2.7 {URL}")],
                         ids=["connect", "timeout", "connection", "oserror"])
def test_a_transport_failure_names_the_type_and_never_the_text(verb, exc):
    with pytest.raises(UsageReportError) as caught:
        call(verb, usage(Fake(exc=exc)))
    msg = str(caught.value)
    assert f"spend-governor unreachable ({type(exc).__name__})" in msg
    assert "NOT metered" in msg
    assert "10.9.8.7" not in msg and "192.0.2.7" not in msg and "secret-host" not in msg
    assert caught.value.__cause__ is None                      # the original (with its text) is not chained


@pytest.mark.parametrize("verb, what", [("report", "usage report"), ("spend", "spend report")])
def test_a_500_with_a_long_body_is_the_fixed_status_text(verb, what):
    with pytest.raises(UsageReportError) as caught:
        call(verb, usage(Fake(status=500, text=("x" * 5000) + MARK)))
    assert str(caught.value) == f"{what} returned 500"


@pytest.mark.parametrize("verb", ["report", "spend"])
@pytest.mark.parametrize("body", [{"detail": {"nested": MARK}}, {"detail": "no cap for a1 " + MARK}, {}], ids=["dict-detail", "str-detail", "empty"])
def test_a_404_is_no_spend_cap_and_never_relays_the_governors_text(verb, body):
    with pytest.raises(NoSpendCapError) as caught:
        call(verb, usage(Fake(status=404, body=body)))
    assert MARK not in str(caught.value) and "no spend cap" in str(caught.value)


@pytest.mark.parametrize("verb", ["report", "spend"])
@pytest.mark.parametrize("text", ["not json", "{}", "[]", "null", '{"x": "' + MARK + '"}'], ids=["not-json", "empty-object", "list", "null", "wrong-shape"])
def test_a_201_with_an_unusable_body_is_a_usage_report_error_saying_not_metered(verb, text):
    with pytest.raises(UsageReportError) as caught:
        call(verb, usage(Fake(status=201, text=text)))
    assert "NOT metered" in str(caught.value) and MARK not in str(caught.value)
