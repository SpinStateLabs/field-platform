"""``crosswalk regwatch check-file`` — the manual path for a page a named human
saved from a browser (Don's decision 2026-09-13: OSFI answers HTTP 403 to the
honest crosswalk User-Agent, and a spoofed browser UA is bot-detection
evasion).

What is pinned here:

* the file is hashed with the SAME normalisation and anchor rule as a fetch,
  and a fetch and a file of the same bytes are interchangeable readings;
* baseline / unchanged / changed are recorded exactly like ``check``, the
  change flags the framework, and the reading is ``via manual:<NAME>`` with
  the file's sha256;
* a file that is not HTML, is empty, or is over the 8 MB cap is refused, as
  are a page that is not a reading and bad arguments — nothing written;
* it never clears a flag, never touches ``last_check``, re-loads before it
  writes, and has no HTTP route.

Offline: conftest.py makes the default httpx factory raise.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from compliance_crosswalk import regwatch
from compliance_crosswalk.api import create_app
from compliance_crosswalk.mapping import (
    SRC_EU_ART12,
    SRC_EU_ART14,
    SRC_EU_OFFICIAL,
    SRC_NIST,
    SRC_OSFI,
)
from compliance_crosswalk.staleness import StaleStore

HUMAN = "D. Hagell"

# A browser "Save Page As… (HTML only)" of the OSFI guideline: a saved-from
# comment and a doctype, per-response noise in markup, the cited identifiers.
SAVED = (
    "<!-- saved from url=(0092){url} -->\n"
    "<!DOCTYPE html><html lang=\"en\"><head><meta name=\"csrf\" content=\"{nonce}\">"
    "<script>window.__n='{nonce}'</script><title>Guideline E-23</title></head>"
    "<body><h1>Guideline E-23 – Model Risk Management</h1>"
    "<p>Principle 1.1 · Principle 1.2 · Principle 2.1 · Principle 3.6</p>"
    "<p>{text}</p></body></html>"
)


def saved_page(text: str = "Institutions should manage model risk.", *,
               nonce: str = "n-1", url: str = SRC_OSFI) -> bytes:
    return SAVED.format(text=text, nonce=nonce, url=url).encode("utf-8")


def write(path, data: bytes):
    path.write_bytes(data)
    return path


@pytest.fixture
def store(tmp_path):
    return StaleStore(tmp_path / "flags.json")


def _fetcher(pages: dict[str, bytes], default: bytes):
    def fetch(url: str) -> bytes:
        return pages.get(url, default)
    return fetch


# --- the reading ---------------------------------------------------------------------

def test_baseline_then_unchanged_then_changed_like_check(store, tmp_path):
    first = write(tmp_path / "osfi-e23.html", saved_page())
    report = regwatch.check_file("osfi-e23", first, HUMAN, store=store)
    assert report["status"] == "baseline" and report["exit_code"] == 0
    assert report["url"] == SRC_OSFI
    assert report["fetched_via"] == report["via"] == f"manual:{HUMAN}"
    assert report["file_sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert report["flag_active"] is False
    record = StaleStore(store.path).source_record(SRC_OSFI)
    assert record["via"] == f"manual:{HUMAN}"
    assert record["fetched_by"] == HUMAN
    assert record["file_sha256"] == report["file_sha256"]
    assert record["sha256"] == regwatch.content_hash(first.read_bytes())
    assert StaleStore(store.path).active() == []

    # same text, different per-response markup noise: not a change
    again = write(tmp_path / "osfi-e23-again.htm", saved_page(nonce="n-2"))
    report = regwatch.check_file("osfi-e23", again, HUMAN, store=store)
    assert report["status"] == "unchanged" and report["exit_code"] == 0
    assert report["file_sha256"] != hashlib.sha256(first.read_bytes()).hexdigest()

    amended = write(tmp_path / "osfi-e23-amended.html",
                    saved_page("Institutions must manage model risk."))
    report = regwatch.check_file("osfi-e23", amended, "A. Reviewer", store=store)
    assert report["status"] == "changed" and report["exit_code"] == 3
    assert report["flag_active"] is True
    assert report["previous_sha256_prefix"] == record["sha256"][:12]
    (flag,) = StaleStore(store.path).active()
    assert flag["framework"] == "osfi-e23"
    assert SRC_OSFI in flag["reason"] and "via manual:A. Reviewer" in flag["reason"]
    assert "manual file" in flag["reason"]


def test_a_file_hashes_exactly_like_a_fetch_of_the_same_bytes(tmp_path):
    body = saved_page()
    fetched = StaleStore(tmp_path / "fetched.json")
    regwatch.run_check(fetched, _fetcher({}, body))
    manual = StaleStore(tmp_path / "manual.json")
    regwatch.check_file("osfi-e23", write(tmp_path / "p.html", body), HUMAN, store=manual)
    by_fetch = StaleStore(fetched.path).source_record(SRC_OSFI)
    by_file = StaleStore(manual.path).source_record(SRC_OSFI)
    for key in ("sha256", "raw_sha256", "raw_bytes"):
        assert by_fetch[key] == by_file[key], key
    assert by_file["raw_sha256"] == by_file["file_sha256"]


def test_fetch_and_file_readings_compare_against_each_other(tmp_path):
    body = saved_page()
    # baseline by fetch, then a file of the same page: unchanged, no flag
    store = StaleStore(tmp_path / "a.json")
    regwatch.run_check(store, _fetcher({}, body))
    same = regwatch.check_file("osfi-e23", write(tmp_path / "same.html", body), HUMAN,
                               store=store)
    assert same["status"] == "unchanged" and StaleStore(store.path).active() == []
    # baseline by file, then a fetch that reads different text: changed, flagged
    other = StaleStore(tmp_path / "b.json")
    regwatch.check_file("osfi-e23", write(tmp_path / "base.html", body), HUMAN, store=other)
    report = regwatch.run_check(other, _fetcher({SRC_OSFI: saved_page("Amended.")}, body))
    rows = {r["framework"]: r for r in report["frameworks"]}
    assert rows["osfi-e23"]["status"] == "changed"
    assert [f["framework"] for f in StaleStore(other.path).active()] == ["osfi-e23"]


def test_eu_needs_url_and_records_only_that_url(store, tmp_path):
    art12 = ("<!doctype html><html><body><h1>Article 12</h1><p>Record-keeping.</p>"
             "</body></html>").encode()
    path = write(tmp_path / "art12.html", art12)
    with pytest.raises(regwatch.ManualFileRefused, match="watches 3 URLs; pass --url"):
        regwatch.check_file("eu-ai-act", path, HUMAN, store=store)
    report = regwatch.check_file("eu-ai-act", path, HUMAN, url=SRC_EU_ART12, store=store)
    assert report["status"] == "baseline" and report["url"] == SRC_EU_ART12
    sources = StaleStore(store.path).sources()
    assert set(sources) == {SRC_EU_ART12}
    assert SRC_EU_ART14 not in sources and SRC_EU_OFFICIAL not in sources


# --- refusals: nothing written --------------------------------------------------------

def _assert_nothing_written(store):
    assert not store.path.exists(), "a refused check-file wrote the store"


@pytest.mark.parametrize("name, data, message", [
    ("osfi-e23.pdf", saved_page(), "not HTML"),
    ("osfi-e23.mhtml", saved_page(), "not HTML"),
    ("osfi-e23.txt", saved_page(), "not HTML"),
    ("osfi-e23", saved_page(), "not HTML"),
    ("osfi-e23.html", b"%PDF-1.7\n%synthetic not a page\n", "not HTML"),
    ("osfi-e23.html", b"Principle 1.1 plain text, no markup", "not HTML"),
    ("osfi-e23.html", "<!doctype html><html>Principle 1.1</html>".encode("utf-16"), "NUL bytes"),
    ("osfi-e23.html", b"", "empty file"),
], ids=["pdf", "mhtml", "txt", "no-suffix", "pdf-bytes", "plain-text", "utf-16", "empty"])
def test_a_file_that_is_not_html_or_is_empty_is_refused(store, tmp_path, name, data, message):
    path = write(tmp_path / name, data)
    with pytest.raises(regwatch.ManualFileRefused, match=message):
        regwatch.check_file("osfi-e23", path, HUMAN, store=store)
    _assert_nothing_written(store)


def test_a_file_over_the_8_mb_fetch_cap_is_refused_before_it_is_read(store, tmp_path, monkeypatch):
    assert regwatch.MAX_BYTES == 8 * 1024 * 1024
    head = saved_page()
    path = tmp_path / "huge.html"
    with path.open("wb") as handle:
        handle.write(head)
        handle.write(b" " * (regwatch.MAX_BYTES + 1 - len(head)))
    assert path.stat().st_size == regwatch.MAX_BYTES + 1
    opened = []
    real_open = type(path).open
    monkeypatch.setattr(type(path), "open",
                        lambda self, *a, **k: opened.append(self) or real_open(self, *a, **k))
    with pytest.raises(regwatch.ManualFileRefused, match="over the 8388608-byte cap"):
        regwatch.check_file("osfi-e23", path, HUMAN, store=store)
    assert path not in opened, "an over-cap file was opened"
    _assert_nothing_written(store)


def test_a_file_that_grows_past_the_cap_after_stat_is_still_refused(store, tmp_path,
                                                                    monkeypatch):
    """The size check before reading is not the only one: the read itself is
    capped, so a file that grows between stat and read is still refused."""
    body = saved_page()
    path = write(tmp_path / "growing.html", body + b" " * 64)
    monkeypatch.setattr(regwatch, "MAX_BYTES", len(body))
    real_stat = type(path).stat

    def stat_before_growth(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == path:
            fields = list(result)
            fields[6] = len(body)  # st_size as it was when stat ran
            return type(result)(fields)
        return result

    monkeypatch.setattr(type(path), "stat", stat_before_growth)
    # the read's own message (the normaliser's cap in _observe is a backstop)
    with pytest.raises(regwatch.ManualFileRefused,
                       match=f"^over the {len(body)}-byte cap: "):
        regwatch.check_file("osfi-e23", path, HUMAN, store=store)
    _assert_nothing_written(store)


def test_the_cap_boundary_is_the_fetchers(store, tmp_path, monkeypatch):
    """Same rule as the fetcher (``len > MAX_BYTES`` refused): a file of
    exactly the cap is read, one byte more is not."""
    body = saved_page()
    monkeypatch.setattr(regwatch, "MAX_BYTES", len(body) + 1)
    at_cap = write(tmp_path / "at.html", body + b" ")
    assert regwatch.check_file("osfi-e23", at_cap, HUMAN, store=store)["status"] == "baseline"
    over = write(tmp_path / "over.html", body + b"  ")
    with pytest.raises(regwatch.ManualFileRefused, match="cap"):
        regwatch.check_file("osfi-e23", over, HUMAN, store=store)


@pytest.mark.parametrize("make, message", [
    (lambda d: d / "missing.html", "cannot read"),
    (lambda d: (d / "folder.html").mkdir() or d / "folder.html", "not a regular file"),
], ids=["missing", "directory"])
def test_a_path_that_is_not_a_readable_file_is_refused(store, tmp_path, make, message):
    with pytest.raises(regwatch.ManualFileRefused, match=message):
        regwatch.check_file("osfi-e23", make(tmp_path), HUMAN, store=store)
    _assert_nothing_written(store)


@pytest.mark.parametrize("data, message", [
    (b"<!doctype html><html><body><h1>Verify you are human</h1>"
     b"<p>Checking your browser before accessing osfi-bsif.gc.ca.</p></body></html>",
     "anchor missing"),
    (b"<!doctype html><html><head><script>location.reload()</script></head></html>",
     "no visible text"),
    (b"<!doctype html><html><body><p>Principle 1.10 only</p></body></html>",
     "anchor missing"),
], ids=["challenge-page", "script-only", "near-miss-identifier"])
def test_a_saved_page_that_is_not_a_reading_is_refused_and_never_flags(
        store, tmp_path, data, message):
    baseline = regwatch.check_file("osfi-e23", write(tmp_path / "ok.html", saved_page()),
                                   HUMAN, store=store)
    before = store.path.read_bytes()
    with pytest.raises(regwatch.ManualFileRefused, match=message):
        regwatch.check_file("osfi-e23", write(tmp_path / "bad.html", data), HUMAN, store=store)
    assert store.path.read_bytes() == before
    assert StaleStore(store.path).active() == []
    assert baseline["status"] == "baseline"


@pytest.mark.parametrize("framework, kwargs, message", [
    ("osfi", {}, "unknown framework"),
    ("iso-42001", {}, "no-source"),
    ("osfi-e23", {"url": SRC_NIST}, "is not watched for osfi-e23"),
    ("osfi-e23", {"url": SRC_OSFI + "?x=1"}, "is not watched for osfi-e23"),
    ("osfi-e23", {"fetched_by": ""}, "must name the human"),
    ("osfi-e23", {"fetched_by": "   "}, "must name the human"),
    ("osfi-e23", {"fetched_by": "D. Hagell\nreviewed_by: someone"}, "plain name"),
    # integration review R5(b): Unicode that is invisible or breaks a line, and no-letter names
    ("osfi-e23", {"fetched_by": "\u200b"}, "plain name"),
    ("osfi-e23", {"fetched_by": "D. Hagell\u2028reviewed_by: someone"}, "plain name"),
    ("osfi-e23", {"fetched_by": "D. Hagell\u2029x"}, "plain name"),
    ("osfi-e23", {"fetched_by": "D.\u200bHagell"}, "plain name"),
    ("osfi-e23", {"fetched_by": "D. Hagell\u0085x"}, "plain name"),
    ("osfi-e23", {"fetched_by": "\ufeffD. Hagell"}, "plain name"),
    ("osfi-e23", {"fetched_by": "- . -"}, "letter or digit"),
], ids=["unknown", "iso-no-source", "other-url", "url-near-miss", "blank-name",
        "whitespace-name", "newline-name", "zero-width-space-only", "line-separator",
        "paragraph-separator", "zero-width-space-inside", "nel", "bom", "no-letter-or-digit"])
def test_bad_arguments_are_refused_and_write_nothing(store, tmp_path, framework, kwargs,
                                                     message):
    path = write(tmp_path / "osfi-e23.html", saved_page())
    fetched_by = kwargs.pop("fetched_by", HUMAN)
    with pytest.raises(regwatch.ManualFileRefused, match=message):
        regwatch.check_file(framework, path, fetched_by, store=store, **kwargs)
    _assert_nothing_written(store)


# --- never clears, never touches last_check, re-loads before write ------------------------

def test_check_file_never_clears_a_flag_and_never_touches_last_check(store, tmp_path):
    body = saved_page()
    regwatch.run_check(store, _fetcher({}, body))
    last_check = StaleStore(store.path).last_check()
    assert last_check is not None
    store.mark("osfi-e23", "operator: consultation published")
    (flag,) = StaleStore(store.path).active()

    report = regwatch.check_file("osfi-e23", write(tmp_path / "same.html", body), HUMAN,
                                 store=StaleStore(store.path))
    assert report["status"] == "unchanged" and report["flag_active"] is True
    after = StaleStore(store.path)
    assert after.active() == [flag]
    assert after.status()["history"] == []
    assert after.last_check() == last_check


def test_a_clear_persisted_after_the_store_was_loaded_survives(store, tmp_path):
    """check-file writes through ``StaleStore.transaction`` (re-load first),
    so a named clear written by another process after this instance loaded
    is kept, never resurrected."""
    regwatch.check_file("osfi-e23", write(tmp_path / "a.html", saved_page()), HUMAN,
                        store=store)
    store.mark("osfi-e23", "operator flag")
    stale_instance = StaleStore(store.path)          # loads the active flag
    StaleStore(store.path).clear("osfi-e23", HUMAN)  # e.g. the CLI, elsewhere
    regwatch.check_file("osfi-e23", write(tmp_path / "b.html", saved_page()), HUMAN,
                        store=stale_instance)
    final = StaleStore(store.path)
    assert final.active() == []
    assert [h["reviewed_by"] for h in final.status()["history"]] == [HUMAN]


def test_check_file_has_no_http_route(store):
    """The manual path is CLI-only: an HTTP upload would make the named human
    self-asserted by any holder of the perimeter secret. The mutating route
    set stays exactly what test_no_http_route_can_clear_staleness names."""
    app = create_app(stale_store=store, fetcher=_fetcher({}, saved_page()))
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        assert "file" not in path and "manual" not in path, path
    mutating = sorted(r.path for r in app.routes
                      if isinstance(r, APIRoute) and r.methods - {"GET", "HEAD"})
    assert mutating == ["/crosswalk", "/crosswalk/markdown", "/pack", "/regwatch/check"]
    client = TestClient(app)
    for path in ("/regwatch/check-file", "/regwatch/check_file", "/regwatch/manual"):
        assert client.post(path, content=saved_page()).status_code in (404, 405)


# --- CLI ------------------------------------------------------------------------------

def _cli():
    from compliance_crosswalk.cli import app

    return app


def test_cli_check_file_exit_codes_0_3_2(tmp_path):
    runner = CliRunner()
    flags = tmp_path / "data" / "crosswalk_stale_flags.json"  # conftest FIELD_DATA_DIR
    page = write(tmp_path / "osfi-e23.html", saved_page())
    args = ["regwatch", "check-file", "osfi-e23", "--file", str(page), "--fetched-by", HUMAN]

    result = runner.invoke(_cli(), args)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["status"] == "baseline" and body["fetched_via"] == f"manual:{HUMAN}"
    assert body["file_sha256"] == hashlib.sha256(page.read_bytes()).hexdigest()
    assert f"proves only what {HUMAN} saved" in result.stderr
    assert StaleStore(flags).source_record(SRC_OSFI)["via"] == f"manual:{HUMAN}"

    amended = write(tmp_path / "amended.html", saved_page("Amended text."))
    result = runner.invoke(_cli(), ["regwatch", "check-file", "osfi-e23", "--file",
                                    str(amended), "--fetched-by", HUMAN])
    assert result.exit_code == 3, result.output
    assert "STALE: osfi-e23" in result.stderr
    assert [f["framework"] for f in StaleStore(flags).active()] == ["osfi-e23"]

    # the same amended page again: no NEW change, the standing flag is named
    result = runner.invoke(_cli(), ["regwatch", "check-file", "osfi-e23", "--file",
                                    str(amended), "--fetched-by", HUMAN])
    assert result.exit_code == 0, result.output
    assert "STALE (standing): osfi-e23" in result.stderr

    before = flags.read_bytes()
    pdf = write(tmp_path / "osfi-e23.pdf", b"%PDF-1.7 synthetic")
    result = runner.invoke(_cli(), ["regwatch", "check-file", "osfi-e23", "--file",
                                    str(pdf), "--fetched-by", HUMAN])
    assert result.exit_code == 2, result.output
    assert "REFUSED (nothing written): not HTML" in result.stderr
    assert result.stdout == ""
    assert flags.read_bytes() == before


def test_cli_check_file_requires_a_named_human(tmp_path):
    page = write(tmp_path / "osfi-e23.html", saved_page())
    runner = CliRunner()
    missing = runner.invoke(_cli(), ["regwatch", "check-file", "osfi-e23", "--file", str(page)])
    assert missing.exit_code == 2
    blank = runner.invoke(_cli(), ["regwatch", "check-file", "osfi-e23", "--file", str(page),
                                   "--fetched-by", "  "])
    assert blank.exit_code == 2 and "must name the human" in blank.stderr
    assert not (tmp_path / "data" / "crosswalk_stale_flags.json").exists()


def test_the_manual_reading_is_readable_later_while_last_check_keeps_the_automated_result(tmp_path):
    """Integration review R5(a): check-file leaves ``last_check`` as the last
    automated check (OSFI ``unreachable``), so the D-gate's OSFI evidence is
    the stored source record. ``regwatch check`` without ``--fetch`` prints it:
    the via ``manual:<NAME>``, who saved it and the file's sha256."""
    runner = CliRunner()
    flags = tmp_path / "data" / "crosswalk_stale_flags.json"  # conftest FIELD_DATA_DIR
    body = saved_page()

    others = (b"<html><body><p>GOVERN 1.6 GOVERN 2.1 MANAGE 2.4 Article 12 Article 14</p>"
              b"<p>Synthetic page text.</p></body></html>")

    def forbidden(url: str) -> bytes:
        if url == SRC_OSFI:
            raise regwatch.FetchError("HTTP 403 (simulated)")
        return others

    regwatch.run_check(StaleStore(flags), forbidden)
    page = write(tmp_path / "osfi-e23.html", body)
    assert runner.invoke(_cli(), ["regwatch", "check-file", "osfi-e23", "--file", str(page),
                                  "--fetched-by", HUMAN]).exit_code == 0

    shown = runner.invoke(_cli(), ["regwatch", "check"])
    assert shown.exit_code == 0, shown.output
    report = json.loads(shown.stdout)
    (osfi,) = [row for row in report["frameworks"] if row["framework"] == "osfi-e23"]
    (candidate,) = osfi["candidates"]
    assert candidate["stored_via"] == f"manual:{HUMAN}" and candidate["fetched_by"] == HUMAN
    assert candidate["file_sha256"] == hashlib.sha256(body).hexdigest()
    assert report["last_check"]["frameworks"]["osfi-e23"] == "unreachable"
    (nist,) = [row for row in report["frameworks"] if row["framework"] == "nist-ai-rmf"]
    assert nist["candidates"][0]["stored_via"] == "official"
    assert nist["candidates"][0]["fetched_by"] is None and nist["candidates"][0]["file_sha256"] is None
