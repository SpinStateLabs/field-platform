"""C-255 (reviewer C-232 P4, decided under Don's standing authority): a reading must carry EVERY cited identifier.

`has_anchor` accepted a page naming ANY one identifier cited from its URL, so a rewrite that kept one cited article
and dropped the others read as an ordinary page. A page that is a reading (it names at least one identifier: a
challenge page names none) but lacks some of the cited identifiers now flags the framework stale, with the missing
identifiers named in the reason, whether or not its hash changed. A page naming none stays `unreachable`
(`anchor missing`), never a change."""

from __future__ import annotations

import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.evidence_pack import StalePackError, generate_pack
from compliance_crosswalk.mapping import SRC_EU_ART12, SRC_EU_ART14, SRC_EU_OFFICIAL, SRC_NIST, SRC_OSFI
from compliance_crosswalk.staleness import StaleStore
from field_core.templates_api import template_data


def anchors_of(framework: str, url: str) -> tuple[str, ...]:
    return dict(regwatch.inventory()[framework].anchors)[url]


def all_refs() -> list[str]:
    return sorted({a for e in regwatch.inventory().values() for _u, anchors in e.anchors for a in anchors})


def page(refs, text="The text as verified."):
    body = " · ".join(refs)
    return (f"<html><body><h1>Regulation</h1><p>{body}</p><p>{text}</p></body></html>").encode()


class Fetcher:
    """url -> bytes; unknown URLs get the full page (every identifier)."""

    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.default = page(all_refs())

    def __call__(self, url):
        return self.pages.get(url, self.default)


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


def framework_row(report, framework):
    return next(r for r in report["frameworks"] if r["framework"] == framework)


def manifest():
    data = template_data("default")
    data["agent"]["name"] = "pack-test-agent"
    data["agent"]["description"] = "x"
    data["identity"]["principal"] = "Controller"
    data["identity"]["org"] = "Org"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller"
    data["delegation"]["scope"] = ["x"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


# --- the unit ------------------------------------------------------------------------------------------


def test_missing_anchors_lists_exactly_the_absent_identifiers_in_order():
    text = "see Principle 1.1 and principle 2.1 only"
    assert regwatch.missing_anchors(text, ("Principle 1.1", "Principle 1.2", "Principle 2.1", "Principle 3.6")) \
        == ["Principle 1.2", "Principle 3.6"]
    assert regwatch.missing_anchors(text, ()) == []


def test_missing_anchors_is_whole_token_and_case_insensitive():
    assert regwatch.missing_anchors("Principle 1.10 only", ("Principle 1.1",)) == ["Principle 1.1"]
    assert regwatch.missing_anchors("Article 120", ("Article 12",)) == ["Article 12"]
    assert regwatch.missing_anchors("see govern   1.6: inventory", ("GOVERN 1.6",)) == []


def test_has_anchor_is_still_the_any_gate():
    assert regwatch.has_anchor("Principle 1.1", ("Principle 1.1", "Principle 3.6"))
    assert not regwatch.has_anchor("nothing cited", ("Principle 1.1", "Principle 3.6"))
    assert not regwatch.has_anchor("anything", ())


# --- the check -----------------------------------------------------------------------------------------


def test_a_page_with_every_identifier_baselines_and_flags_nothing(store):
    report = regwatch.run_check(store, Fetcher())
    assert report["flagged"] == [] and store.active() == []
    osfi = framework_row(report, "osfi-e23")
    assert osfi["status"] == "baseline"
    assert "missing_anchors" not in osfi["sources"][0]


def test_a_page_missing_one_identifier_flags_the_framework_and_names_it(store):
    osfi = list(anchors_of("osfi-e23", SRC_OSFI))
    assert len(osfi) >= 2
    dropped = osfi[-1]
    keep = [a for a in all_refs() if a != dropped]
    report = regwatch.run_check(store, Fetcher({SRC_OSFI: page(keep)}))
    row = framework_row(report, "osfi-e23")
    assert row["status"] == "changed" and "osfi-e23" in report["flagged"]
    assert row["sources"][0]["missing_anchors"] == [dropped]
    active = {f["framework"]: f for f in store.active()}
    assert "osfi-e23" in active and dropped in active["osfi-e23"]["reason"]
    assert "not on the page" in active["osfi-e23"]["reason"]
    assert report["exit_code"] == regwatch.EXIT_CHANGED


def test_a_flag_from_a_missing_identifier_blocks_the_evidence_pack(store):
    dropped = anchors_of("osfi-e23", SRC_OSFI)[0]
    regwatch.run_check(store, Fetcher({SRC_OSFI: page([a for a in all_refs() if a != dropped])}))
    with pytest.raises(StalePackError):
        generate_pack(manifest(), signer="Ann Lee", stale_store=store)


def test_a_page_missing_every_identifier_is_unreachable_not_a_flag(store):
    report = regwatch.run_check(store, Fetcher({SRC_OSFI: b"<html><body>verify you are human</body></html>"}))
    row = framework_row(report, "osfi-e23")
    assert row["status"] == "unreachable" and "anchor missing" in row["sources"][0]["error"]
    assert store.active() == [] and "osfi-e23" not in report["flagged"]


def test_a_page_missing_one_identifier_is_flagged_again_on_the_next_run_and_after_a_clear(store):
    dropped = anchors_of("osfi-e23", SRC_OSFI)[0]
    pages = {SRC_OSFI: page([a for a in all_refs() if a != dropped])}
    regwatch.run_check(store, Fetcher(pages))
    second = regwatch.run_check(store, Fetcher(pages))
    assert "osfi-e23" in second["flagged"]                      # same hash, still missing: still flagged
    assert framework_row(second, "osfi-e23")["sources"][0]["status"] == "unchanged"
    store.clear("osfi-e23", "D. Hagell")
    assert store.active() == []
    third = regwatch.run_check(store, Fetcher(pages))
    assert "osfi-e23" in third["flagged"]                       # until the mapping is re-ingested


def test_a_hash_change_and_a_missing_identifier_give_one_combined_reason(store):
    regwatch.run_check(store, Fetcher())
    dropped = anchors_of("osfi-e23", SRC_OSFI)[0]
    report = regwatch.run_check(store, Fetcher({SRC_OSFI: page([a for a in all_refs() if a != dropped], "new text")}))
    reason = {f["framework"]: f for f in store.active()}["osfi-e23"]["reason"]
    assert "normalised sha256" in reason and dropped in reason and "not on the page" in reason
    assert framework_row(report, "osfi-e23")["sources"][0]["status"] == "changed"


def test_the_official_eu_url_must_carry_both_articles(store):
    art12, art14 = "Article 12", "Article 14"
    assert set(anchors_of("eu-ai-act", SRC_EU_OFFICIAL)) == {art12, art14}
    only12 = page([a for a in all_refs() if a != art14])
    report = regwatch.run_check(store, Fetcher({SRC_EU_OFFICIAL: only12}))
    row = framework_row(report, "eu-ai-act")
    assert row["status"] == "changed" and row["fetched_via"] == "official"
    assert art14 in {f["framework"]: f for f in store.active()}["eu-ai-act"]["reason"]


def test_a_mirror_page_naming_its_single_identifier_is_complete(store):
    assert anchors_of("eu-ai-act", SRC_EU_ART12) == ("Article 12",)
    pages = {SRC_EU_OFFICIAL: OSError("down"), SRC_EU_ART12: page(["Article 12"]), SRC_EU_ART14: page(["Article 14"])}

    def fetch(url):
        value = pages.get(url, Fetcher().default)
        if isinstance(value, Exception):
            raise value
        return value

    report = regwatch.run_check(store, fetch)
    row = framework_row(report, "eu-ai-act")
    assert row["fetched_via"] == "mirror" and row["status"] == "baseline"
    assert "eu-ai-act" not in report["flagged"]


def test_nist_needs_every_cited_identifier_too(store):
    nist = list(anchors_of("nist-ai-rmf", SRC_NIST))
    assert len(nist) >= 2
    report = regwatch.run_check(store, Fetcher({SRC_NIST: page([a for a in all_refs() if a != nist[0]])}))
    assert "nist-ai-rmf" in report["flagged"]


# --- the manual path -----------------------------------------------------------------------------------


def test_a_saved_page_missing_one_identifier_flags_through_check_file(store, tmp_path):
    dropped = anchors_of("osfi-e23", SRC_OSFI)[0]
    f = tmp_path / "osfi-e23.html"
    f.write_bytes(b"<!doctype html>" + page([a for a in all_refs() if a != dropped]))
    report = regwatch.check_file("osfi-e23", f, "D. Hagell", store=store)
    assert report["exit_code"] == regwatch.EXIT_CHANGED
    assert dropped in {x["framework"]: x for x in store.active()}["osfi-e23"]["reason"]


def test_a_saved_page_with_every_identifier_is_a_clean_baseline(store, tmp_path):
    f = tmp_path / "osfi-e23.html"
    f.write_bytes(b"<!doctype html>" + page(all_refs()))
    report = regwatch.check_file("osfi-e23", f, "D. Hagell", store=store)
    assert report["exit_code"] == 0 and store.active() == []
