"""The board pack's "Source query" cells are clickable links, one per recorded query (Don, 2026-11-06). The text of a
link is the query exactly as recorded; the href is its URL; a ``;``-joined list is split one per line; anything that is
not a ``GET http(s)://`` entry is escaped text, never a link. Mutants: L1 the cell printed as one escaped string again;
L2 the joined list not split; L3 a non-http scheme turned into a link; L4 the href not attribute-escaped; L5 the link
text not the recorded query; L6 a ``;`` inside a URL treated as a break; L7 a link without rel noopener."""
from __future__ import annotations

import html
import re

import pytest

from attestation_reporter.render import query_cell, render_html

from test_render_html_escaping import _pack

URL = "http://127.0.0.1:8002/events?event_type=conformance.allow&since=2026-10-01T00%3A00%3A00%2B00%3A00"


def _hrefs(cell: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r"<a [^>]*href='([^']*)'", cell)]


def test_one_get_is_one_link_whose_text_is_the_recorded_query():
    cell = query_cell(f"GET {URL}")
    assert _hrefs(cell) == [URL]
    assert f">{html.escape('GET ' + URL)}</a>" in cell
    assert "<br>" not in cell


def test_a_joined_list_is_one_link_per_entry_one_per_line():
    cell = query_cell("GET http://l:1/events?a=1 ; GET http://l:1/events?a=2 ; GET http://l:1/health")
    assert _hrefs(cell) == ["http://l:1/events?a=1", "http://l:1/events?a=2", "http://l:1/health"]
    assert cell.count("<br>") == 2 and "; GET" not in re.sub(r"<[^>]+>", "", cell)


def test_a_semicolon_inside_a_url_is_not_a_break():
    cell = query_cell("GET http://l:1/x?a=1;b=2")
    assert _hrefs(cell) == ["http://l:1/x?a=1;b=2"] and "<br>" not in cell


@pytest.mark.parametrize("entry", ["GET /events?x=1", "GET ftp://l/x", "GET javascript:alert(1)", "POST http://l/x",
                                   "GET http://l/x y", "", "no query recorded"])
def test_anything_that_is_not_a_get_http_entry_is_escaped_text_not_a_link(entry):
    cell = query_cell(entry)
    assert "<a " not in cell and cell == html.escape(entry)


def test_a_url_with_quotes_and_markup_cannot_break_out_of_the_attribute():
    cell = query_cell("GET http://l/x?a='\"><script>x</script>")
    assert "<script>" not in cell and "'>" not in cell.split("href='", 1)[1].split("'", 1)[0]
    assert _hrefs(cell) == ["http://l/x?a='\"><script>x</script>"]          # round-trips only through the escaped attribute


def test_every_link_opens_without_an_opener_or_referrer():
    cell = query_cell("GET http://l/a ; GET http://l/b")
    assert cell.count("rel='noopener noreferrer'") == 2 and cell.count("target='_blank'") == 2


def test_the_rendered_page_prints_the_links_in_the_source_query_column():
    page = render_html(_pack(m={"source_query": "GET http://l:1/verify ; GET http://l:1/health"}))
    assert "<td class='query'><a class='qlink' href='http://l:1/verify'" in page
    assert page.count("class='qlink'") == 2
    assert "GET http://l:1/verify ; GET http://l:1/health" not in page        # no longer one raw string


def test_an_unavailable_metric_still_prints_its_failed_query_as_a_link():
    page = render_html(_pack(m={"status": "unavailable", "value": None, "source_query": f"GET {URL}"}))
    assert f"href='{html.escape(URL, quote=True)}'" in page
