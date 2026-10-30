"""C-389 (reviewer C-387 F-C387-1): a page that spells a cited identifier differently flags the framework on every
run, `clear` does not end it, and the operator needs the procedure. The behaviour the README's procedure rests on is
pinned here, and the procedure itself is pinned in the README text."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.mapping import SRC_EU_OFFICIAL, SRC_OSFI
from compliance_crosswalk.staleness import StaleStore

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def all_refs():
    return sorted({a for e in regwatch.inventory().values() for _u, anchors in e.anchors for a in anchors})


def page(refs):
    return ("<html><body><h1>R</h1><p>" + " · ".join(refs) + "</p></body></html>").encode()


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


def fetcher(pages):
    full = page(all_refs())
    return lambda url: pages.get(url, full)


def respelled(identifier: str) -> list[str]:
    """Every identifier on the page, with one of them spelled the way a source might ("Article 12" -> "Art. 12")."""
    return [a for a in all_refs() if a != identifier] + [identifier.replace("Article ", "Art. ").replace("Principle ", "Princ. ")]


@pytest.mark.parametrize("url,framework,identifier", [
    (SRC_EU_OFFICIAL, "eu-ai-act", "Article 12"),
    (SRC_OSFI, "osfi-e23", "Principle 2.1"),
])
def test_a_respelled_identifier_flags_every_run_and_clear_does_not_end_it(store, url, framework, identifier):
    f = fetcher({url: page(respelled(identifier))})
    first = regwatch.run_check(store, f)
    assert framework in first["flagged"]
    reason = {x["framework"]: x for x in store.active()}[framework]["reason"]
    assert identifier in reason and "not on the page" in reason and url in reason
    store.clear(framework, "D. Hagell")
    assert store.active() == []
    again = regwatch.run_check(store, f)
    assert framework in again["flagged"] and framework in {x["framework"] for x in store.active()}


def test_the_status_view_lists_the_identifiers_the_mapping_expects_for_each_url(store):
    rows = regwatch.inventory_report(store)
    rows = rows["frameworks"] if isinstance(rows, dict) and "frameworks" in rows else rows
    osfi = next(r for r in rows if r["framework"] == "osfi-e23")
    listed = {c["url"]: c["anchors"] for c in osfi["candidates"]}
    assert listed[SRC_OSFI] == list(dict(regwatch.inventory()["osfi-e23"].anchors)[SRC_OSFI])
    eu = next(r for r in rows if r["framework"] == "eu-ai-act")
    assert {c["url"]: c["anchors"] for c in eu["candidates"]}[SRC_EU_OFFICIAL] == ["Article 12", "Article 14"]


def test_a_page_that_now_carries_every_identifier_is_one_content_change_then_clean(store):
    """If the SOURCE page is corrected, the first check after is an ordinary content change (the hash differs from the
    respelled page): re-review and clear once; a second check of the same page is clean. A respelled page that the
    source keeps is the case that flags every run (above)."""
    regwatch.run_check(store, fetcher({SRC_OSFI: page(respelled("Principle 2.1"))}))
    store.clear("osfi-e23", "D. Hagell")
    fixed = regwatch.run_check(store, fetcher({}))
    reason = {x["framework"]: x for x in store.active()}["osfi-e23"]["reason"]
    assert "osfi-e23" in fixed["flagged"] and "normalised sha256" in reason and "not on the page" not in reason
    store.clear("osfi-e23", "D. Hagell")
    assert "osfi-e23" not in regwatch.run_check(store, fetcher({}))["flagged"]
    assert store.active() == []


# --- the README states the procedure -------------------------------------------------------------------------


def _procedure() -> str:
    m = re.search(r"A flag for a missing identifier: what an operator does \(C-389\)\.(.*?)(?=\n- \*\*|\n## )", README, re.S)
    assert m, "the README no longer has the operator procedure for a missing-identifier flag"
    return " ".join(m.group(1).split())


@pytest.mark.parametrize("phrase", [
    "flags the framework on every run",
    "blocks packs",
    "`regwatch clear` does not end it",
    "names the missing identifier(s) and the URL",
    "`regwatch check` (no `--fetch`) lists the identifiers the mapping expects",
    "the fix is a change to the mapping's cited identifier",
    "`regwatch clear <framework> --reviewed-by NAME`",
    "re-review the cited text",
])
def test_the_readme_procedure_says(phrase):
    assert phrase in _procedure()


def test_the_signer_row_of_the_readme_states_the_rule():
    row = next(ln for ln in README.splitlines() if ln.startswith("| No pack ships without a named signer"))
    for phrase in ("200 characters", "invisible-format", "line-break", "exit 2", "422"):
        assert phrase in row, phrase
