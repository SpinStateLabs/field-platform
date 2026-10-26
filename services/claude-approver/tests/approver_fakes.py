"""Test doubles: a fake Managed Agents client and recorded FIELD services.

``FakeConsole`` mirrors the SDK surface the approver uses (anthropic v2.3.0):
``beta.sessions.{list, retrieve, archive}``, ``beta.sessions.events.{list,
send}`` and ``beta.agents.retrieve``, with keyword names as in the SDK. It
records every call and behaves like the API where the brief states a fact:
a confirmation is accepted only for an event whose ``evaluated_permission`` is
``ask`` and that has not been answered (else the whole send raises, like a
400), and a sent event is echoed into the event list.

``FieldServices`` is an ``httpx.MockTransport`` handler for the sentinel,
kill-switch and governor that records every request.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable

import httpx

T0 = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

CONSOLE_AGENT = "agent_011console"
FIELD_AGENT = "ssl-timekeeping-agent"
TOKEN = "tok_test_0001"


def set_map(monkeypatch, mapping: dict) -> None:
    monkeypatch.setenv("CLAUDE_APPROVER_AGENT_MAP", json.dumps(mapping))


def default_map(**overrides) -> dict:
    entry = {"field_agent_id": FIELD_AGENT, "token_id": TOKEN}
    entry.update(overrides)
    return {"_comment": "ignored", CONSOLE_AGENT: entry}


class FakeAPIError(Exception):
    def __init__(self, status_code: int, message: str = "fake api error"):
        super().__init__(message)
        self.status_code = status_code


def ns(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def usage(input_tokens=0, output_tokens=0, cache_read=0) -> SimpleNamespace:
    return ns(input_tokens=input_tokens, output_tokens=output_tokens,
              cache_read_input_tokens=cache_read, cache_creation=None, list_cost=None)


class FakeConsole:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.sessions: dict[str, SimpleNamespace] = {}
        self.events: dict[str, list[SimpleNamespace]] = {}
        self.agents: dict[str, SimpleNamespace] = {}
        self.retrieve_script: dict[str, list[str]] = {}
        self.fail: dict[str, Exception] = {}
        self._n = 0
        self.beta = ns(
            sessions=ns(
                list=self._sessions_list, retrieve=self._sessions_retrieve,
                archive=self._sessions_archive,
                events=ns(list=self._events_list, send=self._events_send),
            ),
            agents=ns(retrieve=self._agents_retrieve),
        )

    # ----------------------------------------------------------- builders

    def _ts(self) -> datetime:
        self._n += 1
        return T0 + timedelta(seconds=self._n)

    def add_agent(self, agent_id: str, model: str = "claude-sonnet-5-5") -> None:
        self.agents[agent_id] = ns(id=agent_id, model=ns(id=model))

    def add_session(self, sid: str, agent_id: str, *, status: str = "idle",
                    environment_id: str = "env_1", model: str | None = "claude-opus-5-5",
                    use: SimpleNamespace | None = None) -> SimpleNamespace:
        agent = ns(id=agent_id, model=ns(id=model) if model else None, version=1)
        s = ns(id=sid, agent=agent, status=status, environment_id=environment_id,
               archived_at=None, updated_at=self._ts(), usage=use or usage())
        self.sessions[sid] = s
        self.events.setdefault(sid, [])
        return s

    def touch(self, sid: str) -> None:
        self.sessions[sid].updated_at = self._ts()

    def add_event(self, sid: str, etype: str, **fields: Any) -> SimpleNamespace:
        eid = fields.pop("id", None) or f"sevt_{len(self.events[sid]) + 1:03d}_{sid}"
        ev = ns(id=eid, type=etype, processed_at=fields.pop("processed_at", self._ts()), **fields)
        self.events[sid].append(ev)
        self.touch(sid)
        return ev

    def ask(self, sid: str, name: str = "bash", *, etype: str = "agent.tool_use",
            permission: str = "ask", **extra: Any) -> SimpleNamespace:
        fields: dict[str, Any] = {"name": name, "input": {"command": "ls"},
                                  "evaluated_permission": permission}
        if etype == "agent.mcp_tool_use":
            fields["mcp_server_name"] = extra.pop("mcp_server_name", "github")
        fields.update(extra)
        return self.add_event(sid, etype, **fields)

    def pending_ids(self, sid: str) -> list[str]:
        """What the API lists in ``requires_action.event_ids``: every ask and
        custom tool use not yet answered."""
        evs = self.events.get(sid, [])
        answered = {getattr(e, "tool_use_id", None) for e in evs if e.type == "user.tool_confirmation"}
        answered |= {getattr(e, "custom_tool_use_id", None) for e in evs
                     if e.type == "user.custom_tool_result"}
        return [e.id for e in evs if e.id not in answered and (
            (e.type in ("agent.tool_use", "agent.mcp_tool_use")
             and getattr(e, "evaluated_permission", None) == "ask")
            or e.type == "agent.custom_tool_use")]

    def idle(self, sid: str, reason: str = "requires_action", event_ids=None, *,
             omit_ids: bool = False) -> SimpleNamespace:
        """``event_ids=None`` lists what is pending, as the API does; pass a list
        to override it, or ``omit_ids=True`` for a stop_reason without the field."""
        self.sessions[sid].status = "idle"
        if reason != "requires_action" or omit_ids:
            stop = ns(type=reason)
        else:
            ids = self.pending_ids(sid) if event_ids is None else list(event_ids)
            stop = ns(type=reason, event_ids=ids)
        return self.add_event(sid, "session.status_idle", stop_reason=stop)

    # ---------------------------------------------------------------- API

    def _maybe_fail(self, name: str) -> None:
        exc = self.fail.get(name)
        if exc is not None:
            raise exc

    def _sessions_list(self, **kw: Any):
        self.calls.append(("sessions.list", kw))
        self._maybe_fail("sessions.list")
        out = []
        for s in self.sessions.values():
            if "agent_id" in kw and s.agent.id != kw["agent_id"]:
                continue
            if s.archived_at is not None and not kw.get("include_archived"):
                continue
            out.append(s)
        return out

    def _sessions_retrieve(self, session_id: str, **kw: Any):
        self.calls.append(("sessions.retrieve", {"session_id": session_id, **kw}))
        self._maybe_fail("sessions.retrieve")
        s = self.sessions[session_id]
        script = self.retrieve_script.get(session_id)
        if script:
            s.status = script.pop(0) if len(script) > 1 else script[0]
        return s

    def _sessions_archive(self, session_id: str, **kw: Any):
        self.calls.append(("sessions.archive", {"session_id": session_id, **kw}))
        self._maybe_fail("sessions.archive")
        s = self.sessions[session_id]
        if s.status == "running":
            raise FakeAPIError(400, "cannot archive while running")
        s.archived_at = self._ts()
        return s

    def _events_list(self, session_id: str, **kw: Any):
        self.calls.append(("events.list", {"session_id": session_id, **kw}))
        self._maybe_fail("events.list")
        evs = list(self.events.get(session_id, []))
        gte = kw.get("created_at_gte")
        if gte is not None:
            evs = [e for e in evs if e.processed_at is None or e.processed_at >= gte]
        if kw.get("types"):
            evs = [e for e in evs if e.type in kw["types"]]
        evs.sort(key=lambda e: e.processed_at or T0, reverse=kw.get("order") == "desc")
        if kw.get("limit"):
            evs = evs[: kw["limit"]]
        return evs

    def _events_send(self, session_id: str, events: list[dict], **kw: Any):
        self.calls.append(("events.send", {"session_id": session_id, "events": events, **kw}))
        self._maybe_fail("events.send")
        by_id = {e.id: e for e in self.events.get(session_id, [])}
        answered = {e.tool_use_id for e in self.events.get(session_id, [])
                    if e.type == "user.tool_confirmation"}
        for e in events:
            if e["type"] == "user.tool_confirmation":
                target = by_id.get(e["tool_use_id"])
                if target is None or getattr(target, "evaluated_permission", None) != "ask":
                    raise FakeAPIError(400, "confirmation for an event that is not ask")
                if e["tool_use_id"] in answered:
                    raise FakeAPIError(400, "already confirmed")
                if e["result"] not in ("allow", "deny"):
                    raise FakeAPIError(400, "bad result")
                if e["result"] == "allow" and "deny_message" in e:
                    raise FakeAPIError(400, "deny_message only with deny")
        for e in events:
            fields = {k: v for k, v in e.items() if k != "type"}
            self.add_event(session_id, e["type"], **fields)
            if e["type"] == "user.interrupt" and self.sessions[session_id].status == "running":
                pass  # the retrieve script decides when it goes idle
        return ns(data=[])

    def _agents_retrieve(self, agent_id: str, **kw: Any):
        self.calls.append(("agents.retrieve", {"agent_id": agent_id, **kw}))
        self._maybe_fail("agents.retrieve")
        return self.agents[agent_id]

    # ------------------------------------------------------------ queries

    def sends(self, sid: str | None = None) -> list[dict]:
        return [kw for name, kw in self.calls if name == "events.send"
                and (sid is None or kw["session_id"] == sid)]

    def confirmations(self, sid: str | None = None) -> list[dict]:
        return [e for kw in self.sends(sid) for e in kw["events"]
                if e["type"] == "user.tool_confirmation"]

    def count(self, name: str) -> int:
        return sum(1 for n, _ in self.calls if n == name)


class FieldServices:
    """Sentinel + kill-switch + governor behind one MockTransport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.sentinel: Callable[[httpx.Request], httpx.Response] = lambda r: self.verdict("ALLOW")
        self.heartbeat: Callable[[httpx.Request], httpx.Response] = (
            lambda r: httpx.Response(200, json={"killed": False}))
        self.usage: Callable[[httpx.Request], httpx.Response] = (
            lambda r: httpx.Response(201, json={"ok": True}))

    @staticmethod
    def verdict(decision: str, clause: str | None = None, reasons=None,
                context: dict | None = None) -> httpx.Response:
        return httpx.Response(200, json={
            "decision": decision, "agent_id": "x", "action": "y", "clause_id": clause,
            "reasons": reasons or [], "context": context or {},
        })

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/check"):
            return self.sentinel(request)
        if "/heartbeat/" in path:
            return self.heartbeat(request)
        if path.endswith("/usage"):
            return self.usage(request)
        return httpx.Response(404, json={"detail": "no route"})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def of(self, suffix: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith(suffix) or suffix in r.url.path]

    def checks(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("/check")]

    def usage_posts(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("/usage")]

    def heartbeats(self) -> list[httpx.Request]:
        return [r for r in self.requests if "/heartbeat/" in r.url.path]
