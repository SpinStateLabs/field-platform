"""S3-15: every interpolation site of ``render_html`` escapes a hostile string.

``render_html`` builds the board-pack page by f-string; every ledger- or caller-derived text goes through
``html.escape``. Before this file one test (the signer, test_f4_served_signing) checked it. Here each site is
tested alone: the payload goes into ONE field of an otherwise benign pack, and the page must (a) never contain
the raw payload, (b) contain no ``<script``, and (c) contain the escaped payload, so a site that is dropped
from the page does not pass by accident.

The integrity CSS class is built from a metric VALUE (``class='integrity-<first token>'``) and is not escaped.
The engine only produces the values ``INTACT`` and ``BROKEN — <reason>`` (``PackEngine._integrity`` in engine.py), so a
ledger-supplied reason sits after the space and never reaches the class; the real-value test pins that. A hand
built Metric whose value starts with INTACT or BROKEN and has no space is NOT covered here (see the report).
"""
from __future__ import annotations

import html

import pytest

from attestation_reporter.engine import BoardPack, Metric, Section
from attestation_reporter.render import render_html
from attestation_reporter.window import Window

PAYLOAD = "</td><script>x</script>'\""
ESCAPED = html.escape(PAYLOAD)


def _pack(*, org="Acme", period="2026-Q3", w=None, generated_at="2026-10-01T00:00:00Z", title="Section",
          m=None, signed=False, sign=None, method=None) -> BoardPack:
    window = Window(**{"kind": "range", "since": "2026-07-01T00:00:00Z", "until": "2026-09-30T23:59:59Z",
                       "note": "window note", **(w or {})})
    metric = Metric(**{"name": "Metric", "value": 3, "unit": "events", "source_query": "GET /events?x=1",
                       "note": "metric note", **(m or {})})
    extra = {}
    if method is not None:
        extra["method"] = method
    if signed:
        extra.update(signed=True, **{"signer": "Pat", "signed_at": "2026-10-01T00:00:00Z",
                                     "key_fingerprint": "ab:cd", "signature": "c2ln", "signed_via": "cli",
                                     **(sign or {})})
    return BoardPack(org=org, period=period, window=window, generated_at=generated_at,
                     sections=[Section(title=title, metrics=[metric])], **extra)


SITES = {
    "org": dict(org=PAYLOAD),
    "period": dict(period=PAYLOAD),
    "window.since": dict(w={"since": PAYLOAD}),
    "window.until": dict(w={"until": PAYLOAD}),
    "window.note": dict(w={"note": PAYLOAD}),
    "generated_at": dict(generated_at=PAYLOAD),
    "section.title": dict(title=PAYLOAD),
    "metric.name": dict(m={"name": PAYLOAD}),
    "metric.unit": dict(m={"unit": PAYLOAD}),
    "metric.value": dict(m={"value": PAYLOAD}),
    "metric.note": dict(m={"note": PAYLOAD}),
    "metric.source_query": dict(m={"source_query": PAYLOAD}),
    "method": dict(method=PAYLOAD),
    "signer": dict(signed=True, sign={"signer": PAYLOAD}),
    "signed_at": dict(signed=True, sign={"signed_at": PAYLOAD}),
    "key_fingerprint": dict(signed=True, sign={"key_fingerprint": PAYLOAD}),
}


def _assert_escaped(page: str) -> None:
    assert PAYLOAD not in page
    assert "<script" not in page
    assert ESCAPED in page


@pytest.mark.parametrize("site", sorted(SITES))
def test_a_hostile_string_in_one_field_is_escaped(site: str) -> None:
    _assert_escaped(render_html(_pack(**SITES[site])))


def test_the_benign_pack_has_no_script_and_every_site_is_listed() -> None:
    page = render_html(_pack(signed=True))
    assert "<script" not in page and ESCAPED not in page
    # the table covers every free-text field the renderer interpolates (new site => add it here)
    assert len(SITES) == 16


def test_an_all_time_window_still_escapes_the_note_it_does_not_print_as_bounds() -> None:
    page = render_html(_pack(w={"kind": "all-time", "since": None, "until": None, "note": PAYLOAD}))
    _assert_escaped(page)


def test_the_unavailable_branch_escapes_name_note_and_query() -> None:
    page = render_html(_pack(m={"status": "unavailable", "value": None, "name": PAYLOAD, "note": PAYLOAD,
                                "source_query": PAYLOAD}))
    assert PAYLOAD not in page and "<script" not in page
    assert page.count(ESCAPED) == 3


@pytest.mark.parametrize("value, cls", [("INTACT", "integrity-INTACT"),
                                        ("BROKEN — chain broken at 4", "integrity-BROKEN")])
def test_integrity_value_class_is_the_fixed_word_for_values_the_engine_produces(value: str, cls: str) -> None:
    page = render_html(_pack(m={"value": value}))
    assert f"<span class='{cls}'>" in page


def test_a_ledger_supplied_broken_reason_never_reaches_the_class_attribute() -> None:
    page = render_html(_pack(m={"value": f"BROKEN — {PAYLOAD}"}))
    assert "<span class='integrity-BROKEN'>" in page  # class is the fixed word; reason follows the space
    _assert_escaped(page)
