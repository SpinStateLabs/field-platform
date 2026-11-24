"""S8-20: a blackholed upstream cost one timeout per metric, so one pack took minutes. After a transport
failure (no answer) to an upstream, the rest of the same build makes that upstream's metrics unavailable
at once, with the same literal query and note as before. An HTTP status is an answer and never trips it."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from attestation_reporter import engine as engine_mod
from attestation_reporter.engine import UNREACHABLE, PackEngine


class Down:
    """Raises on every call (a dropped host); counts them."""

    def __init__(self):
        self.calls = []

    def get(self, target, **kw):
        self.calls.append(target)
        raise TimeoutError("connect timed out")


class Status:
    """Answers every call with a fixed HTTP status and an empty JSON body."""

    def __init__(self, status):
        self.status, self.calls = status, []

    def get(self, target, **kw):
        self.calls.append(target)
        return SimpleNamespace(status_code=self.status, json=lambda: [])


def _metrics(pack):
    return {m.name: m for m in pack.all_metrics()}


def test_a_dead_ledger_is_called_exactly_once_per_build():
    ledger = Down()
    pack = PackEngine(ledger=ledger).build(period="2026-Q3")
    assert len(ledger.calls) == 1
    ledger_metrics = [m for m in pack.all_metrics() if m.source_query.startswith("GET http://127.0.0.1:8002")]
    assert len(ledger_metrics) > 10
    assert all(m.status == "unavailable" for m in ledger_metrics)


def test_each_upstream_is_remembered_separately():
    registry, ledger, delegation, governor = Down(), Down(), Down(), Down()
    PackEngine(registry=registry, ledger=ledger, delegation=delegation, governor=governor).build()
    assert [len(c.calls) for c in (registry, ledger, delegation, governor)] == [1, 1, 1, 1]


def test_a_healthy_other_upstream_is_still_queried_in_full():
    ledger, registry = Down(), Status(200)
    PackEngine(ledger=ledger, registry=registry).build()
    assert len(ledger.calls) == 1 and len(registry.calls) == 3


@pytest.mark.parametrize("code", [404, 500, 503])
def test_an_http_status_is_an_answer_and_never_short_circuits(code):
    ledger = Status(code)
    PackEngine(ledger=ledger).build(period="2026-Q3")
    assert len(ledger.calls) > 10


def test_the_unavailable_figures_and_queries_are_exactly_what_a_direct_failed_fetch_reports():
    ledger = Down()
    engine = PackEngine(ledger=ledger)
    pack = engine.build(period="2026-Q3")
    sealed = [m for m in pack.all_metrics() if m.source_query.startswith("GET http://127.0.0.1:8002")]
    base = "GET http://127.0.0.1:8002"
    for m in sealed:
        assert m.status == "unavailable"
        for segment in m.source_query.split(" ; "):       # a composite figure prints each query it ran
            assert segment.startswith(base)
            path, _, qs = segment[len(base):].partition("?")
            params = ({unquote(k): unquote(v) for k, v in (kv.split("=", 1) for kv in qs.split("&"))}
                      if qs else None)
            # outside a build there is no memory: the same fetch prints the same literal query
            _, query, ok, status = engine_mod._fetch_answer(Down(), engine.ledger_base, path, params)
            assert (ok, status) == (False, None) and segment == query
    assert any(m.note == UNREACHABLE for m in sealed)


def test_the_memory_is_per_build_and_gone_after_it():
    ledger = Down()
    engine = PackEngine(ledger=ledger)
    engine.build()
    engine.build()
    assert len(ledger.calls) == 2                       # one per build, not one ever
    assert engine_mod._DOWN.get() is None               # nothing leaks out of a build
    _, _, ok, _ = engine_mod._fetch_answer(Down(), "http://x", "/events")
    assert ok is False


def test_a_build_that_raises_still_resets_the_memory(monkeypatch):
    engine = PackEngine(ledger=Down())
    monkeypatch.setattr(engine, "_build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        engine.build()
    assert engine_mod._DOWN.get() is None
