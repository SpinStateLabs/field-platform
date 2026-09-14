"""``POST /regwatch/check`` and ``GET /staleness`` ``last_check`` (v1.2 D4),
the no-clear-over-HTTP guarantee, and the doc-drift guard.

Offline: a fake fetcher is injected through ``create_app(fetcher=...)``;
conftest.py makes the default httpx factory raise.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app
from compliance_crosswalk.mapping import (
    SRC_EU_ART12,
    SRC_EU_ART14,
    SRC_EU_OFFICIAL,
    SRC_NIST,
    SRC_OSFI,
)
from compliance_crosswalk.staleness import StaleStore

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ALL_URLS = (SRC_OSFI, SRC_NIST, SRC_EU_OFFICIAL, SRC_EU_ART12, SRC_EU_ART14)


def page(text: str = "The text as verified.") -> bytes:
    # carries one cited reference identifier per watched page (D4-R3 anchors)
    return (f"<html><body><h1>Regulation</h1><p>Principle 1.1 · GOVERN 1.6 · "
            f"Article 12 · Article 14</p><p>{text}</p></body></html>").encode()


class FakeFetcher:
    def __init__(self, pages: dict | None = None):
        self.pages = dict(pages or {})
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        value = self.pages.get(url, page())
        if isinstance(value, BaseException):
            raise value
        return value


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


def statuses(body: dict) -> dict[str, str]:
    return {row["framework"]: row["status"] for row in body["frameworks"]}


# --- served check ---------------------------------------------------------------

def test_regwatch_check_200_with_per_source_statuses_and_last_check(store):
    fetch = FakeFetcher()
    client = TestClient(create_app(stale_store=store, fetcher=fetch))
    assert client.get("/staleness").json()["last_check"] is None  # never checked

    r = client.post("/regwatch/check")
    assert r.status_code == 200, r.text
    body = r.json()
    assert statuses(body) == {"osfi-e23": "baseline", "eu-ai-act": "baseline",
                              "iso-42001": "no-source", "nist-ai-rmf": "baseline"}
    assert body["exit_code"] == 0 and body["trigger"] == "http"
    eu = next(row for row in body["frameworks"] if row["framework"] == "eu-ai-act")
    assert eu["fetched_via"] == "official"
    assert [s["url"] for s in eu["sources"]] == [SRC_EU_OFFICIAL]

    last = client.get("/staleness").json()["last_check"]
    assert last["checked_at"] == body["checked_at"]
    assert last["trigger"] == "http"
    assert last["frameworks"]["iso-42001"] == "no-source"


def test_regwatch_check_is_200_even_when_everything_is_unreachable(store):
    fetch = FakeFetcher({u: httpx.ConnectError("synthetic") for u in ALL_URLS})
    client = TestClient(create_app(stale_store=store, fetcher=fetch))
    r = client.post("/regwatch/check")
    assert r.status_code == 200, r.text
    assert r.json()["exit_code"] == 2
    assert statuses(r.json())["osfi-e23"] == "unreachable"
    assert client.get("/staleness").json()["active"] == []


def test_regwatch_check_sets_a_flag_that_blocks_packs(store):
    client = TestClient(create_app(stale_store=store, fetcher=FakeFetcher()))
    client.post("/regwatch/check")
    client.app.state.fetcher = FakeFetcher({SRC_OSFI: page("amended")})
    r = client.post("/regwatch/check")
    assert r.status_code == 200 and r.json()["exit_code"] == 3
    assert [f["framework"] for f in client.get("/staleness").json()["active"]] == ["osfi-e23"]
    # the detected change is enforcement, not a report: packs now answer 409
    blocked = client.post("/pack", json={"signer": "Controller", "manifest": {}})
    assert blocked.status_code == 409, blocked.text
    assert "osfi-e23" in blocked.json()["detail"]["affected_controls"]


def test_a_200_challenge_page_never_flags_or_blocks_packs(store):
    """D4-R3 over HTTP: an official host swapping in a 200 bot-challenge page
    (visible <noscript> text) is not a change — no flag, packs are not 409 —
    and the real page coming back is not a change either."""
    waf = (b"<html><body><noscript>JavaScript is disabled. In order to continue, "
           b"we need to verify that you're not a robot.</noscript>"
           b"<script>challenge()</script></body></html>")
    client = TestClient(create_app(stale_store=store, fetcher=FakeFetcher()))
    assert client.post("/regwatch/check").json()["exit_code"] == 0
    client.app.state.fetcher = FakeFetcher({SRC_EU_OFFICIAL: waf, SRC_OSFI: waf})
    body = client.post("/regwatch/check").json()
    assert body["flagged"] == [] and body["exit_code"] == 2  # osfi has no mirror
    assert statuses(body)["osfi-e23"] == "unreachable"
    assert statuses(body)["eu-ai-act"] == "baseline"  # fell back to the mirrors
    r = client.post("/pack", json={"signer": "Controller", "manifest": {}})
    assert r.status_code == 200, r.text
    client.app.state.fetcher = FakeFetcher()
    body = client.post("/regwatch/check").json()
    assert body["exit_code"] == 0 and body["flagged"] == []
    assert all(row["flag_active"] is False for row in body["frameworks"])


def test_regwatch_check_401_under_shared_secret(monkeypatch, store):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "synthetic-test-secret")
    client = TestClient(create_app(stale_store=store, fetcher=FakeFetcher()))
    assert client.get("/health").status_code == 200
    assert client.post("/regwatch/check").status_code == 401
    assert client.post("/regwatch/check", headers={"x-field-auth": "wrong"}).status_code == 401
    assert client.get("/staleness").status_code == 401
    r = client.post("/regwatch/check", headers={"x-field-auth": "synthetic-test-secret"})
    assert r.status_code == 200, r.text
    assert store.last_check() is not None


def test_default_store_is_the_flags_file_under_field_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path))
    client = TestClient(create_app(fetcher=FakeFetcher()))
    assert client.post("/regwatch/check").status_code == 200
    on_disk = StaleStore(tmp_path / "crosswalk_stale_flags.json")
    assert set(on_disk.sources()) == {SRC_OSFI, SRC_NIST, SRC_EU_OFFICIAL}


# --- flags can be SET over HTTP, never cleared ------------------------------------

def test_no_http_route_can_clear_staleness(store):
    fetch = FakeFetcher()
    app = create_app(stale_store=store, fetcher=fetch)
    client = TestClient(app)
    client.post("/regwatch/check")  # baseline, so later checks read unchanged

    # 1. no route path names a clearing verb, anywhere on the app
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        for verb in ("clear", "unmark", "unflag", "review", "resolve"):
            assert verb not in path, f"route {path!r} looks like a clear route"

    # 2. /staleness stays GET-only, and every other verb on it is refused
    for route in app.routes:
        if isinstance(route, APIRoute) and "staleness" in route.path:
            assert route.methods == {"GET"}
    assert client.post("/staleness").status_code == 405
    assert client.put("/staleness", json={}).status_code == 405
    assert client.patch("/staleness", json={}).status_code == 405
    assert client.delete("/staleness").status_code == 405

    # 3. POST /regwatch/check with ANY body cannot remove a flag
    store.mark("osfi-e23", "operator-set flag under review")
    (flag,) = store.active()
    bodies = [
        None,
        {"clear": "osfi-e23"},
        {"framework": "osfi-e23", "reviewed_by": "D. Hagell"},
        {"action": "clear", "frameworks": ["osfi-e23"], "force": True},
        {"unmark": True, "reset": True},
        ["osfi-e23"],
        "clear osfi-e23",
    ]
    for body in bodies:
        kwargs = {} if body is None else {"json": body}
        r = client.post("/regwatch/check", **kwargs)
        assert r.status_code == 200, (body, r.text)
        assert StaleStore(store.path).active() == [flag], body
    for query in ("clear=osfi-e23", "reviewed_by=D.+Hagell&framework=osfi-e23"):
        assert client.post(f"/regwatch/check?{query}").status_code == 200
        assert StaleStore(store.path).active() == [flag]
    assert StaleStore(store.path).status()["history"] == []

    # 4. no guessed clear path exists (404/405, never 2xx) and none cleared
    for method in ("post", "put", "delete"):
        for path in ("/staleness/clear", "/regwatch/clear", "/regwatch/osfi-e23",
                     "/staleness/osfi-e23"):
            assert getattr(client, method)(path).status_code in (404, 405)
    assert StaleStore(store.path).active() == [flag]

    # 5. every non-GET route is either the pack/crosswalk renderers or the
    #    check — the complete mutating surface, named
    mutating = sorted(r.path for r in app.routes
                      if isinstance(r, APIRoute) and r.methods - {"GET", "HEAD"})
    assert mutating == ["/crosswalk", "/crosswalk/markdown", "/pack", "/regwatch/check"]


# --- doc drift ---------------------------------------------------------------------

def test_doc_drift_guard_no_stub_citation_wording():
    spec = (SERVICE_ROOT / "SPEC.md").read_text(encoding="utf-8")
    readme = (SERVICE_ROOT / "README.md").read_text(encoding="utf-8")
    demo = (SERVICE_ROOT / "demo.sh").read_text(encoding="utf-8")
    pyproject = tomllib.loads((SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    description = create_app().description

    assert "TODO-CITE" not in spec
    assert "TODO-CITE" not in description
    assert "stub" not in description.lower()
    assert "stub" not in pyproject["project"]["description"].lower()
    assert "ISO/IEC 42001 (pending text purchase)" in pyproject["project"]["description"]
    assert "TODO" not in demo
    assert "pending ingestion" not in demo
    assert "No continuous monitoring" not in spec
    assert "regwatch" in spec and "/regwatch/check" in spec
    assert "does not watch" not in readme
    assert "operator-fed in v0.1" not in readme

    from compliance_crosswalk.cli import regwatch_app

    assert "operator-fed" not in (regwatch_app.info.help or "")


def test_doc_drift_agent_id_optionality_is_an_open_plan_assigned_d4_item():
    """D4-R4: A3 and plan Decisions §2 assign PackRequest optionality by
    agent_id to D4. The docs must say it is an open D4 item that was not
    built — never that it is outside D4's scope."""
    from compliance_crosswalk.api import PackRequest

    readme = (SERVICE_ROOT / "README.md").read_text(encoding="utf-8")
    spec = (SERVICE_ROOT / "SPEC.md").read_text(encoding="utf-8")
    doc = PackRequest.__doc__ or ""
    for text in (readme, " ".join(doc.split()), spec):
        flat = " ".join(text.split())
        assert "does not carry it" not in flat
        assert "plan-assigned D4" in flat
        assert "NOT built" in flat or "not built" in flat
    # and the body really still requires manifest (the docs are not ahead of the code)
    assert PackRequest.model_fields["manifest"].is_required()
