"""collect_evidence builds URLs from the agent id and indexes whatever the services
answer (scout S-B5). The id is now percent-encoded (one path segment / one query value,
never a second parameter or a fragment) and a reply of the wrong shape is "not
collected" (None) instead of an exception that becomes a 500 on POST /pack."""
from __future__ import annotations

from urllib.parse import quote

import pytest

from compliance_crosswalk.api import collect_evidence

TRICKY = ["a&x=1", "a#frag", "a/../b", "a%2Fb", "a b", "a?x=1", "a;b", "ünï"]


class _Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


@pytest.fixture
def served(monkeypatch):
    """Patch httpx.get and the registry client; returns (urls, set_reply)."""
    import field_core.clients as clients
    import httpx

    urls: list[str] = []
    replies: dict[str, object] = {}

    def fake_get(url, **kw):
        urls.append(url)
        for key, body in replies.items():
            if key in url:
                return _Resp(body)
        return _Resp(None, 404)

    class _Reg:
        def get_agent(self, agent_id):
            return {"agent_id": "stub"}

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(clients, "RegistryClient", _Reg)
    for v in ("FIELD_LEDGER_URL", "FIELD_DELEGATION_URL", "FIELD_GOVERNOR_URL"):
        monkeypatch.delenv(v, raising=False)
    return urls, replies


@pytest.mark.parametrize("agent_id", TRICKY)
def test_the_id_is_one_encoded_segment_or_value_in_every_url(served, agent_id):
    urls, _ = served
    collect_evidence(agent_id)
    q = quote(agent_id, safe="")
    events = next(u for u in urls if "/events" in u)
    tokens = next(u for u in urls if "/tokens" in u)
    caps = next(u for u in urls if "/caps/" in u)
    assert events.endswith(f"/events?agent_id={q}") and events.count("?") == 1
    assert tokens.endswith(f"/tokens?agent_id={q}") and tokens.count("?") == 1
    assert caps.endswith(f"/caps/{q}") and "?" not in caps and "#" not in caps


def test_a_plain_slug_is_unchanged_in_the_urls(served):
    urls, _ = served
    collect_evidence("invoicing-agent")
    assert any(u.endswith("/events?agent_id=invoicing-agent") for u in urls)
    assert any(u.endswith("/caps/invoicing-agent") for u in urls)


def test_well_formed_replies_are_collected(served):
    _, replies = served
    replies["/events"] = [{"event_type": "a"}, {"event_type": "a"}, {"event_type": "b"}]
    replies["/verify"] = {"ok": True}
    replies["/tokens"] = [{"token_id": "t"}]
    replies["/caps/"] = {"limit": 1}
    ev = collect_evidence("x")
    assert ev.ledger_event_types == {"a": 2, "b": 1}
    assert ev.ledger_verify == {"ok": True} and ev.tokens == [{"token_id": "t"}]
    assert ev.governor_cap == {"limit": 1}


@pytest.mark.parametrize("bad", [{"detail": "x"}, "text", 5, [1, 2], [None], [{"no_type": 1}], [{"event_type": 3}]])
def test_a_wrong_shaped_events_reply_is_not_collected_not_a_crash(served, bad):
    _, replies = served
    replies["/events"] = bad
    assert collect_evidence("x").ledger_event_types is None


def test_non_dict_event_entries_are_skipped_but_good_ones_count(served):
    _, replies = served
    replies["/events"] = [1, None, {"event_type": "ok"}, {"x": 1}, {"event_type": ["unhashable"]}]
    assert collect_evidence("x").ledger_event_types == {"ok": 1}


@pytest.mark.parametrize("bad", [{"a": 1}, "text", 5, [1], [None]])
def test_a_wrong_shaped_tokens_reply_is_dropped_not_a_validation_error(served, bad):
    _, replies = served
    replies["/tokens"] = bad
    assert collect_evidence("x").tokens is None


@pytest.mark.parametrize("key,field", [("/verify", "ledger_verify"), ("/caps/", "governor_cap")])
@pytest.mark.parametrize("bad", [[1], "text", 5])
def test_a_wrong_shaped_dict_reply_is_dropped(served, key, field, bad):
    _, replies = served
    replies[key] = bad
    assert getattr(collect_evidence("x"), field) is None
