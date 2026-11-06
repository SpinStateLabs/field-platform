"""The console's "board pack" link on a locked estate (Don, 2026-11-06: the attestation pack does not work).

Root cause (measured against live ledger, registry, delegation, governor and attest processes with FIELD_SHARED_SECRET set):
``GET /attest/pack.html`` answers 401 JSON without ``x-field-auth`` and 200 HTML with it. The console linked to the route
with a plain ``<a href target=_blank>``, and a browser navigation cannot carry that header, so the link only ever showed the
401 on a locked estate. The page now fetches the pack through ``sfetch`` (which adds the header) and saves it as a file; it is
never opened as a page of the console origin, which holds the secret. Mutants: B1 the link is a plain navigation again (no
``data-pack`` handler); B2 the handler fetches without ``sfetch``; B3 the pack is opened in a window or the console's own
frame instead of saved; B4 the refusal is not shown; B5 the pack is saved under another type or name."""
from __future__ import annotations

import re
from pathlib import Path

import ops_console

PAGE = (Path(ops_console.__file__).parent / "static" / "console.html").read_text(encoding="utf-8")


def _handler() -> str:
    m = re.search(r'document\.addEventListener\("click", async ev => \{.*?a\[data-pack\].*?\n\}\);', PAGE, re.S)
    assert m, "the board pack click handler is missing"
    return m.group(0)


def test_the_board_pack_link_is_marked_for_the_authenticated_fetch():
    link = re.search(r'<a [^>]*href="/attest/pack\.html"[^>]*>', PAGE)
    assert link and 'data-pack="html"' in link.group(0)
    assert PAGE.count('href="/attest/pack.html"') == 1            # no second, plain link to the data route


def test_the_handler_fetches_with_the_page_header_and_saves_the_file():
    h = _handler()
    assert 'fetch("/attest/pack.html", {headers: hdrs(false)' in h   # hdrs adds x-field-auth; sfetch is local to the setup IIFE
    assert "ev.preventDefault()" in h
    assert 'type: "text/html"' in h and 'd.download = "board-pack.html"' in h
    assert "URL.createObjectURL" in h and "URL.revokeObjectURL" in h


def test_the_pack_is_saved_never_opened_in_the_console_origin():
    h = _handler()
    for opener in ("window.open", "location", "iframe", "document.write", "innerHTML", "srcdoc"):
        assert opener not in h, opener


def test_a_refusal_is_shown_in_the_status_text_not_swallowed():
    h = _handler()
    assert "resp.status === 401" in h and "if (!resp.ok)" in h and "textContent" in h
    assert 'id="pack-status"' in PAGE


def test_the_handler_calls_no_helper_that_is_local_to_the_setup_script():
    h = _handler()
    for local in ("sfetch(", "describe(", " g(", "failure(", "result("):
        assert local not in h, local


def test_the_perimeter_header_helper_sends_the_secret():
    hdrs = PAGE.split("function hdrs(", 1)[1][:600]
    assert "x-field-auth" in hdrs
