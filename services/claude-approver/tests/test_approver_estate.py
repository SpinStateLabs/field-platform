"""Per-agent estate routing (Don's P28 b): an agent-map entry may point its
FIELD calls at its own estate, with that estate's perimeter secret read from a
file per request."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, TOKEN, set_map, usage

from claude_approver.api import create_app

ESTATE_SECRET = "estate-secret-SENTINEL-7f3a9c"  # never a real value
LOCAL_SECRET = "local-perimeter-SENTINEL-1b2c"
FLY_AGENT = "agent_011fly"
FLY_FIELD = "git-post-agent"


def _two_agent_map(monkeypatch, tmp_path, *, secret: str | None = ESTATE_SECRET):
    secret_path = tmp_path / "fly-secret"
    if secret is not None:
        secret_path.write_text(f"  {secret}\n", encoding="utf-8")
    set_map(monkeypatch, {
        CONSOLE_AGENT: {"field_agent_id": FIELD_AGENT, "token_id": TOKEN},
        FLY_AGENT: {
            "field_agent_id": FLY_FIELD, "token_id": "tok_fly",
            "estate_base_url": "https://force-field-sandbox.fly.test/",
            "secret_file": str(secret_path),
        },
    })
    return secret_path


def _pending(console, sid, agent):
    console.add_session(sid, agent, use=usage(500, 50, 5))
    ev = console.ask(sid, "bash")
    console.idle(sid)
    return ev


@pytest.mark.expects_allow
def test_estate_agent_routes_to_its_base_with_the_file_header(
        console, field, make_approver, monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SHARED_SECRET", LOCAL_SECRET)
    _two_agent_map(monkeypatch, tmp_path)
    _pending(console, "sesn_fly", FLY_AGENT)
    _pending(console, "sesn_gb10", CONSOLE_AGENT)
    a = make_approver()
    a.tick()

    by_host: dict[str, list] = {}
    for r in field.requests:
        by_host.setdefault(r.url.host, []).append(r)
    fly = by_host["force-field-sandbox.fly.test"]
    assert sorted(r.url.path for r in fly) == sorted(
        ["/sentinel/check", f"/killswitch/heartbeat/{FLY_FIELD}", "/governor/usage"])
    assert all(r.url.scheme == "https" for r in fly)
    assert all(r.headers.get("x-field-auth") == ESTATE_SECRET for r in fly)

    # the env-default agent is untouched by the estate block: env URLs, env secret
    local = [r for r in field.requests if r.url.host != "force-field-sandbox.fly.test"]
    assert sorted(str(r.url) for r in local) == sorted([
        "http://sentinel.test:8004/check",
        f"http://killswitch.test:8005/heartbeat/{FIELD_AGENT}",
        "http://governor.test:8006/usage",
    ])
    assert all(r.headers.get("x-field-auth") == LOCAL_SECRET for r in local)
    assert [c["result"] for c in console.confirmations()] == ["allow", "allow"]


@pytest.mark.parametrize("secret", [None, "   \n"], ids=["missing", "blank"])
def test_unreadable_estate_secret_denies(console, field, make_approver, monkeypatch, tmp_path, secret):
    _two_agent_map(monkeypatch, tmp_path, secret=secret)
    if secret is not None:
        (tmp_path / "fly-secret").write_text(secret, encoding="utf-8")
    ev = _pending(console, "sesn_fly", FLY_AGENT)
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations("sesn_fly")
    assert conf == {"type": "user.tool_confirmation", "tool_use_id": ev.id, "result": "deny",
                    "deny_message": "claude-approver: estate secret unreadable"}
    assert [r for r in field.requests if "/check" in r.url.path] == []
    assert a.stats()["denied"]["config_error"] == 1
    assert a.stats()["usage_failures"] == 1  # usage is not posted without the header


def test_secret_rotation_is_read_per_request(console, field, make_approver, monkeypatch, tmp_path):
    path = _two_agent_map(monkeypatch, tmp_path)
    _pending(console, "sesn_fly", FLY_AGENT)
    a = make_approver()
    a.tick()
    path.write_text("rotated-SENTINEL-value", encoding="utf-8")
    console.add_event("sesn_fly", "session.status_running")
    console.ask("sesn_fly", "edit")
    console.idle("sesn_fly")
    a.tick()
    checks = [r for r in field.requests if r.url.path == "/sentinel/check"]
    assert [r.headers["x-field-auth"] for r in checks] == [ESTATE_SECRET, "rotated-SENTINEL-value"]


def test_estate_without_secret_file_sends_no_perimeter_header(
        console, field, make_approver, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", LOCAL_SECRET)
    set_map(monkeypatch, {FLY_AGENT: {"field_agent_id": FLY_FIELD,
                                      "estate_base_url": "http://other-estate.test:8080"}})
    _pending(console, "sesn_fly", FLY_AGENT)
    make_approver().tick()
    (check,) = [r for r in field.requests if r.url.path.endswith("/check")]
    assert str(check.url) == "http://other-estate.test:8080/sentinel/check"
    assert "x-field-auth" not in check.headers  # the local secret never goes to another estate


def test_bad_estate_url_makes_the_entry_unusable(console, field, make_approver, monkeypatch):
    set_map(monkeypatch, {FLY_AGENT: {"field_agent_id": FLY_FIELD,
                                      "estate_base_url": "file:///etc/passwd"}})
    _pending(console, "sesn_fly", FLY_AGENT)
    a = make_approver()
    a.tick()
    (conf,) = console.confirmations("sesn_fly")
    assert conf["deny_message"] == "claude-approver: estate_base_url is not an http(s) URL"
    assert field.requests == []


def test_estate_secret_never_appears_in_any_response(console, field, make_approver, monkeypatch, tmp_path):
    _two_agent_map(monkeypatch, tmp_path)
    _pending(console, "sesn_fly", FLY_AGENT)
    field.sentinel = lambda r: field.verdict("BLOCK", "D.scope", ["nope"])
    a = make_approver()
    a.tick()
    client = TestClient(create_app(a))
    bodies = [
        client.get("/health").text,
        client.get("/stats").text,
        client.post(f"/halt/{FLY_FIELD}").text,
        client.post(f"/halt/{FLY_FIELD}", headers={"x-field-kill-origin": "kill-switch"}).text,
        client.post("/halt/nobody", headers={"x-field-kill-origin": "kill-switch"}).text,
    ]
    for body in bodies:
        assert ESTATE_SECRET not in body
    assert ESTATE_SECRET not in str(console.calls)
