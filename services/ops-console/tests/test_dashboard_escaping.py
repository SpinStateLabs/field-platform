"""C-220 (reviewer C-200 F-C200-2): the dashboard's escaping is pinned.

console.html runs in jsdom (dashboard_xss_harness.mjs) against a stub estate whose every string field
holds a hostile payload; the shipped page must inject nothing (no img[src=x], svg[onload], on*
attribute naming the payload, extra script, or window.__pwn) in any of five data modes. The same
probe must then FLAG a copy of the page with one `esc(` removed, for a sample of sites across the
dashboard script, so a probe that cannot fail is caught here.

The C-200 reviewer's full round removed `esc(` at each of the 79 sites of the dashboard script:
70 were caught and 9 survive as equivalent or bounded (select option text jsdom's parser discards,
an 8-character slice, a number, a constant action or note, a client-side error string). The sample
below is drawn from the caught set; the full round is in the card's report.

Needs node + npm (jsdom is cached by test_setup_behaviour's fixture). Skipped when unavailable, but
a failure when CI=true so the gate cannot silently vanish.
"""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from test_setup_behaviour import HTML_PATH, jsdom_dir  # noqa: F401  (fixture)

HARNESS = Path(__file__).parent / "dashboard_xss_harness.mjs"
MODES = ("ok", "short", "unavail", "err", "status")
ALL_PAYLOADS = range(7)
MUTANT_PAYLOADS = (0, 2, 5)


def probe(jsdom_dir: Path, html: Path, payload: int, mode: str) -> int:
    p = subprocess.run(["node", str(HARNESS), str(jsdom_dir), str(html), str(payload), mode],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])["maxhit"]


def sweep(jsdom_dir: Path, html: Path, payloads, modes) -> dict[tuple[int, str], int]:
    combos = [(i, m) for i in payloads for m in modes]
    with ThreadPoolExecutor(max_workers=6) as pool:
        hits = pool.map(lambda c: probe(jsdom_dir, html, *c), combos)
    return dict(zip(combos, hits))


@pytest.mark.parametrize("mode", MODES)
def test_the_shipped_dashboard_injects_nothing(jsdom_dir, mode):
    hits = sweep(jsdom_dir, HTML_PATH, ALL_PAYLOADS, [mode])
    assert {k: v for k, v in hits.items() if v} == {}


# One esc( removed per case: the text is a line of the dashboard script that holds exactly one such
# call (asserted below), so the case survives a renumbering of lines.
SITES = [
    "unavailable — ${esc(sec.error)}",
    '<td class="mono"><button class="link" data-id="${esc(a.agent_id)}"',
    '<td class="mono">${esc(e.agent_id)}</td>',
    "<pre>${esc(JSON.stringify(e, null, 2))}</pre>",
    "agent errors: ${esc(r.agent_errors || 0)}",
    "<b>${esc(data.decision)}</b>",
]


@pytest.mark.parametrize("site", SITES)
def test_removing_one_esc_is_flagged(jsdom_dir, tmp_path, site):
    html = HTML_PATH.read_text(encoding="utf-8")
    assert html.count(site) == 1, "site text must appear exactly once in console.html"
    mutant = tmp_path / "console.html"
    mutant.write_text(html.replace(site, site.replace("esc(", "(", 1)), encoding="utf-8")
    hits = sweep(jsdom_dir, mutant, MUTANT_PAYLOADS, MODES)
    assert any(hits.values()), f"probe did not notice `esc(` removed from {site!r}"
