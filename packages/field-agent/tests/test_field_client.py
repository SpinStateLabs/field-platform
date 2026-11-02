"""field_agent.field_client — the stdlib FIELD client lifted from cost-optimizer (P28(c)).

Three parts:

A. ``FieldClientTests``: the source repo's own tests
   (SpinStateLabs/cost-optimizer ``tests/test_field_client.py`` at 817aace), ported
   with the import path changed, the placeholder token/secret strings renamed and
   one optional element (response headers) added to the fake route tuple. Every
   assertion is the source's. A loopback ``http.server`` plays the estate; the
   "dead" client points at 127.0.0.1:9 (discard port, nothing listening).
B. Additions that close gaps the source tests leave open (a redirect that WOULD
   reach an ALLOW if followed; an invalid usage record that WOULD be accepted if
   sent; the module stays stdlib-only; the facade re-exports the same objects).
C. Contract tests against THIS repo's real sentinel, spend-governor and
   kill-switch apps (the ``stack`` fixture), reached through an in-process
   opener under the estate's path prefixes. No socket, no estate, no network.
"""

import ast
import email.message
import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import field_agent
from field_agent import field_client as fc_mod
from field_agent.field_client import Blocked, Escalated, FieldClient, Halted, Unmetered
from tests.conftest import AGENT_ID

SECRET, TOKEN = "fake-shared-secret", "fake-token-id"


# == A. ported from cost-optimizer ===========================================

class FakeEstate(BaseHTTPRequestHandler):
    routes: dict = {}
    seen: list = []

    def _reply(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        FakeEstate.seen.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        status, payload, *extra = FakeEstate.routes.get((self.command, self.path), (404, {"detail": "no route"}))
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        for k, v in (extra[0] if extra else {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST = _reply

    def log_message(self, *a):
        pass


class FieldClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeEstate)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        FakeEstate.routes, FakeEstate.seen = {}, []
        self.c = FieldClient(self.url, "cost-optimizer", TOKEN, shared_secret=SECRET)

    def alive(self):
        FakeEstate.routes[("GET", "/killswitch/heartbeat/cost-optimizer")] = (200, {"killed": False})

    def test_allow_sends_auth_and_body(self):
        self.alive()
        FakeEstate.routes[("POST", "/sentinel/check")] = (200, {"decision": "ALLOW", "clause_id": None})
        self.assertTrue(self.c.guard("open report pull request").allowed)
        method, path, headers, body = FakeEstate.seen[-1]
        self.assertEqual(body, {"agent_id": "cost-optimizer", "action": "open report pull request", "token_id": TOKEN})
        self.assertEqual(headers.get("x-field-auth"), SECRET)

    def test_escalate_and_block_raise_without_retry(self):
        self.alive()
        FakeEstate.routes[("POST", "/sentinel/check")] = (200, {"decision": "ESCALATE", "clause_id": "E.escalation_trigger"})
        with self.assertRaises(Escalated):
            self.c.guard("publish monthly chargeback")
        self.assertEqual(sum(1 for s in FakeEstate.seen if s[1] == "/sentinel/check"), 1)
        FakeEstate.routes[("POST", "/sentinel/check")] = (200, {"decision": "BLOCK", "clause_id": "D.scope"})
        with self.assertRaises(Blocked):
            self.c.guard("change subscription")

    def test_rule1_fail_closed(self):
        for route in [(500, {}), (200, b"not json"), (200, {"decision": "MAYBE"}), (401, {})]:
            FakeEstate.routes[("POST", "/sentinel/check")] = route
            self.assertEqual(self.c.check("x").decision, "BLOCK")
        dead = FieldClient("http://127.0.0.1:9", "cost-optimizer", TOKEN, timeout=0.5)
        self.assertEqual(dead.check("x").decision, "BLOCK")

    def test_rules2_and_4_killed_unless_explicitly_alive(self):
        for route in [None, (500, {}), (200, {"killed": True}), (200, {}), (200, {"killed": "false"})]:
            FakeEstate.routes.pop(("GET", "/killswitch/heartbeat/cost-optimizer"), None)
            if route:
                FakeEstate.routes[("GET", "/killswitch/heartbeat/cost-optimizer")] = route
            self.assertTrue(self.c.killed())
            with self.assertRaises(Halted):
                self.c.guard("x")
        self.alive()
        self.assertFalse(self.c.killed())

    def test_rule3_usage_unmetered(self):
        FakeEstate.routes[("POST", "/governor/usage")] = (201, {"ok": True})
        self.c.report_usage("claude-sonnet-5-5", 1000, 200, 5000, "daily digest")
        FakeEstate.routes[("POST", "/governor/usage")] = (404, {"detail": "no cap"})
        with self.assertRaises(Unmetered):
            self.c.report_usage("claude-sonnet-5-5", 1, 1)

    def test_redirects_fail_closed_and_target_never_hit(self):
        FakeEstate.routes[("POST", "/sentinel/check")] = (302, {})
        FakeEstate.routes[("GET", "/killswitch/heartbeat/cost-optimizer")] = (302, {})
        self.assertEqual(self.c.check("x").decision, "BLOCK")
        self.assertTrue(self.c.killed())

    def test_list_decision_is_block(self):
        FakeEstate.routes[("POST", "/sentinel/check")] = (200, {"decision": ["ALLOW"]})
        self.assertEqual(self.c.check("x").decision, "BLOCK")

    def test_unreachable_killswitch_means_killed(self):
        dead = FieldClient("http://127.0.0.1:9", "cost-optimizer", TOKEN, timeout=0.5)
        self.assertTrue(dead.killed())

    def test_escalated_action_not_rechecked(self):
        self.alive()
        FakeEstate.routes[("POST", "/sentinel/check")] = (200, {"decision": "ESCALATE"})
        for _ in range(3):
            with self.assertRaises(Escalated):
                self.c.guard("publish monthly chargeback")
        self.assertEqual(sum(1 for s in FakeEstate.seen if s[1] == "/sentinel/check"), 1)

    def test_invalid_usage_record_is_unmetered(self):
        for args in [(None, 1, 1), ("m", -1, 1), ("m", 1.5, 1), ("m", True, 1)]:
            with self.assertRaises(Unmetered):
                self.c.report_usage(*args)

    def test_secret_needs_https_or_private_host(self):
        with self.assertRaises(ValueError):
            FieldClient("http://force-field-sandbox.example", "a", "t", shared_secret=SECRET)
        FieldClient("https://force-field-sandbox.example", "a", "t", shared_secret=SECRET)
        FieldClient("http://10.0.2.10:18080", "a", "t", shared_secret=SECRET)

    def test_agent_id_is_quoted_in_path(self):
        c = FieldClient(self.url, "../x y", TOKEN)
        c.killed()
        self.assertEqual(FakeEstate.seen[-1][1], "/killswitch/heartbeat/..%2Fx%20y")

    def test_repr_hides_secrets(self):
        self.assertNotIn(SECRET, repr(self.c))
        self.assertNotIn(TOKEN, repr(self.c))

    # == B. additions (same fake estate) ======================================

    def test_redirect_to_an_allow_is_not_followed(self):
        """The source test's 302s carry no Location, so following them could not
        change the outcome. Here following WOULD reach an ALLOW and an alive
        heartbeat; the client must still BLOCK, stay killed and never touch either
        target (so the secret is never re-sent to it)."""
        FakeEstate.routes[("POST", "/sentinel/check")] = (302, {}, {"location": f"{self.url}/elsewhere/check"})
        FakeEstate.routes[("GET", "/elsewhere/check")] = (200, {"decision": "ALLOW"})
        FakeEstate.routes[("POST", "/elsewhere/check")] = (200, {"decision": "ALLOW"})
        FakeEstate.routes[("GET", "/killswitch/heartbeat/cost-optimizer")] = (
            302, {}, {"location": f"{self.url}/elsewhere/heartbeat"})
        FakeEstate.routes[("GET", "/elsewhere/heartbeat")] = (200, {"killed": False})
        self.assertEqual(self.c.check("x").decision, "BLOCK")
        self.assertTrue(self.c.killed())
        with self.assertRaises(Halted):
            self.c.guard("x")
        self.assertEqual([s for s in FakeEstate.seen if s[1].startswith("/elsewhere/")], [])

    def test_invalid_usage_record_is_never_sent(self):
        """With a governor that would accept anything, only the client's own
        validation can refuse an invalid record (the source test's estate has no
        /governor/usage route, so a 404 refused those records too)."""
        FakeEstate.routes[("POST", "/governor/usage")] = (201, {"ok": True})
        for args in [(None, 1, 1), ("", 1, 1), ("m", -1, 1), ("m", 1.5, 1), ("m", True, 1), ("m", 1, 1, -5)]:
            with self.assertRaises(Unmetered):
                self.c.report_usage(*args)
        self.assertEqual([s for s in FakeEstate.seen if s[1] == "/governor/usage"], [])

    def test_unreachable_governor_is_unmetered(self):
        """Rule 3's transport branch: the source tests only reach the governor
        when it answers."""
        dead = FieldClient("http://127.0.0.1:9", "cost-optimizer", TOKEN, timeout=0.5)
        with self.assertRaises(Unmetered):
            dead.report_usage("claude-sonnet-5-5", 1, 1)


def test_module_imports_only_the_standard_library():
    """The module a stdlib-only gateway copies or imports must stay stdlib-only."""
    tree = ast.parse(Path(fc_mod.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "field_client must not import from the package"
            roots.add(node.module.split(".")[0])
    assert roots and roots <= set(sys.stdlib_module_names) | {"__future__"}, roots


def test_facade_reexports_the_same_objects():
    assert field_agent.FieldClient is fc_mod.FieldClient
    assert field_agent.FieldStop is fc_mod.FieldStop
    for name in ("FieldClient", "FieldStop"):
        assert name in field_agent.__all__
    for cls in (fc_mod.Blocked, fc_mod.Escalated, fc_mod.Halted, fc_mod.Unmetered):
        assert issubclass(cls, fc_mod.FieldStop)


# == C. contract tests against the real services ==============================

ESTATE = "http://estate.invalid"


class _Resp:
    def __init__(self, status, raw):
        self.status, self._raw = status, raw

    def read(self, amt=None):           # like http.client.HTTPResponse.read(amt)
        return self._raw if amt is None else self._raw[:amt]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class InProcessEstate:
    """A urllib-style opener that routes /sentinel, /governor and /killswitch to
    the stack's real apps, never follows a redirect, and records every call."""

    def __init__(self, stack):
        self.apps = {"/sentinel": stack.sentinel, "/governor": stack.governor, "/killswitch": stack.killswitch}
        self.seen = []

    def __call__(self, req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        assert f"{url.scheme}://{url.netloc}" == ESTATE
        prefix, _, rest = url.path[1:].partition("/")
        app = self.apps[f"/{prefix}"]
        self.seen.append((req.get_method(), url.path))
        r = app.request(req.get_method(), f"/{rest}", content=req.data,
                        headers=dict(req.header_items()), follow_redirects=False)
        if r.status_code >= 300:
            hdrs = email.message.Message()
            raise urllib.error.HTTPError(req.full_url, r.status_code, "in-process", hdrs, io.BytesIO(r.content))
        return _Resp(r.status_code, r.content)

    def count(self, path):
        return sum(1 for _, p in self.seen if p == path)


def _client(stack, agent_id=AGENT_ID, token=None):
    estate = InProcessEstate(stack)
    return FieldClient(ESTATE, agent_id, token or "no-token", opener=estate), estate


def test_contract_allow_then_metered(stack):
    token = stack.mint_token()
    stack.set_cap()
    c, estate = _client(stack, token=token)
    assert c.guard("draft invoices").allowed
    assert stack.events("conformance.allow")[-1]["payload"]["action"] == "draft invoices"
    c.report_usage("claude-haiku-4-5", 1000, 200, 0, "contract test")
    assert stack.events("usage.recorded")[-1]["payload"]["model"] == "claude-haiku-4-5"
    assert estate.seen == [("GET", f"/killswitch/heartbeat/{AGENT_ID}"), ("POST", "/sentinel/check"),
                           ("POST", "/governor/usage")]


def test_contract_rule4_unknown_agent_halts_before_any_check(stack):
    """The real kill-switch answers killed=true, status=unregistered for an id it
    has never seen. The client halts and never asks the sentinel."""
    c, estate = _client(stack, agent_id="never-registered")
    assert stack.killswitch.get("/heartbeat/never-registered").json()["status"] == "unregistered"
    assert c.killed() is True
    try:
        c.guard("draft invoices")
        raise AssertionError("expected Halted")
    except Halted:
        pass
    assert estate.count("/sentinel/check") == 0


def test_contract_rule2_killed_agent_halts(stack):
    token = stack.mint_token()
    stack.set_cap()
    c, _ = _client(stack, token=token)
    assert c.guard("draft invoices").allowed
    stack.kill()
    try:
        c.guard("draft invoices")
        raise AssertionError("expected Halted")
    except Halted:
        pass


def test_contract_rule3_no_cap_is_unmetered(stack):
    c, _ = _client(stack)
    try:
        c.report_usage("claude-haiku-4-5", 1000, 200)
        raise AssertionError("expected Unmetered")
    except Unmetered as exc:
        assert "HTTP 404" in str(exc)
    assert stack.events("usage.recorded") == []


def test_contract_rule5_escalate_is_not_rechecked(stack):
    token = stack.mint_token()
    c, estate = _client(stack, token=token)
    try:
        c.guard("send invoice email")
        raise AssertionError("expected Escalated")
    except Escalated as exc:
        assert exc.verdict.clause_id == "E.escalation_trigger"
    for _ in range(2):
        try:
            c.guard("send invoice email")
            raise AssertionError("expected Escalated")
        except Escalated as exc:
            assert exc.verdict is None  # refused locally, not re-checked
    assert estate.count("/sentinel/check") == 1


def test_contract_rule1_out_of_scope_blocks(stack):
    token = stack.mint_token()
    c, _ = _client(stack, token=token)
    try:
        c.guard("transfer funds")
        raise AssertionError("expected Blocked")
    except Blocked as exc:
        assert exc.verdict.decision == "BLOCK" and exc.verdict.clause_id == "D.scope"
