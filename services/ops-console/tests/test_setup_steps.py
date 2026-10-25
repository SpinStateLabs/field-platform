"""The Setup area of the ops console: the step registry and the page's safety rules.

The page is one static HTML file (no static route, air-gapped), so these are HTML/text tests: they parse
the registry data block and the setup script, and they pin the rules the area must keep (a view per
placed step, unique slugs, no external requests, no API data parsed as markup, nothing persisted, the
real refusal codes documented).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ops_console
from ops_console.api import ServiceClient, create_app

HTML = (Path(ops_console.__file__).parent / "static" / "console.html").read_text(encoding="utf-8")

#: Placement decision (DECISIONS-FOR-DON P10): the ops console is primary for these quickstart steps.
PLACED = {
    "register-agent": "1",
    "mint-token": "2",
    "sentinel-check": "3",
    "attest-pack": "5",
    "read-ledger": "6",
}
#: Portal-only steps: they must NOT be built here.
PORTAL_ONLY_IDS = {"roster-scopes", "anthropic-key", "api-key", "environment", "governed-call",
                   "console-boundaries"}


def _doc() -> dict:
    m = re.search(r'<script type="application/json" id="setup-steps">(.*?)</script>', HTML, re.S)
    assert m, "setup step registry block missing"
    return json.loads(m.group(1))


def _setup_script() -> str:
    m = re.search(r"/\* SETUP:BEGIN.*?/\* SETUP:END \*/", HTML, re.S)
    assert m, "setup script markers missing"
    return m.group(0)


def _section(slug: str) -> str:
    m = re.search(r'<section id="step-%s" class="setup-step".*?</section>' % re.escape(slug), HTML, re.S)
    assert m, f"no view for step {slug}"
    return m.group(0)


def test_registry_has_exactly_the_placed_steps_in_guide_order():
    steps = _doc()["steps"]
    assert [s["id"] for s in steps] == list(PLACED)
    assert {s["id"]: s["num"] for s in steps} == PLACED
    assert not PORTAL_ONLY_IDS & {s["id"] for s in steps}


def test_slugs_and_aliases_are_unique_and_route_safe():
    steps = _doc()["steps"]
    names = [s["slug"] for s in steps] + [a for s in steps for a in s.get("aliases", [])]
    assert len(names) == len(set(names))
    assert "overview" not in names
    for n in names:
        assert re.fullmatch(r"[a-z0-9-]+", n), n
    # ids equal slugs so the two console surfaces cannot drift apart on step ids
    assert all(s["id"] == s["slug"] for s in steps)


def test_every_placed_step_has_a_view_stepper_entry_and_required_copy():
    for s in _doc()["steps"]:
        sec = _section(s["slug"])
        for hook in ("data-title", "data-purpose", "data-see", "data-fail"):
            assert hook in sec, (s["slug"], hook)
        assert s["purpose"].strip() and s["see"] and s["fail"], s["slug"]
        assert all(f["code"] and f["text"] for f in s["fail"])
    assert 'id="step-overview"' in HTML
    assert 'id="setup-stepper-list"' in HTML


def test_portal_only_steps_are_not_built_here():
    doc = _doc()
    portal_titles = " ".join(p["title"] for p in doc["portalOnly"])
    for needle in ("roster scopes", "Anthropic key", "API key", "governed LLM call", "policy"):
        assert needle.lower() in portal_titles.lower()
    # no views and no calls for them
    assert 'id="step-governed-call"' not in HTML and 'id="step-roster-scopes"' not in HTML
    script = _setup_script()
    assert "/gateway/" not in script and "x-api-key" not in script and "/api/v1" not in script


def test_the_real_refusal_codes_are_documented_on_the_right_steps():
    by_id = {s["id"]: s for s in _doc()["steps"]}

    def codes(step):
        return " ".join(f["code"] + " " + f["text"] for f in by_id[step]["fail"])

    for step in ("register-agent", "mint-token"):
        assert "401" in codes(step) and "403" in codes(step)
    assert "D.grantor" in codes("mint-token") and "D.scope" in codes("mint-token")
    assert "422" in codes("register-agent") and "409" in codes("register-agent")
    assert "R.unregistered" in codes("sentinel-check") and "E.spend_cap" in codes("sentinel-check")
    assert "404" in codes("read-ledger")
    assert "attest verify board-pack.json --pubkey attest-sign.pub.pem" in json.dumps(by_id["attest-pack"])


def test_commands_carry_no_secret_values_and_no_portal_gateway_shapes():
    blob = json.dumps(_doc())
    assert "x-api-key" not in blob and "/api/v1" not in blob and "ff_live_" not in blob
    # operator headers are named, but only ever from shell variables
    assert "x-field-operator: $OPERATOR" in blob and "x-field-operator-key: $OPERATOR_KEY" in blob
    assert not re.search(r"x-field-operator-key: (?!\$)", blob)


def test_no_external_requests_in_the_setup_area():
    doc_json = json.dumps(_doc())
    assert not re.search(r"https?://", doc_json)
    script = _setup_script()
    # the only absolute-URL-looking thing allowed is a regex that scrubs them
    assert not re.search(r"""(fetch|src=|href=|import\s*\()\s*\(?\s*["']https?:""", script)
    views = HTML[HTML.index('<div id="setup-view"'):HTML.index('<script type="application/json"')]
    assert not re.search(r"""(src|href|action)\s*=\s*["']\s*(https?:)?//""", views)
    mine = (views + script).lower()
    assert "@import" not in mine and "cdn" not in mine and "googleapis" not in mine and "gstatic" not in mine
    # every request path the area makes is a same-origin absolute path
    for path in re.findall(r'sfetch\(\s*"([^"]+)"', script) + re.findall(r'(?<![\w])"(/(?:registry|delegation|sentinel|attest|ledger|lifecycle)/[^"?]*)', script):
        assert path.startswith("/"), path


def test_api_data_never_reaches_the_page_as_markup():
    script = _setup_script()
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert banned not in script, banned
    assert "textContent" in script
    # the only places a value is set as a DOM property are form values / option values / attributes
    assert ".insertBefore(" in script  # DOM nodes only


def test_nothing_secret_is_stored_logged_or_put_in_a_url():
    script = _setup_script()
    assert "localStorage" not in script and "sessionStorage" not in script
    assert "console.log" not in script and "console.debug" not in script
    # operator values are only ever read through the console's own header helper
    assert "x-field-operator" not in script and "OPKEY" not in script.replace("signedIn() { return !!(OPID && OPKEY); }", "")
    # no request path is built from the operator id or key
    assert not re.search(r"""["'`]/[^"'`]*\$\{?\s*OP(ID|KEY)""", script)
    assert not re.search(r"\+\s*OP(ID|KEY)\b.*\?", script)


def test_honest_states_are_wired():
    script = _setup_script()
    assert "Not signed in as an operator" in script
    assert "operator credentials required" in script
    assert "operator not authorised" in script
    assert "No sweep recorded yet" in script  # lifecycle 404 before the first sweep
    assert "NOT checked here" in script       # the console never claims it verified a signature
    assert "are withheld" in script or "withheld" in script  # host internals are scrubbed
    assert "address withheld" in script and "host withheld" in script


def test_hash_routes_exist_for_every_step():
    script = _setup_script()
    assert 'location.hash' in script and '"hashchange"' in script
    assert '"#setup/" + s.slug' in script


def test_existing_dashboard_hooks_are_untouched():
    for ident in ("agents", "tokens", "escalations", "usage", "platform", "harness", "h-agent", "h-token",
                  "h-action", "h-irr", "verdict", "events", "ledger-filter", "f-agent", "f-type", "older",
                  "bulk-result", "sel-count", "halt", "halt-go", "drawer", "d-details", "opid", "opkey",
                  "opstate", "secretbar", "secret", "integrity", "mode", "stamp"):
        assert f'id="{ident}"' in HTML, ident
    for fn in ("saveOperator()", "clearOperator()", "runCheck(event)", "openHalt()", "applyFilter(event)"):
        assert fn in HTML, fn
    assert "x-field-operator-key" in HTML and "sessionStorage" in HTML


def test_console_still_serves_the_page_with_the_setup_area():
    class Dead:
        def get(self, *a, **k):
            raise ConnectionError("down")

        post = get

    dead = ServiceClient(client=Dead(), base_url="http://dead")
    c = TestClient(create_app(registry=dead, ledger=dead, delegation=dead, governor=dead,
                              killswitch=dead, sentinel=dead))
    r = c.get("/")
    assert r.status_code == 200
    assert 'id="setup-view"' in r.text and 'id="setup-steps"' in r.text
    assert r.text == HTML
