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

C-268 (reviewer C-256): "nothing was injected" is only as strong as the proof that something was
rendered. The harness reports which containers held the payload text; the shipped-page test asserts all
nine did, and a copy of the page with one flow killed (an early `return` in the function that fills the
container) must come back with that container missing, so a dead flow cannot pass as clean.

Needs node + npm (jsdom is cached by test_setup_behaviour's fixture). Skipped when unavailable, but
a failure when CI=true so the gate cannot silently vanish.
"""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from test_setup_behaviour import HTML_PATH, jsdom_dir  # noqa: F401  (fixture)

HARNESS = Path(__file__).parent / "dashboard_xss_harness.mjs"
MODES = ("ok", "short", "unavail", "err", "status")
CONTAINERS = ("agents", "escalations", "events", "d-details", "d-manifest", "bulk-result", "halt-result",
              "verdict", "platform")
ALL_PAYLOADS = range(7)
MUTANT_PAYLOADS = (0, 2, 5)


def probe(jsdom_dir: Path, html: Path, payload: int, mode: str) -> dict:
    p = subprocess.run(["node", str(HARNESS), str(jsdom_dir), str(html), str(payload), mode],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def sweep(jsdom_dir: Path, html: Path, payloads, modes) -> dict[tuple[int, str], dict]:
    combos = [(i, m) for i in payloads for m in modes]
    with ThreadPoolExecutor(max_workers=6) as pool:
        hits = pool.map(lambda c: probe(jsdom_dir, html, *c), combos)
    return dict(zip(combos, hits))


def any_hit(jsdom_dir: Path, html: Path, payloads, modes) -> bool:
    """True as soon as one probe flags the page; the probes still queued are cancelled."""
    combos = [(i, m) for i in payloads for m in modes]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(probe, jsdom_dir, html, *c) for c in combos]
        for done in as_completed(futures):
            if done.result()["maxhit"]:
                for f in futures:
                    f.cancel()
                return True
    return False


@pytest.mark.parametrize("mode", MODES)
def test_the_shipped_dashboard_injects_nothing(jsdom_dir, mode):
    results = sweep(jsdom_dir, HTML_PATH, ALL_PAYLOADS, [mode])
    assert {k: r["maxhit"] for k, r in results.items() if r["maxhit"]} == {}
    # ... and the payload really reached every container, in every payload of this mode
    assert {k: sorted(set(CONTAINERS) - set(r["rendered"])) for k, r in results.items()
            if set(CONTAINERS) - set(r["rendered"])} == {}


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
    assert any_hit(jsdom_dir, mutant, MUTANT_PAYLOADS, MODES), f"probe did not notice `esc(` removed from {site!r}"


# One flow killed per case: an early `return` at the top of the function that fills the container. The
# page still loads and nothing is injected, so only the "rendered" record can tell.
DEAD_FLOWS = [
    ("agents", "function renderAgents(sec) {"),
    ("escalations", "function renderEscalations(sec) {"),
    ("events", "function paintEvents(withDate) {"),
    ("d-details", "async function loadDetails(id) {"),
    ("d-manifest", "async function loadManifest(id) {"),
    ("bulk-result", "async function bulk(action) {"),
    ("halt-result", "async function fleetHalt() {"),
    ("verdict", "async function runCheck(ev) {"),
    ("platform", "async function refreshPlatform() {"),
]


def test_every_container_is_covered_by_a_dead_flow_case():
    assert [c for c, _ in DEAD_FLOWS] == list(CONTAINERS)


@pytest.mark.parametrize(("container", "header"), DEAD_FLOWS)
def test_a_dead_flow_is_reported_as_not_rendered(jsdom_dir, tmp_path, container, header):
    html = HTML_PATH.read_text(encoding="utf-8")
    assert html.count(header) == 1, "function header must appear exactly once in console.html"
    dead = tmp_path / "console.html"
    dead.write_text(html.replace(header, header + " return;"), encoding="utf-8")
    result = probe(jsdom_dir, dead, 0, "ok")
    assert result["maxhit"] == 0, "a dead flow injects nothing: that is the vacuous pass"
    assert container not in result["rendered"], result["rendered"]
    assert set(result["rendered"]) | {container} == set(CONTAINERS),         f"killing {container} must not take other containers with it: {result['rendered']}"
