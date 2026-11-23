"""`on_breach` is recorded and served, never read: BLOCK comes from the cap limit alone (S12-16).

The field-core financial-agent template comments `on_breach: halt # breaching the cap fires the kill switch`; the
governor never consults the field and never calls the kill-switch (the sentinel's /check is the gate). The README and
SPEC must say so, and these tests pin the behavior the docs describe.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SPEC = (ROOT / "SPEC.md").read_text(encoding="utf-8")
VALUES = ("halt", "escalate", "ignore")


def _run(tmp_path, on_breach):
    client = TestClient(create_app(store=GovernorStore(tmp_path / f"{on_breach}.sqlite3")))
    body = {"agent_id": "a1", "currency": "USD", "limit_cents": 1000, "period": "daily",
            "escalate_at_pct": 80, "on_breach": on_breach}
    put = client.put("/caps/a1", json=body)
    assert put.status_code == 200
    spent = client.post("/spend", json={"agent_id": "a1", "cents": 1500, "tokens": 0, "actions": 0})
    assert spent.status_code in (200, 201)
    status = client.get("/status/a1")
    return put.json(), spent.json(), status.json()


def test_the_value_is_stored_and_echoed(tmp_path):
    for value in VALUES:
        put, _spent, _status = _run(tmp_path, value)
        assert put["on_breach"] == value


def test_block_is_identical_whatever_on_breach_says(tmp_path):
    runs = {v: _run(tmp_path, v) for v in VALUES}
    for _put, spent, status in runs.values():
        assert spent["state"] == "BLOCK" and status["state"] == "BLOCK"
    assert runs["halt"][1] == runs["escalate"][1] == runs["ignore"][1]
    assert runs["halt"][2] == runs["escalate"][2] == runs["ignore"][2]


def test_the_readme_declared_table_has_an_on_breach_row():
    rows = [line for line in README.split("\n## Enforced vs. Declared\n", 1)[1].split("\n## ", 1)[0].splitlines()
            if line.startswith("|") and "on_breach" in line]
    assert len(rows) == 1
    row = rows[0]
    assert "**Declared only**" in row and "never read" in row and "sentinel" in row


def test_the_spec_says_on_breach_is_declared_only():
    assert "`on_breach`" in SPEC and "declared only" in SPEC.lower()
