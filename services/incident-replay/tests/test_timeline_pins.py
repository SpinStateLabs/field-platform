"""R-14 pins (C-137): the per-event `enforced` label and `_summarize` text,
the Markdown "revoked" cell of the Accountable grant, and a malformed
/health. Stub clients, so each assertion names exactly one engine branch."""

from __future__ import annotations

import pytest

from incident_replay.engine import ReplayEngine, ReplayRequest, render_markdown

AGENT = "pin-agent"
REQ = ReplayRequest(
    agent_id=AGENT, since="2020-01-01T00:00:00+00:00", until="2030-01-01T00:00:00+00:00"
)
TOKEN_ID = "abcdef0123456789"


class _Ledger:
    def __init__(self, events=(), health=None):
        self._events = list(events)
        self._health = health

    def verify(self):
        return {"ok": True, "length": len(self._events)}

    def events(self, **_params):
        return self._events

    def health(self):
        return self._health


class _Registry:
    def get_agent(self, agent_id):
        return {"agent_id": agent_id, "name": "Pin Agent", "owner": "Pin Owner",
                "domain": "finance", "status": "active", "manifest_ref": None}


class _Delegation:
    def __init__(self, tokens=()):
        self._tokens = list(tokens)

    def tokens(self, agent_id):
        return self._tokens


def _event(event_type, payload=None, n=0):
    return {"ts": f"2026-01-01T00:00:{n:02d}+00:00", "event_type": event_type,
            "hash": f"h{n}", "payload": payload}


def _grant(**over):
    base = {"token_id": TOKEN_ID, "granted_by": "Controller", "scope": ["draft invoices"],
            "issued_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2027-01-01T00:00:00+00:00",
            "revoked": False, "revocation_id": None, "revoked_at": None}
    return {**base, **over}


def _replay(events=(), tokens=(), health=None):
    engine = ReplayEngine(_Ledger(events, health), _Registry(), _Delegation(tokens))
    return engine.replay(REQ)


@pytest.mark.parametrize(
    ("event_type", "payload", "enforced", "summary"),
    [
        ("conformance.allow", {"action": "draft invoices", "clause_id": None},
         True, "ALLOW 'draft invoices'"),
        ("conformance.block", {"action": "transfer funds", "clause_id": "D.scope"},
         True, "BLOCK 'transfer funds' [D.scope]"),
        ("conformance.shadow_block", {"action": "transfer funds", "would_block": "D.scope"},
         False, "SHADOW_BLOCK 'transfer funds' [D.scope] (log-only, not enforced)"),
        ("conformance.shadow_escalate", {"action": "wire", "would_block": "E.review"},
         False, "SHADOW_ESCALATE 'wire' [E.review] (log-only, not enforced)"),
        ("delegation.mint",
         {"token_id": TOKEN_ID, "granted_by": "Controller", "scope": ["draft invoices"]},
         None, "token abcdef01… minted by Controller scope=['draft invoices']"),
        ("delegation.revoke", {"token_id": TOKEN_ID},
         None, "token abcdef01… revoked"),
        ("kill.agent", {"operator": "CISO on-call", "reason": "scope probing"},
         None, "kill.agent by CISO on-call (scope probing)"),
        ("kill.domain", {}, None, "kill.domain by ? ()"),
        ("spend.throttle", {"cap": 5}, None, "spend.throttle {'cap': 5}"),
        ("agent.registered", {"agent_id": AGENT}, None, "agent.registered"),
    ],
)
def test_timeline_labels_each_event_type(event_type, payload, enforced, summary):
    entry = _replay([_event(event_type, payload)]).timeline[0]
    assert entry.enforced is enforced
    assert entry.summary == summary


def test_a_payloadless_event_is_summarised_without_crashing():
    entry = _replay([_event("kill.agent", None)]).timeline[0]
    assert entry.summary == "kill.agent by ? ()"
    assert entry.enforced is None


def _accountable_line(md: str) -> str:
    return next(ln for ln in md.splitlines() if ln.startswith("*Accountable grant:*"))


def test_markdown_accountable_grant_live_reads_revoked_no():
    md = render_markdown(_replay(tokens=[_grant()]))
    assert _accountable_line(md).endswith("· revoked no")


def test_markdown_accountable_grant_revoked_reads_revoked_yes_with_time():
    pm = _replay(tokens=[_grant(revoked=True, revocation_id="r1",
                                revoked_at="2026-01-02T03:04:05.678+00:00")])
    assert _accountable_line(render_markdown(pm)).endswith(
        "· revoked yes (2026-01-02T03:04:05)")


def test_markdown_accountable_grant_revoked_without_time_reads_plain_yes():
    pm = _replay(tokens=[_grant(revoked=True, revocation_id="r1")])
    assert _accountable_line(render_markdown(pm)).endswith("· revoked yes")


@pytest.mark.parametrize("health", [["not", "a", "dict"], "ok", None])
def test_malformed_health_returns_no_note(health):
    pm = ReplayEngine(_Ledger(health=health), _Registry(), _Delegation()).replay(REQ)
    assert pm.integrity_notes == []
