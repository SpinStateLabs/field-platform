"""Capture Scene 3 stills by driving the LIVE ops-console with Playwright.

Every screenshot is the real page reflecting real backend state; the
harness verdict and the kill are genuine /api calls that land on the
sealed ledger. Requires the ops-console demo stack up on :8011.

Writes PNGs + captions.json into out/scene3-shots/ for record_scenes.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SHOTS = HERE / "out" / "scene3-shots"
URL = "http://localhost:8011/"
SHOTS.mkdir(parents=True, exist_ok=True)

captions = []


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # Auto-accept the operator/reason prompt() dialogs the console raises,
        # supplying a real recorded operator name.
        answers = iter(["CISO (video capture)", "anomalous behaviour drill"])

        def on_dialog(dialog):
            try:
                dialog.accept(next(answers))
            except StopIteration:
                dialog.accept("CISO (video capture)")

        page.on("dialog", on_dialog)

        page.goto(URL)
        page.wait_for_timeout(6000)  # let the 5 s poll populate

        # Shot 1 — the whole fleet, live.
        page.screenshot(path=str(SHOTS / "01-dashboard.png"))
        captions.append({"png": "01-dashboard.png", "seconds": 4.5,
                         "caption": "This is the ops console — every governed "
                         "agent, its human owner, its tokens, and the "
                         "escalation queue where agents wait for people."})

        # Shot 2 — harness dry-run of an out-of-scope action WITH a valid
        # token, so the block is genuinely about scope (D.scope), not a
        # missing token. Pick the invoicing-agent token by its label.
        page.select_option("#h-agent", "invoicing-agent")
        tok_labels = page.eval_on_selector_all(
            "#h-token option",
            "els => els.map(e => ({v: e.value, t: e.textContent}))")
        tok_value = next(o["v"] for o in tok_labels
                         if "invoicing-agent" in o["t"] and o["v"])
        page.select_option("#h-token", tok_value)
        page.fill("#h-action", "transfer funds")
        page.click("form#harness button[type=submit]")
        page.wait_for_selector("#verdict.BLOCK", timeout=8000)
        page.wait_for_timeout(400)
        page.screenshot(path=str(SHOTS / "02-harness-block.png"))
        captions.append({"png": "02-harness-block.png", "seconds": 4.5,
                         "caption": "The harness asks the enforcement engine "
                         "what WOULD happen — and the verdict is real, "
                         "landing on the ledger like any check. BLOCK, "
                         "D.scope."})

        # Shot 3 — kill invoicing-agent through the console (real, ledgered).
        rows = page.query_selector_all("#agents tr")
        for row in rows:
            if "invoicing-agent" in (row.inner_text() or ""):
                row.query_selector("button.danger").click()
                break
        page.wait_for_timeout(1500)  # refresh() re-polls after the action
        page.reload()
        page.wait_for_timeout(6000)
        page.screenshot(path=str(SHOTS / "03-killed.png"))
        captions.append({"png": "03-killed.png", "seconds": 5.0,
                         "caption": "The kill button holds no authority of its "
                         "own — it proxies the kill-switch, with your name on "
                         "the ledger. The agent is down; the event is on the "
                         "chain."})

        browser.close()

    (SHOTS / "captions.json").write_text(json.dumps(captions, indent=2),
                                         encoding="utf-8")
    print(f"captured {len(captions)} Scene 3 stills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
