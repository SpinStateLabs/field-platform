"""HTML rendering + best-effort PDF via headless Edge/Chrome."""

from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path

from attestation_reporter.engine import BoardPack

_CSS = """
body { font-family: Segoe UI, system-ui, sans-serif; margin: 2.5rem auto;
       max-width: 60rem; color: #1a1a1a; }
h1 { border-bottom: 3px solid #1a1a1a; padding-bottom: .4rem; }
h2 { margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #ddd;
         vertical-align: top; }
th { background: #f2f2f2; }
td.value { font-size: 1.05rem; font-weight: 600; white-space: nowrap; }
td.query { font-family: Consolas, monospace; font-size: .78rem; color: #555; }
.unavailable { color: #a33; font-weight: 600; }
.integrity-INTACT { color: #1a7a1a; }
.integrity-BROKEN { color: #a31111; }
footer { margin-top: 2.5rem; font-size: .8rem; color: #666;
         border-top: 1px solid #ddd; padding-top: .6rem; }
"""


def render_html(pack: BoardPack) -> str:
    esc = html.escape
    rows: list[str] = []
    add = rows.append
    add("<!doctype html><html><head><meta charset='utf-8'>")
    add(f"<title>FIELD board pack — {esc(pack.org)}</title>")
    add(f"<style>{_CSS}</style></head><body>")
    add(f"<h1>FIELD governance board pack — {esc(pack.org)}</h1>")
    add(f"<p><b>Period:</b> {esc(pack.period)} · <b>Generated:</b> "
        f"{esc(pack.generated_at)}</p>")
    add("<p><i>Every figure below prints the query it came from. "
        "No number without a source.</i></p>")
    for section in pack.sections:
        add(f"<h2>{esc(section.title)}</h2>")
        add("<table><tr><th>Metric</th><th>Value</th><th>Source query</th></tr>")
        for m in section.metrics:
            if m.status == "unavailable":
                value = "<span class='unavailable'>unavailable</span>"
            else:
                cls = ""
                if isinstance(m.value, str) and m.value.startswith(("INTACT", "BROKEN")):
                    cls = f" class='integrity-{m.value.split(' ')[0].rstrip('—')}'"
                unit = f" {esc(m.unit)}" if m.unit else ""
                value = f"<span{cls}>{esc(str(m.value))}{unit}</span>"
            note = f"<br><i>{esc(m.note)}</i>" if m.note else ""
            add(f"<tr><td>{esc(m.name)}{note}</td><td class='value'>{value}</td>"
                f"<td class='query'>{esc(m.source_query)}</td></tr>")
        add("</table>")
    add(f"<footer>Method: {esc(pack.method)}<br>"
        "Force Field Protocol · Spin State Labs · FIELD Platform "
        "attestation-reporter v0.1</footer>")
    add("</body></html>")
    return "\n".join(rows)


_BROWSER_CANDIDATES = (
    "msedge",
    "chrome",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


def find_browser() -> str | None:
    for candidate in _BROWSER_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
        if Path(candidate).exists():
            return candidate
    return None


def render_pdf(html_path: Path, pdf_path: Path) -> tuple[bool, str]:
    """Best-effort PDF via headless Edge/Chrome. Returns (ok, detail)."""
    browser = find_browser()
    if browser is None:
        return False, "no Edge/Chrome found — HTML only (see LIMITS)"
    try:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu",
             f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer",
             html_path.as_uri()],
            check=True, capture_output=True, timeout=120,
        )
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return True, f"rendered by {Path(browser).name}"
        return False, "browser exited cleanly but produced no PDF"
    except Exception as exc:
        return False, f"headless print failed: {exc}"
