"""C-457 (design note channel 15, reviewer C-200): every HTML sink in the ops-console page takes only escaped or constant text.

`innerhtml_audit.mjs` parses the page's inline scripts with acorn and follows the value of every `innerHTML` /
`outerHTML` assignment, `insertAdjacentHTML` and `document.write` through the page's own helpers. A sink is clean when
its value is built only from literals, numbers and booleans, `esc(...)`, and safe template parts, branches, calls and
`.map(...).join(...)` results (the rules are at the top of the script). The shipped page must have no finding and
`esc` must turn the HTML specials into entities. Each rule is exercised on small pages, and the shipped page is
mutated (a dropped `esc(`, a new sink, a weakened `esc`) to prove the audit goes red.

Needs node + npm (acorn is installed once into a cache dir). Skipped when unavailable, but a failure when CI=true
so the gate cannot silently vanish.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

import ops_console

HTML_PATH = Path(ops_console.__file__).parent / "static" / "console.html"
AUDIT = Path(__file__).parent / "innerhtml_audit.mjs"
ACORN_VERSION = "8.14.0"


@pytest.fixture(scope="session")
def acorn_dir() -> Path:
    def unavailable(why: str):
        if os.environ.get("CI", "").lower() in {"1", "true"}:
            pytest.fail(why)
        pytest.skip(why)

    node, npm = shutil.which("node"), shutil.which("npm")
    if not node:
        unavailable("node is not installed")
    d = Path(os.environ.get("FIELD_TEST_ACORN_DIR") or Path(tempfile.gettempdir()) / f"field-acorn-{ACORN_VERSION}")
    if not (d / "node_modules" / "acorn").is_dir():
        if not npm:
            unavailable("npm is not installed")
        d.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--prefix", str(d), f"acorn@{ACORN_VERSION}"],
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            unavailable("could not install acorn: " + p.stderr[-300:])
    return d


def audit(acorn_dir: Path, html: Path) -> dict:
    p = subprocess.run(["node", str(AUDIT), str(acorn_dir), str(html)], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def findings(result: dict) -> list[str]:
    out = [f"{s['line']}: {p['text']}  [{p['why']}]" for s in result["sinks"] for p in s["problems"]]
    out += [f"esc leaves a special unescaped: {e['out']}" for e in result["escChecks"] if not e["clean"]]
    return out


def page(tmp_path: Path, js: str) -> Path:
    f = tmp_path / "page.html"
    f.write_text(f"<!doctype html><script>\n{js}\n</script>", encoding="utf-8")
    return f


ESC = 'const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/\'/g,"&#39;");\n'


# ---- the shipped page ------------------------------------------------------------------------------------------------

def test_the_shipped_page_has_no_unescaped_sink(acorn_dir):
    r = audit(acorn_dir, HTML_PATH)
    assert findings(r) == []


def test_the_audit_is_not_blind(acorn_dir):
    r = audit(acorn_dir, HTML_PATH)
    assert r["scripts"] == 2
    assert len(r["sinks"]) >= 25, "the card counts about 25 innerHTML sites; the page has more, never fewer"
    assert len(r["escChecks"]) == 1 and r["escChecks"][0]["clean"]


MUTANTS = {
    "a dropped esc() in the agent table": ("<td>${esc(a.owner)}</td>", "<td>${a.owner}</td>"),
    "the unavailable notice unescaped": ('unavailable — ${esc(sec.error)}</span>`;', 'unavailable — ${sec.error}</span>`;'),
    "the cost cell unescaped": ("${esc(u.total_cost_display)}", "${u.total_cost_display}"),
    "the model name unescaped": ("${esc(m.model)}</span>${tag}", "${m.model}</span>${tag}"),
    "the payload sink unescaped": ("<pre>${esc(JSON.stringify(e, null, 2))}</pre></td></tr>`);", "<pre>${JSON.stringify(e, null, 2)}</pre></td></tr>`);"),
    "an action button id unescaped": ("const id = esc(a.agent_id);", "const id = a.agent_id;"),
    "a token agent unescaped": ('<td class="mono">${esc(t.agent_id)}</td>', '<td class="mono">${t.agent_id}</td>'),
    "a select option label unescaped": ("${esc(label)}</option>", "${label}</option>"),
    "a detail key unescaped": ("<dt>${esc(k)}</dt>", "<dt>${k}</dt>"),
    "an error message unescaped": ('<span class="bad">refused: ${esc(e.message)}</span>`; haltReady(); }', '<span class="bad">refused: ${e.message}</span>`; haltReady(); }'),
    "an unsafe table header": ('"agent","owner","domain","status","actions"]', 'AGENTS[0].owner,"owner","domain","status","actions"]'),
    "a new sink from data": ('$("sel-count").textContent = `${SELECTED.size} selected`;\n  const opts =', '$("sel-count").innerHTML = `${SELECTED.size} selected ${AGENTS[0].owner}`;\n  const opts ='),
    "a new sink from the location": ('$("bulk-result").innerHTML = \'<span class="dim">working…</span>\';', '$("bulk-result").innerHTML = location.hash;'),
    "esc without the double quote": ('.replace(/[&<>"\']/g,', ".replace(/[&<>\']/g,"),
    "esc without the single quote": ('.replace(/[&<>"\']/g,', '.replace(/[&<>"]/g,'),
    "esc without the angle bracket": ('.replace(/[&<>"\']/g,', '.replace(/[&"\']/g,'),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_each_mutant_of_the_page_is_caught(acorn_dir, tmp_path, name):
    old, new = MUTANTS[name]
    src = HTML_PATH.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    mutant = tmp_path / "mutant.html"
    mutant.write_text(src.replace(old, new), encoding="utf-8")
    assert findings(audit(acorn_dir, mutant)) != [], "the mutant survived: the audit cannot fail"


# ---- each rule, on small pages ---------------------------------------------------------------------------------------

SAFE = {
    "esc call": 'x.innerHTML = "<b>" + esc(a) + "</b>";',
    "template with esc": "x.innerHTML = `<b>${esc(a)}</b>`;",
    "constant": 'x.innerHTML = "<i>ok</i>";',
    "number from length": "x.innerHTML = `${items.length} rows`;",
    "ternary of literals": 'x.innerHTML = `<b class="${ok ? "ok" : "bad"}">x</b>`;',
    "map join over esc": "x.innerHTML = list.map(a => `<i>${esc(a.name)}</i>`).join('');",
    "map with block body": "x.innerHTML = list.map(a => { const k = 1; return `<i>${esc(a)}${k}</i>`; }).join('');",
    "helper whose returns are safe": "const h = s => `<b>${esc(s)}</b>`;\nx.innerHTML = h(a.b);",
    "string of a coerced number": "function f(n) { n = Number(n) || 0; return String(n); }\nx.innerHTML = f(a);",
    "local built from esc": "let h = '';\nh += `<i>${esc(a)}</i>`;\nx.innerHTML = h;",
    "parameter safe at every call site": "function t(rows) { return '<t>' + rows.join('') + '</t>'; }\nx.innerHTML = t(['<r/>']);\ny.innerHTML = t(list.map(a => `<r>${esc(a)}</r>`));",
    "element of a safe header list": "function t(hs) { return hs.map(h => `<th>${h}</th>`).join(''); }\nx.innerHTML = t(['a', 'b']);",
    "slice of escaped text": "x.innerHTML = esc(a).slice(0, 3);",
    "logical of safe values": "x.innerHTML = esc(a) || '';",
}

UNSAFE = {
    "raw data": "x.innerHTML = a;",
    "property of data": "x.innerHTML = `<b>${a.name}</b>`;",
    "unknown call": "x.innerHTML = foo(a);",
    "helper returning data": "const h = s => s.name;\nx.innerHTML = h(a);",
    "helper with an unescaped part": "const h = s => `<b>${s.name}</b>`;\nx.innerHTML = h(a);",
    "plus with data": "x.innerHTML = '<b>' + a.name;",
    "one unsafe caller": "function t(rows) { return rows.join(''); }\nx.innerHTML = t(['<r/>']);\ny.innerHTML = t([a.name]);",
    "helper used as a value": "function t(r) { return r; }\nx.innerHTML = t('<r/>');\nlist.map(t);",
    "map over data elements": "x.innerHTML = list.map(a => `<i>${a}</i>`).join('');",
    "json of data": "x.innerHTML = JSON.stringify(a);",
    "outerHTML": "x.outerHTML = a.name;",
    "append": "x.innerHTML += a.name;",
    "insertAdjacentHTML": "x.insertAdjacentHTML('beforeend', a.name);",
    "document.write": "document.write(a.name);",
    "global": "x.innerHTML = window.name;",
    "local built from data": "let h = '';\nh += `<i>${a.name}</i>`;\nx.innerHTML = h;",
    "slice of data": "x.innerHTML = a.name.slice(0, 3);",
    "uppercase of data": "x.innerHTML = a.name.toUpperCase();",
    "data in the else branch": "x.innerHTML = ok ? '<b/>' : a.name;",
    "data on the right of ||": "x.innerHTML = esc(a) || a.name;",
    "template inside a ternary branch": "x.innerHTML = ok ? `<b>${a.name}</b>` : '';",
}


@pytest.mark.parametrize("name", sorted(SAFE))
def test_a_safe_shape_is_accepted(acorn_dir, tmp_path, name):
    r = audit(acorn_dir, page(tmp_path, ESC + SAFE[name]))
    assert sum(1 for _ in r["sinks"]) >= 1
    assert findings(r) == []


@pytest.mark.parametrize("name", sorted(UNSAFE))
def test_an_unsafe_shape_is_reported(acorn_dir, tmp_path, name):
    r = audit(acorn_dir, page(tmp_path, ESC + UNSAFE[name]))
    assert len(r["sinks"]) >= 1
    assert findings(r) != []


def test_a_broken_esc_is_reported(acorn_dir, tmp_path):
    weak = 'const esc = s => String(s).replace(/</g, "&lt;");\nx.innerHTML = esc(a);'
    r = audit(acorn_dir, page(tmp_path, weak))
    assert any("esc leaves a special unescaped" in f for f in findings(r))
