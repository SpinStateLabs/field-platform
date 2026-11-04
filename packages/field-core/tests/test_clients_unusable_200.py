"""A 200/201 whose body is unusable is a failure, not a ValueError (scout S4-2).

``LedgerClient.events()`` already turned a non-JSON or non-list body into
``LedgerUnreachableError``. The other readers returned ``resp.json()`` bare, so a proxy answering
200 text/html escaped as ``ValueError`` (a 500 in kill-switch and delegation). Each reader now
raises the client's typed error with a fixed phrase, and the message never carries the body.
"""

from __future__ import annotations

import httpx
import pytest

from field_core.clients import (
    LedgerClient,
    LedgerUnreachableError,
    RegistryClient,
    RegistryUnreachableError,
)

LEAK = "SECRET-BODY-TEXT-9f3a"


def _client(status: int, body: str, ctype: str = "text/html"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers={"content-type": ctype})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _registry(status, body, ctype="text/html") -> RegistryClient:
    return RegistryClient(client=_client(status, body, ctype), base_url="http://registry.test")


def _ledger(status, body, ctype="text/html") -> LedgerClient:
    return LedgerClient(client=_client(status, body, ctype), base_url="http://ledger.test")


def _no_leak(exc: Exception) -> None:
    assert LEAK not in str(exc)


# --- RegistryClient ---------------------------------------------------------


def test_get_agent_html_200_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, f"<html>{LEAK}</html>").get_agent("a")
    _no_leak(e.value)


def test_get_agent_list_body_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, "[]", "application/json").get_agent("a")
    _no_leak(e.value)


def test_get_agent_dict_body_still_works():
    assert _registry(200, '{"agent_id": "a", "status": "active"}', "application/json").get_agent("a") == {
        "agent_id": "a", "status": "active"}


def test_list_agents_html_200_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, f"<html>{LEAK}</html>").list_agents()
    _no_leak(e.value)


def test_list_agents_dict_body_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, "{}", "application/json").list_agents()
    _no_leak(e.value)


def test_list_agents_list_of_non_dicts_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, f'["{LEAK}", 3]', "application/json").list_agents()
    _no_leak(e.value)


def test_list_agents_list_of_dicts_still_works():
    assert _registry(200, '[{"agent_id": "a"}]', "application/json").list_agents() == [{"agent_id": "a"}]
    assert _registry(200, "[]", "application/json").list_agents() == []


def test_set_status_html_200_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, f"<html>{LEAK}</html>").set_status("a", "killed")
    _no_leak(e.value)


def test_set_status_list_body_is_registry_unreachable():
    with pytest.raises(RegistryUnreachableError) as e:
        _registry(200, "[]", "application/json").set_status("a", "killed")
    _no_leak(e.value)


def test_set_status_dict_body_still_works():
    assert _registry(200, '{"status": "killed"}', "application/json").set_status("a", "killed") == {
        "status": "killed"}


# --- LedgerClient -----------------------------------------------------------


def test_append_201_with_text_body_is_ledger_unreachable():
    with pytest.raises(LedgerUnreachableError) as e:
        _ledger(201, f"ok {LEAK}", "text/plain").append("t", {})
    _no_leak(e.value)


def test_append_201_with_list_body_is_ledger_unreachable():
    with pytest.raises(LedgerUnreachableError) as e:
        _ledger(201, "[]", "application/json").append("t", {})
    _no_leak(e.value)


def test_append_201_with_dict_body_still_works():
    assert _ledger(201, '{"seq": 1}', "application/json").append("t", {}) == {"seq": 1}


def test_retention_check_html_200_is_ledger_unreachable():
    with pytest.raises(LedgerUnreachableError) as e:
        _ledger(200, f"<html>{LEAK}</html>").retention_check()
    _no_leak(e.value)


def test_retention_check_list_body_is_ledger_unreachable():
    with pytest.raises(LedgerUnreachableError) as e:
        _ledger(200, "[]", "application/json").retention_check()
    _no_leak(e.value)


def test_retention_check_dict_body_still_works():
    assert _ledger(200, '{"ok": true}', "application/json").retention_check() == {"ok": True}
