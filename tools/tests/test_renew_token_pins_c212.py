"""renew_token test pins (C-212, reviewer C-195): one refusal per token-record field, the renewal-window
boundaries at exactly 0 and exactly renew_within_days, the operator header on the mint and the revoke
only, and the escaped form of a secret holding a quote or a backslash. In-process, no estate; every
value is a test constant."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import renew_token  # noqa: E402

NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
TOKEN_ID = "a1b2c3d4-0000-4000-8000-000000000001"
DAY = renew_token.DAY


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def good(**over) -> dict:
    tok = {"token_id": TOKEN_ID, "agent_id": "canary-gb10", "granted_by": "Controller",
           "scope": ["read", "write"], "issued_at": iso(NOW - timedelta(days=1)),
           "expires_at": iso(NOW + timedelta(days=10)), "revoked": False}
    tok.update(over)
    return tok


# --- the token record: one bad value per field is refused, and names the field -----------------------


def test_a_well_formed_record_has_no_problem():
    assert renew_token.token_problem(good()) is None


@pytest.mark.parametrize("bad", [None, "x", [], 5])
def test_a_record_that_is_not_an_object_is_refused(bad):
    assert renew_token.token_problem(bad) == "not an object"


@pytest.mark.parametrize("field, values, named", [
    ("token_id", [None, "", "not-a-uuid", 7, TOKEN_ID.upper(), TOKEN_ID + "0", " " + TOKEN_ID], "token_id"),
    ("agent_id", [None, "", 5, ["a"]], "agent_id"),
    ("granted_by", [None, "", 5, ["Controller"]], "granted_by"),
    ("scope", [None, [], "read", [""], [1], ["read", ""], {"read": 1}], "scope"),
    ("issued_at", [None, "", "  ", "yesterday", 5], "issued_at/expires_at"),
    ("expires_at", [None, "", "  ", "tomorrow", 5], "issued_at/expires_at"),
    ("revoked", [None, "false", "true", 0, 1, []], "revoked"),
])
def test_each_bad_field_value_is_refused_and_named(field, values, named):
    for value in values:
        assert renew_token.token_problem(good(**{field: value})) == named, (field, value)


@pytest.mark.parametrize("field", ["token_id", "agent_id", "granted_by", "scope", "issued_at", "expires_at", "revoked"])
def test_a_missing_field_is_refused(field):
    tok = good()
    del tok[field]
    assert renew_token.token_problem(tok) is not None, field


def _renewal(tmp_path, *extra):
    args = renew_token.parse(["--agent", "canary-gb10", "--base", "http://127.0.0.1:9",
                              "--env-file", str(tmp_path / "s.env"), "--env-key", "K",
                              "--state-dir", str(tmp_path / "st"), *extra])
    return renew_token.Renewal(args, None)


@pytest.mark.parametrize("over, named", [
    ({"scope": []}, "scope"), ({"granted_by": ""}, "granted_by"), ({"revoked": "no"}, "revoked"),
    ({"expires_at": "soon"}, "issued_at/expires_at"), ({"token_id": "b" * 8}, "token_id"),
])
def test_a_malformed_token_answer_stops_the_renewal_before_anything_is_written(tmp_path, monkeypatch, capsys,
                                                                             over, named):
    r = _renewal(tmp_path)
    monkeypatch.setattr(r, "get_token", lambda current: (200, good(**over)))
    assert r.current_token(TOKEN_ID) == renew_token.EXIT_FAILED
    cap = capsys.readouterr()       # one call: a second one would return empty text (C-1043, reviewer C-250 F-C250-3)
    out = cap.out + cap.err
    assert "malformed response" in out and f"({named})" in out and "nothing written" in out, out
    assert not (tmp_path / "st").exists()


def test_a_token_answer_for_another_id_is_malformed_as_token_id(tmp_path, monkeypatch, capsys):
    r = _renewal(tmp_path)
    monkeypatch.setattr(r, "get_token", lambda current: (200, good(token_id="c1b2c3d4-0000-4000-8000-000000000009")))
    assert r.current_token(TOKEN_ID) == renew_token.EXIT_FAILED
    assert "(token_id)" in capsys.readouterr().out


# --- decide(): the boundaries at exactly 0 days and exactly renew_within_days left -------------------


@pytest.fixture()
def renewal(tmp_path, monkeypatch):
    monkeypatch.setattr(renew_token, "utcnow", lambda: NOW)
    return _renewal(tmp_path, "--renew-within-days", "7")


def _decide(renewal, seconds_left: float, **over):
    return renewal.decide(good(expires_at=iso(NOW + timedelta(seconds=seconds_left)), **over))


def test_exactly_the_window_left_renews_and_one_second_more_does_not(renewal):
    due, why, left = _decide(renewal, 7 * DAY)
    assert due and why.startswith("expires within 7 days") and left == 7.0
    assert _decide(renewal, 7 * DAY + 1)[0] is False
    assert _decide(renewal, 7 * DAY - 1)[0] is True


def test_exactly_zero_left_is_expired_not_within_the_window(renewal):
    due, why, left = _decide(renewal, 0)
    assert due and why.startswith("expired") and "within" not in why and left == 0.0  # prints "-0.0": cosmetic
    assert _decide(renewal, 1)[1].startswith("expires within")  # one second left is still inside the window
    assert _decide(renewal, -1)[1].startswith("expired")


def test_a_token_three_days_past_expiry_prints_the_full_expired_text(renewal):
    """C-1043 (reviewer C-250 F-C250-1): the number is positive and has one decimal; `-left` -> `left` prints
    "-3.0". Exactly zero prints "-0.0": cosmetic, stated in the PR, the code is not changed for it."""
    due, why, left = _decide(renewal, -3 * DAY)
    assert due and why == "expired 3.0 days ago" and left == -3.0
    assert _decide(renewal, -36 * 3600)[1] == "expired 1.5 days ago"


@pytest.mark.parametrize("method, path, guarded", [
    ("POST", "/delegation/tokens", True),
    ("post", "/delegation/tokens", True),
    ("POST", "/delegation/tokens?x=1", True),                       # the query is ignored
    ("POST", "/delegation/tokens/abc/revoke", True),
    ("POST", "/delegation/tokensX", False),                          # fullmatch, not match (F-C250-2)
    ("POST", "/delegation/tokens/", False),
    ("POST", "/delegation/tokens/abc/revoke/extra", False),          # a trailing segment is not the route
    ("POST", "/delegation/tokens/abc/revokeX", False),
    ("POST", "/delegation/tokens/abc/def/revoke", False),            # the id segment holds no slash
    ("GET", "/delegation/tokens", False),
    ("POST", "/ledger/events", False),
])
def test_is_guarded_matches_the_whole_path_and_the_exact_method(method, path, guarded):
    assert renew_token.is_guarded(method, path) is guarded


def test_a_revoked_token_is_due_whatever_its_expiry(renewal):
    due, why, _ = _decide(renewal, 100 * DAY, revoked=True)
    assert due and why == "revoked"


def test_a_zero_day_window_renews_only_at_or_past_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(renew_token, "utcnow", lambda: NOW)
    r = _renewal(tmp_path, "--renew-within-days", "0")
    assert _decide(r, 1)[0] is False
    assert _decide(r, 0)[0] is True


def test_the_ttl_note_about_the_window_appears_at_exactly_the_window_and_not_above_it(tmp_path, capsys):
    r = _renewal(tmp_path, "--renew-within-days", "7", "--ttl-days", "7")
    r.ttl(good())
    assert "inside the 7-day renewal window" in capsys.readouterr().out
    r = _renewal(tmp_path, "--renew-within-days", "7", "--ttl-days", "8")
    r.ttl(good())
    assert "renewal window" not in capsys.readouterr().out


# --- the operator header goes on the mint and the revoke, and on nothing else ------------------------


class _Opener:
    def __init__(self):
        self.sent = []

    def open(self, req, timeout=None):
        self.sent.append((req.get_method(), req.selector, {k.lower(): v for k, v in req.header_items()}))

        class Resp:
            status = 200

            def __enter__(self_):  # noqa: N805
                return self_

            def __exit__(self_, *a):  # noqa: N805
                return False

            def read(self_):  # noqa: N805
                return json.dumps({"ok": True}).encode()

        return Resp()


@pytest.fixture()
def opener(monkeypatch):
    o = _Opener()
    monkeypatch.setattr(renew_token, "_OPENER", o)
    return o


OP = ("svc-renewer", "operator-test-key-0123456789")


def test_mint_and_revoke_carry_the_operator_pair_and_no_other_call_does(opener):
    api = renew_token.Api("http://h", "perimeter-test-secret", OP)
    api.call("POST", "/delegation/tokens", {"a": 1})
    api.call("POST", f"/delegation/tokens/{TOKEN_ID}/revoke", {})
    api.call("GET", f"/delegation/tokens/{TOKEN_ID}")
    api.call("POST", "/ledger/events", {"event_type": "token.renewed"})
    api.call("GET", "/delegation/tokens?agent_id=canary-gb10")
    mint, revoke, read, ledger, listing = opener.sent
    for _, _, headers in (mint, revoke):
        assert headers["x-field-operator"] == OP[0] and headers["x-field-operator-key"] == OP[1]
        assert headers["x-field-auth"] == "perimeter-test-secret"
    for _, _, headers in (read, ledger, listing):
        assert "x-field-operator" not in headers and "x-field-operator-key" not in headers
        assert headers["x-field-auth"] == "perimeter-test-secret"


def test_a_client_without_an_identity_sends_no_operator_header(opener):
    api = renew_token.Api("http://h", "perimeter-test-secret", None)
    api.call("POST", "/delegation/tokens", {"a": 1})
    api.call("POST", f"/delegation/tokens/{TOKEN_ID}/revoke", {})
    assert all("x-field-operator" not in h and "x-field-operator-key" not in h for _, _, h in opener.sent)


# --- the escaped form of a secret with a quote or a backslash ----------------------------------------


@pytest.mark.parametrize("secret, escaped", [
    ("plain-secret-value-0123", "plain-secret-value-0123"),
    ("with'quote-secret-0123", "with'quote-secret-0123"),
    ("with\\back-secret-0123", "with\\\\back-secret-0123"),
    ("both'\\mixed-secret-0123", "both'\\\\mixed-secret-0123"),
    ('dq"and\'sq-secret-0123', "dq\"and\\'sq-secret-0123"),
])
def test_secret_forms_are_the_verbatim_secret_and_its_repr_body(secret, escaped):
    assert renew_token.secret_forms(secret) == (secret, escaped)
    assert renew_token.secret_forms(secret)[1] == repr(secret)[1:-1]


def test_no_secret_gives_no_forms():
    assert renew_token.secret_forms(None) == () and renew_token.secret_forms("") == ()


@pytest.mark.parametrize("secret", ["it's\\a-long-secret-0123456789", "bq'\\mixed-long-secret-0123456789"])
def test_scrub_masks_the_escaped_form_of_a_secret_with_a_quote_or_a_backslash(secret):
    forms = renew_token.secret_forms(secret)
    escaped = forms[1]
    assert escaped != secret
    printed = f"Traceback: KeyError({secret!r})"  # what a traceback prints: the escaped form, quoted
    assert escaped in printed
    (line,) = renew_token.scrub([printed], forms, ())
    assert escaped[:8] not in line and "<redacted>" in line, line
    cut = renew_token.scrub(["x " + escaped[:12], escaped[12:] + " y"], forms, ())
    assert cut == ["x <redacted>", "<redacted> y"], cut
