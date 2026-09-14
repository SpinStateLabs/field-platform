"""regwatch tests (v1.2 D4) — content-change detection over the cited sources.

Every test is offline: conftest.py makes the default httpx factory raise, and
each test injects a fake fetcher (or an ``httpx.MockTransport``). The one
live test is marked ``live_fetch`` and runs only with ``CROSSWALK_LIVE_FETCH=1``.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from compliance_crosswalk import __version__, regwatch, staleness
from compliance_crosswalk.mapping import (
    CONTROLS,
    FRAMEWORKS,
    INGESTION_LOG,
    SRC_EU_ART12,
    SRC_EU_ART14,
    SRC_EU_OFFICIAL,
    SRC_NIST,
    SRC_OSFI,
)
from compliance_crosswalk.staleness import StaleStore

ALL_URLS = (SRC_OSFI, SRC_NIST, SRC_EU_OFFICIAL, SRC_EU_ART12, SRC_EU_ART14)

PAGE = (
    "<!DOCTYPE html><html><head><meta name=\"csrf-token\" content=\"{nonce}\">"
    "<title>Regulation</title><script nonce=\"{nonce}\">window.__n='{nonce}';"
    "</script><style>.banner{{color:red}} /* {nonce} */</style></head><body>"
    "<!-- served by edge-{nonce} --><h1>{title}</h1><p>{refs}</p>{pad}<p>{text}</p>"
    "</body></html>"
)
# One cited reference identifier per watched page (D4-R3: a reading must name
# at least one of the references cited from its URL).
REFS = "Principle 1.1 · GOVERN 1.6 · Article 12 · Article 14"


def page(text: str = "The text as verified.", *, title: str = "Article",
         nonce: str = "n0nce-a", pad: str = "", refs: str = REFS) -> bytes:
    return PAGE.format(text=text, title=title, nonce=nonce, pad=pad,
                       refs=refs).encode("utf-8")


class FakeFetcher:
    """url -> bytes | Exception (raised). Unknown URLs get a default page."""

    def __init__(self, pages: dict | None = None, default: bytes | None = None):
        self.pages = dict(pages or {})
        self.default = default if default is not None else page()
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        value = self.pages.get(url, self.default)
        if isinstance(value, BaseException):
            raise value
        return value


def raising(exc: BaseException | None = None) -> FakeFetcher:
    exc = exc or httpx.ConnectError("synthetic: network down")
    return FakeFetcher({u: exc for u in ALL_URLS})


def by_framework(report: dict) -> dict[str, dict]:
    return {row["framework"]: row for row in report["frameworks"]}


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


# --- inventory ------------------------------------------------------------------

def test_inventory_is_derived_from_controls():
    inv = regwatch.inventory()
    assert list(inv) == list(FRAMEWORKS)
    assert inv["osfi-e23"].candidates == (("official", SRC_OSFI),)
    assert inv["nist-ai-rmf"].candidates == (("official", SRC_NIST),)
    assert inv["eu-ai-act"].candidates == (
        ("official", SRC_EU_OFFICIAL),
        ("mirror", SRC_EU_ART12),
        ("mirror", SRC_EU_ART14),
    )
    assert inv["iso-42001"].candidates == ()
    assert inv["iso-42001"].no_source_reason == "pending-purchase"
    for entry in inv.values():
        for _via, url in entry.candidates:
            assert url.startswith("https://")
    # every cited source_url is watched: nothing cited escapes the inventory
    watched = {url for e in inv.values() for _via, url in e.candidates}
    cited = {c.source_url for ctl in CONTROLS for c in ctl.citations.values()
             if c.status == "cited"}
    assert cited <= watched


def test_official_candidate_is_a_watch_url_never_a_citation_source():
    """Citation.source_url records what was read on RETRIEVED — the EUR-Lex
    candidate must not leak into any citation."""
    for control in CONTROLS:
        for citation in control.citations.values():
            assert citation.source_url != SRC_EU_OFFICIAL


def test_mirror_labelled_frameworks_try_an_official_candidate_first():
    for entry in INGESTION_LOG:
        source = (entry.get("source") or "").lower()
        inv = regwatch.inventory()[entry["framework"]]
        if "mirror" in source:
            assert inv.candidates[0] == ("official", regwatch.OFFICIAL_CANDIDATES[entry["framework"]])
        elif "official" in source:
            assert all(via == "official" for via, _ in inv.candidates)


# --- normalisation --------------------------------------------------------------

def test_normalise_strips_script_style_meta_comments_and_collapses_whitespace():
    raw = page(text="Record-keeping   &amp;\n\n logs", nonce="XYZ-123", refs="")
    text = regwatch.normalise(raw)
    assert text == "Regulation Article Record-keeping & logs"
    assert "XYZ-123" not in text
    assert regwatch.content_hash(page(nonce="a", pad="\n   \t")) == \
        regwatch.content_hash(page(nonce="b"))
    assert regwatch.content_hash(page(text="changed")) != regwatch.content_hash(page())


# --- the check ------------------------------------------------------------------

def test_baseline_run_flags_nothing_and_records_sources(store):
    fetch = FakeFetcher()
    report = regwatch.run_check(store, fetch)
    rows = by_framework(report)
    assert report["exit_code"] == regwatch.EXIT_UNCHANGED == 0
    for fw in ("osfi-e23", "nist-ai-rmf", "eu-ai-act"):
        assert rows[fw]["status"] == "baseline", rows[fw]
        assert rows[fw]["flag_active"] is False
    assert rows["eu-ai-act"]["fetched_via"] == "official"
    assert rows["eu-ai-act"]["fallbacks"] == []
    assert rows["iso-42001"]["status"] == "no-source"
    assert rows["iso-42001"]["reason"] == "pending-purchase"
    assert store.active() == []
    assert report["flagged"] == [] and report["unreachable"] == []
    assert set(store.sources()) == {SRC_OSFI, SRC_NIST, SRC_EU_OFFICIAL}
    # the official answer is the reading: the mirrors are not fetched
    assert sorted(fetch.calls) == sorted([SRC_OSFI, SRC_NIST, SRC_EU_OFFICIAL])
    last = StaleStore(store.path).status()["last_check"]
    assert last["checked_at"] == report["checked_at"]
    assert last["trigger"] == "cli" and last["exit_code"] == 0
    assert last["frameworks"] == {"osfi-e23": "baseline", "eu-ai-act": "baseline",
                                  "iso-42001": "no-source", "nist-ai-rmf": "baseline"}


def test_iso_row_is_no_source_with_zero_fetch_attempts(store):
    fetch = FakeFetcher()
    rows = by_framework(regwatch.run_check(store, fetch))
    assert rows["iso-42001"]["sources"] == [] and rows["iso-42001"]["fallbacks"] == []
    assert rows["iso-42001"]["fetched_via"] is None
    assert not any("iso" in url.lower() for url in fetch.calls)
    assert len(fetch.calls) == 3  # osfi, nist, eu official — nothing for iso


def test_changed_bytes_flag_with_url_sha_prefixes_and_byte_diff(store):
    regwatch.run_check(store, FakeFetcher())
    old = store.source_record(SRC_OSFI)
    changed = page(text="The text as verified, now with an amended paragraph.")
    report = regwatch.run_check(store, FakeFetcher({SRC_OSFI: changed}))
    rows = by_framework(report)
    assert report["exit_code"] == regwatch.EXIT_CHANGED == 3
    assert report["flagged"] == ["osfi-e23"]
    assert rows["osfi-e23"]["status"] == "changed"
    assert rows["osfi-e23"]["flag_active"] is True
    assert rows["nist-ai-rmf"]["status"] == "unchanged"
    assert rows["eu-ai-act"]["status"] == "unchanged"
    (flag,) = store.active()
    new = store.source_record(SRC_OSFI)
    diff = len(changed) - old["raw_bytes"]
    assert diff > 0
    assert flag["framework"] == "osfi-e23"
    assert SRC_OSFI in flag["reason"]
    assert old["sha256"][:12] in flag["reason"]
    assert new["sha256"][:12] in flag["reason"]
    assert f"{diff:+d} raw bytes" in flag["reason"]
    (src,) = rows["osfi-e23"]["sources"]
    assert src["byte_diff"] == diff
    assert src["previous_sha256_prefix"] == old["sha256"][:12]
    assert new["previous_sha256"] == old["sha256"]
    assert new["first_seen"] == old["first_seen"]
    # persisted, not just in memory
    assert [f["framework"] for f in StaleStore(store.path).active()] == ["osfi-e23"]


def test_third_run_keeps_flagged_at(store):
    regwatch.run_check(store, FakeFetcher())
    regwatch.run_check(store, FakeFetcher({SRC_NIST: page(text="v2")}))
    (first,) = store.active()
    time.sleep(0.02)
    # the same changed content again: unchanged since the last reading, and
    # the flag stands with its original clock
    report = regwatch.run_check(store, FakeFetcher({SRC_NIST: page(text="v2")}))
    assert by_framework(report)["nist-ai-rmf"]["status"] == "unchanged"
    assert by_framework(report)["nist-ai-rmf"]["flag_active"] is True
    assert report["exit_code"] == 0
    assert store.active() == [first]
    # a further change re-marks: reason moves on, flagged_at does not
    time.sleep(0.02)
    report = regwatch.run_check(store, FakeFetcher({SRC_NIST: page(text="v3")}))
    assert report["exit_code"] == 3
    (third,) = store.active()
    assert third["flagged_at"] == first["flagged_at"]
    assert third["reason"] != first["reason"]


def test_markup_noise_is_not_a_change(store):
    """Nonces in meta/script/style/comments and whitespace churn change the
    raw bytes of a live page every response — they must not flag."""
    regwatch.run_check(store, FakeFetcher({SRC_OSFI: page(nonce="first")}))
    before = store.source_record(SRC_OSFI)
    noisy = page(nonce="second-much-longer-nonce", pad="\n\n    \t  ")
    report = regwatch.run_check(store, FakeFetcher({SRC_OSFI: noisy}))
    assert report["exit_code"] == 0
    assert by_framework(report)["osfi-e23"]["status"] == "unchanged"
    after = store.source_record(SRC_OSFI)
    assert after["raw_sha256"] != before["raw_sha256"]
    assert after["sha256"] == before["sha256"]
    assert store.active() == []


@pytest.mark.parametrize("failure", [
    regwatch.FetchError("HTTP 403"),
    httpx.ReadTimeout("synthetic: timed out"),
])
def test_official_failure_falls_back_to_mirrors_and_says_so(store, failure):
    fetch = FakeFetcher({SRC_EU_OFFICIAL: failure})
    report = regwatch.run_check(store, fetch)
    eu = by_framework(report)["eu-ai-act"]
    assert eu["status"] == "baseline"
    assert eu["fetched_via"] == "mirror"
    assert [s["url"] for s in eu["sources"]] == [SRC_EU_ART12, SRC_EU_ART14]
    assert all(s["via"] == "mirror" and s["status"] == "baseline" for s in eu["sources"])
    (fallback,) = eu["fallbacks"]
    assert fallback["url"] == SRC_EU_OFFICIAL and fallback["via"] == "official"
    assert type(failure).__name__ in fallback["error"]
    assert report["exit_code"] == 0  # a fallback that read the mirrors is a reading
    assert report["unreachable"] == []
    assert store.active() == []
    assert SRC_EU_OFFICIAL not in store.sources()


def test_switching_between_official_and_mirror_is_not_a_change(store):
    regwatch.run_check(store, FakeFetcher())  # official baseline
    report = regwatch.run_check(store, FakeFetcher({SRC_EU_OFFICIAL: regwatch.FetchError("HTTP 403")}))
    assert by_framework(report)["eu-ai-act"]["status"] == "baseline"  # mirrors first read
    report = regwatch.run_check(store, FakeFetcher())  # official answers again
    assert by_framework(report)["eu-ai-act"]["status"] == "unchanged"
    assert report["exit_code"] == 0 and store.active() == []


def test_all_fetches_raising_is_unreachable_never_changed(store):
    report = regwatch.run_check(store, raising())
    rows = by_framework(report)
    assert report["exit_code"] == regwatch.EXIT_UNREACHABLE == 2
    assert store.active() == [] and report["flagged"] == []
    for fw in ("osfi-e23", "nist-ai-rmf", "eu-ai-act"):
        assert rows[fw]["status"] == "unreachable"
        assert rows[fw]["fetched_via"] is None
    assert set(report["unreachable"]) == {SRC_OSFI, SRC_NIST, SRC_EU_ART12, SRC_EU_ART14}
    assert rows["eu-ai-act"]["fallbacks"][0]["url"] == SRC_EU_OFFICIAL
    assert rows["iso-42001"]["status"] == "no-source"
    assert store.sources() == {}  # nothing read, nothing stored
    assert store.last_check()["exit_code"] == 2


def test_unreachable_after_baseline_keeps_hashes_and_flags_nothing(store):
    regwatch.run_check(store, FakeFetcher())
    hashes = store.sources()
    report = regwatch.run_check(store, raising())
    assert report["exit_code"] == 2 and store.active() == []
    assert store.sources() == hashes
    # and the next good reading of the same content is unchanged, not changed
    assert regwatch.run_check(store, FakeFetcher())["exit_code"] == 0


def test_partial_mirror_unreachable_is_exit_2(store):
    fetch = FakeFetcher({SRC_EU_OFFICIAL: regwatch.FetchError("HTTP 403"),
                         SRC_EU_ART14: httpx.ConnectError("synthetic")})
    report = regwatch.run_check(store, fetch)
    eu = by_framework(report)["eu-ai-act"]
    assert eu["status"] == "baseline" and eu["fetched_via"] == "mirror"
    assert {s["url"]: s["status"] for s in eu["sources"]} == {
        SRC_EU_ART12: "baseline", SRC_EU_ART14: "unreachable"}
    assert report["unreachable"] == [SRC_EU_ART14]
    assert report["exit_code"] == 2


def test_change_wins_over_unreachable_exit_3(store):
    regwatch.run_check(store, FakeFetcher())
    fetch = FakeFetcher({SRC_OSFI: page(text="amended"),
                         SRC_NIST: httpx.ConnectError("synthetic")})
    report = regwatch.run_check(store, fetch)
    assert report["exit_code"] == 3
    assert report["flagged"] == ["osfi-e23"] and report["unreachable"] == [SRC_NIST]


def test_a_page_with_no_visible_text_is_unreachable_not_a_change(store):
    regwatch.run_check(store, FakeFetcher())
    interstitial = b"<html><head><script>challenge()</script></head><body> </body></html>"
    report = regwatch.run_check(store, FakeFetcher({SRC_OSFI: interstitial}))
    osfi = by_framework(report)["osfi-e23"]
    assert osfi["status"] == "unreachable"
    assert "no visible text" in osfi["sources"][0]["error"]
    assert report["exit_code"] == 2 and store.active() == []


CHALLENGE = (b"<html><head><title>Just a moment...</title></head><body><noscript>"
             b"JavaScript is disabled. In order to continue, we need to verify that "
             b"you're not a robot.</noscript><script>challenge()</script></body></html>")


def test_anchors_are_derived_from_the_cited_references():
    inv = regwatch.inventory()
    anchors = {url: set(a) for e in inv.values() for url, a in e.anchors}
    assert anchors[SRC_OSFI] == {"Principle 1.1", "Principle 1.2", "Principle 2.1",
                                 "Principle 3.6"}
    assert anchors[SRC_NIST] == {"GOVERN 1.6", "GOVERN 2.1", "GOVERN 2.3",
                                 "GOVERN 6.1", "MANAGE 2.4"}
    assert anchors[SRC_EU_ART12] == {"Article 12"}
    assert anchors[SRC_EU_ART14] == {"Article 14"}
    assert anchors[SRC_EU_OFFICIAL] == {"Article 12", "Article 14"}
    # every watched URL has at least one anchor, each a cited reference prefix
    for entry in inv.values():
        assert {url for _via, url in entry.candidates} == {url for url, _ in entry.anchors}
    for control in CONTROLS:
        for c in control.citations.values():
            if c.status == "cited":
                assert c.reference.startswith(regwatch.anchor_of(c.reference))
    assert regwatch.anchor_of("Principle 1.2 / §B.2 — third parties") == "Principle 1.2"
    # whole-token, case-insensitive matching
    assert regwatch.has_anchor("see govern 1.6: inventory", ("GOVERN 1.6",))
    assert not regwatch.has_anchor("Principle 1.10 only", ("Principle 1.1",))
    assert not regwatch.has_anchor("Article 120", ("Article 12",))
    # a URL with no derivable anchor fails closed: never an unanchored reading
    obs = regwatch._observe("osfi-e23", "official", SRC_OSFI, FakeFetcher(), ())
    assert obs["ok"] is False and "no anchor" in obs["error"]


def test_a_200_challenge_page_with_visible_text_is_unreachable_not_a_change(store):
    """D4-R3. A WAF / bot-challenge interstitial served with 200 carries
    visible text, but names none of the cited references: it must not flag
    the framework (and so hard-block packs), and the real page coming back
    must not flag it a second time."""
    assert regwatch.normalise(CHALLENGE)  # it HAS visible text
    regwatch.run_check(store, FakeFetcher())
    hashes = store.sources()

    report = regwatch.run_check(store, FakeFetcher({SRC_OSFI: CHALLENGE, SRC_NIST: CHALLENGE}))
    rows = by_framework(report)
    for fw in ("osfi-e23", "nist-ai-rmf"):
        assert rows[fw]["status"] == "unreachable", rows[fw]
        assert "anchor missing" in rows[fw]["sources"][0]["error"]
        assert rows[fw]["flag_active"] is False
    assert report["exit_code"] == 2 and report["flagged"] == []
    assert store.active() == []
    for url in (SRC_OSFI, SRC_NIST):  # the stored readings are untouched
        assert store.source_record(url) == hashes[url]

    report = regwatch.run_check(store, FakeFetcher())  # the real pages are back
    assert report["exit_code"] == 0 and store.active() == []
    assert by_framework(report)["osfi-e23"]["status"] == "unchanged"


def test_a_challenge_page_on_the_official_eu_url_falls_back_to_the_mirrors(store):
    regwatch.run_check(store, FakeFetcher())  # official baseline
    report = regwatch.run_check(store, FakeFetcher({SRC_EU_OFFICIAL: CHALLENGE}))
    eu = by_framework(report)["eu-ai-act"]
    assert eu["fetched_via"] == "mirror" and eu["status"] == "baseline"
    (fallback,) = eu["fallbacks"]
    assert fallback["url"] == SRC_EU_OFFICIAL and "anchor missing" in fallback["error"]
    assert report["exit_code"] == 0 and store.active() == []
    report = regwatch.run_check(store, FakeFetcher())
    assert by_framework(report)["eu-ai-act"]["status"] == "unchanged"
    assert store.active() == []


def test_a_page_that_keeps_one_cited_reference_still_reads_as_changed(store):
    """ANY anchor, not ALL: a real edit that drops some cited references but
    keeps one is a content change that flags — never downgraded to
    unreachable."""
    regwatch.run_check(store, FakeFetcher())
    trimmed = page(text="An amended paragraph under the new numbering.",
                   refs="Principle 2.1")
    report = regwatch.run_check(store, FakeFetcher({SRC_OSFI: trimmed}))
    assert by_framework(report)["osfi-e23"]["status"] == "changed"
    assert report["exit_code"] == 3 and report["flagged"] == ["osfi-e23"]


def test_injected_fetcher_is_capped_too(store, monkeypatch):
    monkeypatch.setattr(regwatch, "MAX_BYTES", 64)
    report = regwatch.run_check(store, FakeFetcher())  # pages are > 64 bytes
    assert report["exit_code"] == 2
    assert "cap" in by_framework(report)["osfi-e23"]["sources"][0]["error"]


def test_single_flight_a_second_check_fetches_nothing_until_the_first_returns(tmp_path):
    """D4-R2. An HTTP-triggered check and a scheduler tick never fan out to
    the third-party hosts in parallel: the second check makes no fetch call
    while the first is still running."""
    entered, release = threading.Event(), threading.Event()
    second_called = threading.Event()
    first_calls: list[str] = []
    second_calls: list[str] = []

    def blocking_fetch(url):
        first_calls.append(url)
        entered.set()
        assert release.wait(timeout=30), "test never released the first check"
        return page()

    def second_fetch(url):
        second_calls.append(url)
        second_called.set()
        return page()

    results: dict = {}
    first = threading.Thread(target=lambda: results.update(
        first=regwatch.run_check(StaleStore(tmp_path / "a.json"), blocking_fetch,
                                 trigger="scheduler")), daemon=True)
    second = threading.Thread(target=lambda: results.update(
        second=regwatch.run_check(StaleStore(tmp_path / "b.json"), second_fetch,
                                  trigger="http")), daemon=True)
    first.start()
    assert entered.wait(timeout=30), "the first check never fetched"
    second.start()
    # the second check is parked on the single-flight lock: no fetch at all
    assert not second_called.wait(timeout=1.0), f"parallel fetch: {second_calls}"
    assert second.is_alive() and second_calls == []
    release.set()
    first.join(timeout=30)
    second.join(timeout=30)
    assert not first.is_alive() and not second.is_alive()
    assert results["first"]["exit_code"] == 0 and results["second"]["exit_code"] == 0
    assert len(second_calls) == 3  # it ran in full once the first returned


def test_without_an_injected_fetcher_tests_stay_offline(store):
    """The conftest guard: the default fetcher's client factory raises, so
    every source is unreachable — never a network call."""
    report = regwatch.run_check(store)
    assert report["exit_code"] == 2
    assert "NetworkRefused" in by_framework(report)["osfi-e23"]["sources"][0]["error"]


# --- the store transaction: a named clear is never overwritten --------------------

def test_scheduler_store_does_not_overwrite_a_named_clear(store):
    """The scheduler holds a long-lived StaleStore whose memory still shows
    the flag; the CLI (another instance / process) clears it by name. The
    next check must re-load before writing, or the flag would resurrect."""
    regwatch.run_check(store, FakeFetcher())
    regwatch.run_check(store, FakeFetcher({SRC_OSFI: page(text="amended")}))
    assert [f["framework"] for f in store.active()] == ["osfi-e23"]
    StaleStore(store.path).clear("osfi-e23", "D. Hagell")  # the CLI's instance
    regwatch.run_check(store, FakeFetcher({SRC_OSFI: page(text="amended")}))
    fresh = StaleStore(store.path)
    assert fresh.active() == []
    assert [h["reviewed_by"] for h in fresh.status()["history"]] == ["D. Hagell"]


def test_clear_during_the_fetch_window_survives_the_write(store):
    regwatch.run_check(store, FakeFetcher())
    regwatch.run_check(store, FakeFetcher({SRC_NIST: page(text="amended")}))

    class ClearsMidFetch(FakeFetcher):
        def __call__(self, url):
            if url == SRC_OSFI:
                StaleStore(store.path).clear("nist-ai-rmf", "D. Hagell")
            return super().__call__(url)

    regwatch.run_check(store, ClearsMidFetch({SRC_NIST: page(text="amended")}))
    assert StaleStore(store.path).active() == []


def test_mark_reloads_before_write(tmp_path):
    path = tmp_path / "flags.json"
    s1 = StaleStore(path)
    s1.mark("osfi-e23", "first")
    StaleStore(path).clear("osfi-e23", "D. Hagell")
    s1.mark("nist-ai-rmf", "second")  # s1's memory still holds osfi
    assert [f["framework"] for f in StaleStore(path).active()] == ["nist-ai-rmf"]


def _cli_subprocess(args: list[str], data_dir) -> subprocess.Popen:
    """The real ``crosswalk`` CLI in a SEPARATE process (as ``docker exec``
    runs it on an estate), importing the same source tree as this test."""
    src = str(Path(staleness.__file__).resolve().parents[1])
    env = dict(os.environ, FIELD_DATA_DIR=str(data_dir), PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join(p for p in (src, os.environ.get("PYTHONPATH")) if p))
    return subprocess.Popen([sys.executable, "-m", "compliance_crosswalk.cli", *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", env=env)


def test_cli_clear_in_another_process_during_a_check_write_is_not_lost(tmp_path):
    """D4-R1. A check's transaction is between its re-load and its persist
    when the CLI — another PROCESS — runs a named clear. The clear must wait
    for the OS store lock and then apply: the flag stays cleared and the
    named review stays in history. (With only a thread lock + re-load, the
    CLI clear lands mid-transaction and the persist resurrects the flag and
    erases the review.)"""
    data_dir = tmp_path / "data"
    path = data_dir / "crosswalk_stale_flags.json"
    regwatch.run_check(StaleStore(path), FakeFetcher())
    regwatch.run_check(StaleStore(path), FakeFetcher({SRC_OSFI: page(text="amended")}))
    assert [f["framework"] for f in StaleStore(path).active()] == ["osfi-e23"]

    seen: dict = {}

    class ClearsFromTheCliMidTransaction(StaleStore):
        def put_source_record(self, url, record):
            if "proc" not in seen:
                proc = _cli_subprocess(["regwatch", "clear", "osfi-e23",
                                        "--reviewed-by", "D. Hagell"], data_dir)
                seen["proc"] = proc
                # Wait until the CLI reports it is blocked on the store lock
                # (EOF first = it finished without waiting: the bug).
                seen["waiting"] = False
                for line in proc.stderr:
                    if "waiting for the store lock" in line:
                        seen["waiting"] = True
                        break
                seen["alive_while_we_hold_the_lock"] = proc.poll() is None
            super().put_source_record(url, record)

    report = regwatch.run_check(ClearsFromTheCliMidTransaction(path),
                                FakeFetcher({SRC_OSFI: page(text="amended")}))
    proc = seen["proc"]
    out, err = proc.communicate(timeout=120)
    assert seen["waiting"], f"the CLI clear did not wait for the store lock: {out!r} {err!r}"
    assert seen["alive_while_we_hold_the_lock"]
    assert proc.returncode == 0, err
    assert "cleared: osfi-e23 re-reviewed by D. Hagell" in out
    assert report["exit_code"] == 0 and report["flagged"] == []
    after = StaleStore(path)
    assert after.active() == [], "the scheduler write resurrected a named clear"
    (review,) = after.status()["history"]
    assert review["reviewed_by"] == "D. Hagell" and review["flag"]["framework"] == "osfi-e23"
    # the check's own write survived too: nothing was lost in either direction
    assert after.last_check()["checked_at"] == report["checked_at"]
    assert SRC_OSFI in after.sources()


def test_a_writer_waits_for_the_os_lock_and_times_out_loudly(tmp_path, monkeypatch):
    """The OS lock excludes a second handle (another process, or another fd in
    this one); a writer that cannot get it within the timeout raises and
    writes nothing."""
    path = tmp_path / "flags.json"
    StaleStore(path).mark("nist-ai-rmf", "operator")
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(staleness, "LOCK_TIMEOUT_SECONDS", 0.3)
    with staleness._file_lock(StaleStore(path).lock_path, 5):
        with pytest.raises(staleness.StoreLockTimeout, match="nothing was written"):
            StaleStore(path).mark("osfi-e23", "second writer")
        with pytest.raises(staleness.StoreLockTimeout):
            StaleStore(path).clear("nist-ai-rmf", "D. Hagell")
    assert path.read_text(encoding="utf-8") == before
    StaleStore(path).clear("nist-ai-rmf", "D. Hagell")  # lock released: proceeds
    assert StaleStore(path).active() == []


def test_each_persist_uses_its_own_temp_file_and_leaves_none_behind(tmp_path, monkeypatch):
    path = tmp_path / "flags.json"
    replaced: list[str] = []
    real_replace = os.replace

    def spy(src, dst):
        replaced.append(str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    StaleStore(path).mark("osfi-e23", "one")
    StaleStore(path).mark("nist-ai-rmf", "two")
    assert len(replaced) == 2 and replaced[0] != replaced[1]
    assert all(Path(s).parent == tmp_path and Path(s).name != "flags.json.tmp"
               for s in replaced)

    def failing(src, dst):
        raise OSError("synthetic: replace failed")

    monkeypatch.setattr(os, "replace", failing)
    with pytest.raises(OSError, match="synthetic"):
        StaleStore(path).mark("eu-ai-act", "three")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["flags.json", "flags.json.lock"]
    assert [f["framework"] for f in StaleStore(path).active()] == ["nist-ai-rmf", "osfi-e23"]


def test_pre_d4_flags_file_loads_and_keeps_its_flags(tmp_path):
    path = tmp_path / "flags.json"
    path.write_text(json.dumps({
        "corpus_version": "corpus-2026-08-08",
        "active": {"eu-ai-act": {"framework": "eu-ai-act", "flagged_at":
                                 "2026-09-01T00:00:00+00:00", "reason": "operator",
                                 "new_version": None}},
        "history": [],
    }), encoding="utf-8")
    s = StaleStore(path)
    assert s.sources() == {} and s.status()["last_check"] is None
    regwatch.run_check(s, FakeFetcher())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"corpus_version", "active", "history", "sources", "last_check"}
    assert data["active"]["eu-ai-act"]["flagged_at"] == "2026-09-01T00:00:00+00:00"


# --- default fetcher (offline, through httpx.MockTransport) ------------------------

def _mock_factory(monkeypatch, handler):
    monkeypatch.setattr(regwatch, "_client_factory",
                        lambda: regwatch.build_http_client(httpx.MockTransport(handler)))


def test_default_fetcher_sends_user_agent_and_no_platform_auth(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "synthetic-secret-never-sent")
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=page())

    _mock_factory(monkeypatch, handler)
    assert regwatch.default_fetcher(SRC_OSFI) == page()
    (request,) = seen
    assert request.headers["user-agent"] == f"field-platform-crosswalk/{__version__}"
    assert "x-field-auth" not in request.headers
    assert "synthetic-secret-never-sent" not in json.dumps(dict(request.headers))


def test_default_fetcher_client_configuration():
    client = regwatch.build_http_client()
    try:
        assert client.timeout.read == regwatch.TIMEOUT_SECONDS == 20
        assert client.follow_redirects is True
        assert client.headers["user-agent"] == regwatch.USER_AGENT
        assert "x-field-auth" not in client.headers
    finally:
        client.close()
    assert regwatch.MAX_BYTES == 8 * 1024 * 1024


def test_regwatch_never_uses_platform_auth_headers():
    assert "auth_headers" not in inspect.getsource(regwatch)


def test_default_fetcher_non_200_raises(monkeypatch):
    _mock_factory(monkeypatch, lambda request: httpx.Response(403, content=b"denied"))
    with pytest.raises(regwatch.FetchError, match="HTTP 403"):
        regwatch.default_fetcher(SRC_EU_OFFICIAL)


def test_default_fetcher_refuses_plain_http_without_sending(monkeypatch):
    seen = []
    _mock_factory(monkeypatch, lambda r: seen.append(r) or httpx.Response(200, content=page()))
    with pytest.raises(regwatch.FetchError, match="https only"):
        regwatch.default_fetcher("http://www.osfi-bsif.gc.ca/")
    assert seen == []


def test_default_fetcher_refuses_a_redirect_off_https_before_sending_it(monkeypatch):
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.scheme == "https":
            return httpx.Response(302, headers={"location": "http://mirror.example/a12"})
        return httpx.Response(200, content=page())

    _mock_factory(monkeypatch, handler)
    with pytest.raises(regwatch.FetchError, match="https only"):
        regwatch.default_fetcher(SRC_EU_ART12)
    assert seen == [SRC_EU_ART12]  # the http:// hop was never sent


def test_default_fetcher_caps_declared_and_streamed_bodies(monkeypatch):
    monkeypatch.setattr(regwatch, "MAX_BYTES", 64)
    _mock_factory(monkeypatch, lambda r: httpx.Response(200, content=b"x" * 65))
    with pytest.raises(regwatch.FetchError, match="cap"):
        regwatch.default_fetcher(SRC_NIST)

    def chunked(request):
        return httpx.Response(200, content=iter([b"x" * 40, b"x" * 40]))

    _mock_factory(monkeypatch, chunked)
    with pytest.raises(regwatch.FetchError, match="cap"):
        regwatch.default_fetcher(SRC_NIST)
    _mock_factory(monkeypatch, lambda r: httpx.Response(200, content=b"x" * 64))
    assert regwatch.default_fetcher(SRC_NIST) == b"x" * 64


def test_default_fetcher_refuses_an_over_declared_body_before_reading_it(monkeypatch):
    monkeypatch.setattr(regwatch, "MAX_BYTES", 64)
    pulled: list[int] = []

    def body():
        for _ in range(4):
            pulled.append(1)
            yield b"x" * 40

    _mock_factory(monkeypatch, lambda r: httpx.Response(
        200, headers={"content-length": "160"}, content=body()))
    with pytest.raises(regwatch.FetchError, match="content-length 160"):
        regwatch.default_fetcher(SRC_NIST)
    assert pulled == []  # not one chunk of a declared-oversize body was read


# --- CLI ----------------------------------------------------------------------------

def _cli():
    from compliance_crosswalk.cli import app

    return app


def test_cli_check_fetch_exit_codes_0_3_2(monkeypatch, tmp_path):
    runner = CliRunner()
    flags = tmp_path / "data" / "crosswalk_stale_flags.json"  # conftest FIELD_DATA_DIR

    monkeypatch.setattr(regwatch, "default_fetcher", FakeFetcher())
    result = runner.invoke(_cli(), ["regwatch", "check", "--fetch"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["exit_code"] == 0
    assert flags.exists()

    monkeypatch.setattr(regwatch, "default_fetcher", FakeFetcher({SRC_NIST: page(text="amended")}))
    result = runner.invoke(_cli(), ["regwatch", "check", "--fetch"])
    assert result.exit_code == 3, result.output
    assert "STALE: nist-ai-rmf" in result.stderr

    monkeypatch.setattr(regwatch, "default_fetcher", raising())
    result = runner.invoke(_cli(), ["regwatch", "check", "--fetch"])
    assert result.exit_code == 2, result.output
    # unreachable never cleared the standing flag
    assert [f["framework"] for f in StaleStore(flags).active()] == ["nist-ai-rmf"]


def test_cli_check_names_standing_flags_even_when_it_exits_0(monkeypatch, tmp_path):
    """D4-R5. A workstation cron sees exit 0 on a re-read of already-changed
    content; exit 0 means "no NEW change", so the standing flag (which still
    blocks packs) must be named on stderr."""
    runner = CliRunner()
    flags = tmp_path / "data" / "crosswalk_stale_flags.json"  # conftest FIELD_DATA_DIR
    monkeypatch.setattr(regwatch, "default_fetcher", FakeFetcher())
    assert runner.invoke(_cli(), ["regwatch", "check", "--fetch"]).exit_code == 0
    amended = FakeFetcher({SRC_NIST: page(text="amended")})
    monkeypatch.setattr(regwatch, "default_fetcher", amended)
    first = runner.invoke(_cli(), ["regwatch", "check", "--fetch"])
    assert first.exit_code == 3 and "STALE (standing)" not in first.stderr
    StaleStore(flags).mark("osfi-e23", "operator: consultation published")

    result = runner.invoke(_cli(), ["regwatch", "check", "--fetch"])  # same content
    assert result.exit_code == 0, result.output
    assert "STALE (standing): osfi-e23, nist-ai-rmf" in result.stderr
    assert "NEW changes only" in result.stderr
    body = json.loads(result.stdout)
    assert {r["framework"] for r in body["frameworks"] if r["flag_active"]} == {
        "osfi-e23", "nist-ai-rmf"}

    StaleStore(flags).clear("osfi-e23", "D. Hagell")
    StaleStore(flags).clear("nist-ai-rmf", "D. Hagell")
    clean = runner.invoke(_cli(), ["regwatch", "check", "--fetch"])
    assert clean.exit_code == 0 and "STALE" not in clean.stderr


def test_cli_check_without_fetch_reads_nothing(monkeypatch):
    fetch = FakeFetcher()
    monkeypatch.setattr(regwatch, "default_fetcher", fetch)
    result = CliRunner().invoke(_cli(), ["regwatch", "check"])
    assert result.exit_code == 0, result.output
    assert fetch.calls == []
    body = json.loads(result.stdout)
    rows = {r["framework"]: r for r in body["frameworks"]}
    assert rows["iso-42001"]["status"] == "no-source"
    assert [c["via"] for c in rows["eu-ai-act"]["candidates"]] == ["official", "mirror", "mirror"]
    assert body["last_check"] is None
    assert "no fetch performed" in result.stderr


def test_serve_reads_every_from_flag_and_env(monkeypatch):
    import uvicorn

    captured = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.append(app))
    runner = CliRunner()
    assert runner.invoke(_cli(), ["serve"]).exit_code == 0
    assert runner.invoke(_cli(), ["serve"], env={"FIELD_CROSSWALK_EVERY": "86400"}).exit_code == 0
    assert runner.invoke(_cli(), ["serve", "--every", "-5"]).exit_code == 0
    assert [a.state.every for a in captured] == [0, 86400, 0]


# --- scheduler ----------------------------------------------------------------------

def test_run_every_ticks_on_a_short_interval_and_survives_an_exception():
    calls = []

    def tick():
        calls.append(time.monotonic())
        if len(calls) == 1:
            raise RuntimeError("synthetic: a bad day at a third-party host")

    stop = threading.Event()
    thread = threading.Thread(target=regwatch.run_every, args=(tick, 0.01, stop), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while len(calls) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=5)
    assert len(calls) >= 3, "the loop died after the raising tick"
    assert not thread.is_alive()


def test_run_every_first_tick_after_the_interval_and_stops():
    events = []
    stop = threading.Event()

    def sleep(seconds):
        events.append(("sleep", seconds))
        if len([e for e in events if e[0] == "tick"]) == 2:
            stop.set()

    ticks = regwatch.run_every(lambda: events.append(("tick", None)), 86400, stop, sleep=sleep)
    assert events[0] == ("sleep", 86400)
    assert events == [("sleep", 86400), ("tick", None), ("sleep", 86400),
                      ("tick", None), ("sleep", 86400)]
    assert ticks == 2


def test_scheduled_check_swallows_and_logs_exceptions(caplog):
    def broken_store():
        raise OSError("synthetic: data volume unavailable")

    assert regwatch.scheduled_check(broken_store, FakeFetcher()) is None
    assert "scheduled check failed" in caplog.text


def test_served_scheduler_runs_a_check_after_the_interval(store):
    from fastapi.testclient import TestClient

    from compliance_crosswalk.api import create_app

    app = create_app(stale_store=store, fetcher=FakeFetcher(), every=2)
    with TestClient(app) as client:
        assert client.get("/health").json()["every"] == 2
        assert app.state.scheduler_thread is not None and app.state.scheduler_thread.daemon
        assert client.get("/staleness").json()["last_check"] is None  # not at start
        deadline = time.monotonic() + 20
        last = None
        while time.monotonic() < deadline:
            last = client.get("/staleness").json()["last_check"]
            if last:
                break
            time.sleep(0.1)
    assert last is not None, "the scheduler never ran a check"
    assert last["trigger"] == "scheduler"
    assert last["frameworks"]["osfi-e23"] == "baseline"
    app.state.scheduler_thread.join(timeout=5)
    assert not app.state.scheduler_thread.is_alive()  # shutdown stops it


def test_every_zero_arms_nothing(store):
    from fastapi.testclient import TestClient

    from compliance_crosswalk.api import create_app

    app = create_app(stale_store=store)
    with TestClient(app) as client:
        assert client.get("/health").json()["every"] == 0
    assert app.state.scheduler_thread is None


# --- live (manual proof) -----------------------------------------------------------

@pytest.mark.live_fetch
def test_live_fetch_reads_the_real_sources(tmp_path, capsys):
    """CROSSWALK_LIVE_FETCH=1 only. First proof that httpx with the planned
    User-Agent reads OSFI, NIST and the EU text (official, or the mirrors
    with the fallback reported)."""
    report = regwatch.run_check(StaleStore(tmp_path / "live.json"), trigger="live-test")
    rows = by_framework(report)
    with capsys.disabled():
        for row in report["frameworks"]:
            print(f"\n{row['framework']}: {row['status']} via {row['fetched_via']} "
                  f"fallbacks={row['fallbacks']} sources="
                  f"{[(s['url'], s['status'], s.get('raw_bytes'), s.get('error')) for s in row['sources']]}")
    for fw in ("osfi-e23", "nist-ai-rmf", "eu-ai-act"):
        assert rows[fw]["status"] == "baseline", rows[fw]
    assert rows["iso-42001"]["status"] == "no-source"
