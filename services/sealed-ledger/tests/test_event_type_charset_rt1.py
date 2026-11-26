"""B-RT1 (F-H1-3): the ledger refuses look-alike event types.

(1) POST /events accepts only ^[a-z0-9_.-]+$ for event_type, with a fixed 422 that never repeats the input.
(2) The sealed ``operator.`` prefix test normalises (NFKC, zero-width and BOM removed) so no look-alike
reaches the accepted path. Every value is made up."""

import ast
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import EVENT_TYPE_PATTERN, create_app
from sealed_ledger.store import LedgerStore

REPO = Path(__file__).resolve().parents[3]
CHARSET = re.compile(EVENT_TYPE_PATTERN)


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")))


@pytest.fixture()
def enforce(tmp_path, monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


LOOKALIKES = {
    "zero-width space prefix (U+200B)": "​operator.kill",
    "BOM prefix (U+FEFF)": "﻿operator.kill",
    "one-dot leader (U+2024)": "operator․kill",
    "upper case": "Operator.kill",
    "trailing space": "operator.kill ",
    "trailing newline": "ledger.x\n",
    "embedded space": "a b",
    "non-ascii letter": "kıll.x",
}


@pytest.mark.parametrize("name", LOOKALIKES)
def test_lookalike_event_type_is_a_fixed_422_with_no_echo(client, name):
    et = LOOKALIKES[name]
    r = client.post("/events", json={"event_type": et, "payload": {}})
    assert r.status_code == 422, r.text
    assert "operator" not in r.text.lower(), r.text   # the rejected input is not echoed
    assert client.get("/events").json() == []


@pytest.mark.parametrize("et", ["operator.kill", "operator.mode_changed"])
def test_plain_operator_types_still_refused_under_enforce(client, enforce, et):
    r = client.post("/events", json={"event_type": et, "payload": {}})
    assert r.status_code == 403


@pytest.mark.parametrize("et", ["operator.unauthenticated", "operator.refused"])
def test_self_reportable_types_still_accepted(client, enforce, et):
    assert client.post("/events", json={"event_type": et, "payload": {}}).status_code == 201


def test_admit_refuses_every_lookalike_of_a_sealed_prefix(enforce):
    for et in ("​operator.kill", "﻿operator.kill", "operator․kill",
               "​operator.unauthenticated", "operator․refused", "OPERATOR.kill"):
        with pytest.raises(oa.OperatorRefused) as e:
            oa.admit_ledger_event(et, {}, {})
        assert e.value.status == 403, et


def test_may_attribute_never_true_for_a_sealed_lookalike():
    a = oa.OperatorAuth(mode=oa.ENFORCE, operator_id="x", scopes=("ledger_attribute",),
                        event_prefixes=("​", "operator"))
    assert a.may_attribute("​operator.kill") is False
    assert a.may_attribute("operator․kill") is False


def test_keyrotation_prefix_is_accepted_today_and_documented(client, enforce):
    # Sealing keyrotation. is NOT done here (PR 57 rework, C-496); this pins today's behaviour.
    r = client.post("/events", json={"event_type": "keyrotation.breakglass_used", "payload": {}})
    assert r.status_code == 201


def _literal_event_types():
    found = set()
    for root in ("services", "packages", "tools"):
        for f in (REPO / root).rglob("*.py"):
            if "tests" in f.parts or "test_" in f.name or ".venv" in f.parts or "site-packages" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.keyword) and n.arg == "event_type" \
                        and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                    found.add(n.value.value)
    return found


def test_every_literal_event_type_the_repo_emits_passes_the_charset():
    found = _literal_event_types()
    assert found, "the scan found nothing: the test is not looking"
    assert [t for t in sorted(found) if not CHARSET.match(t)] == []


def test_conformance_decisions_pass_the_charset():
    from field_core.conformance import Decision
    assert all(CHARSET.match(f"conformance.{d.value.lower()}") for d in Decision)
