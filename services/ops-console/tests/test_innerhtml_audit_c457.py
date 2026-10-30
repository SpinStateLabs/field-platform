"""C-457 (design note channel 15, reviewer C-200; hardened after reviewer C-508 and the Lane 10 review of PR 314): every
HTML sink in the ops-console page takes only escaped or constant text.

`innerhtml_audit.mjs` parses the page's inline JavaScript with acorn and follows the value of every sink through the
page's own helpers. A sink is clean when its value is built only from literals, numbers and booleans, `esc(...)`, and
safe template parts, branches, calls, `for...of` elements and `.map(...).join(...)` results (the rules are at the top of
the script). The shipped page must have no finding and `esc` must turn the HTML specials into entities. Each rule is
exercised on small pages, and the shipped page is mutated (a dropped `esc(`, a new sink, a weakened `esc`, a templated
`onclick`) to prove the audit goes red.

COVERED (reported when found; a test for each): `innerHTML` / `outerHTML` / `srcdoc` assignment (also with a string-literal
key, in `Object.assign(x, {innerHTML: e})`, and a destructuring assignment into one); `insertAdjacentHTML`;
`.write(` / `.writeln(` on any object; `createContextualFragment`; `DOMParser().parseFromString`; `setAttribute` with a
computed name, or `on*` / `srcdoc` given a non-constant, or a URL attribute given a non-safe URL; `href` / `src` /
`action` / `formAction` assigned anything but a literal, a `#` or `/` relative string, or `URL.createObjectURL(...)`;
`eval`, `Function(...)`, `new Function`, `setTimeout` / `setInterval` given a string; a template expression inside an
inline event handler (`on*="..."`) or at the start of a URL attribute or after `javascript:`; `esc` bound or assigned
anywhere but once at the top level (a parameter, loop, catch or inner declaration named `esc`), or declared in two
scripts; a function name defined twice; a `.replace` that re-introduces markup characters; a `for...in` key, a caught
error, and a `for...of` element of data; every executable `<script>` however its `type` is spelled (quoted or not,
`module`, any JavaScript MIME type), with the skipped ones (JSON data, external `src`) listed and pinned.

NOT COVERED (a review has to catch these): `el[k] = data` with a variable key; `eval` reached through an alias
(`const e = eval`); the static `on*=` attributes of the page's own HTML (they run, the audit never parses them); a
helper that builds an attribute value across two functions (the on* / URL check sees one string expression at a time);
`document.cookie`, `location` assignments and `window.open`; any flow through `JSON.parse`, `localStorage` or
`postMessage`; code loaded from another file; and a test environment that is not trusted (acorn is fetched from npm at
test time and checked against the pinned integrity hash below, not vendored).

Needs node + npm (acorn is installed once into a cache dir). Skipped when unavailable, but a failure when CI=true
so the gate cannot silently vanish.
"""

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
ACORN_INTEGRITY = "sha512-cl669nCJTZBsL97OF4kUQm5g5hC2uihk0NxY3WENAC0TYdILVkAyHymAntgxGkl7K+t0cXIrH5siy5S4XkFycA=="


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
    lock = json.loads((d / "package-lock.json").read_text(encoding="utf-8")) if (d / "package-lock.json").is_file() else {}
    got = (lock.get("packages", {}).get("node_modules/acorn") or {}).get("integrity")
    if got != ACORN_INTEGRITY:
        unavailable(f"the installed acorn does not match the pinned integrity hash (got {got!r})")
    return d


def audit(acorn_dir: Path, html: Path) -> dict:
    p = subprocess.run(["node", str(AUDIT), str(acorn_dir), str(html)], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def findings(result: dict) -> list[str]:
    out = [f"{s['line']}: {p['text']}  [{p['why']}]" for s in result["sinks"] for p in s["problems"]]
    out += [f"{p['line']}: {p['text']}  [{p['why']}]" for p in result["structure"]]
    out += [f"esc leaves a special unescaped: {e['out']}" for e in result["escChecks"] if not e["clean"]]
    return out


def page(tmp_path: Path, js: str) -> Path:
    return raw_page(tmp_path, f"<script>\n{js}\n</script>")


def raw_page(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "page.html"
    f.write_text(f"<!doctype html>{body}", encoding="utf-8")
    return f


ESC_VAR = 'var esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/\'/g,"&#39;");\n'
ESC = 'const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/\'/g,"&#39;");\n'


# ---- the shipped page ------------------------------------------------------------------------------------------------

def test_the_shipped_page_has_no_unescaped_sink(acorn_dir):
    r = audit(acorn_dir, HTML_PATH)
    assert findings(r) == []


def test_the_audit_is_not_blind(acorn_dir):
    r = audit(acorn_dir, HTML_PATH)
    assert r["scripts"] == 2
    assert [k["type"] for k in r["skipped"]] == ["application/json"], "only the JSON data block may be skipped"
    assert sum(1 for k in r["sinks"] if k["kind"] == "html") >= 25, "the card counts about 25 innerHTML sites; the page has more, never fewer"
    assert sum(1 for k in r["sinks"] if k["kind"] == "url") >= 3, "the page assigns a URL in several places"
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
    "a templated inline handler": ('onclick="killAgent(this.dataset.id)">kill</button>', 'onclick="killAgent(\'${id}\')">kill</button>'),
    "a templated inline handler with esc": ('onclick="drillAgent(this.dataset.id)">drill</button>', 'onclick="drillAgent(\'${id}\')">drill</button>'),
    "a URL from data": ('a.href = url; a.download = name; document.body.appendChild(a); a.click();\n    a.remove();', 'a.href = AGENTS[0].owner; a.download = name; document.body.appendChild(a); a.click();\n    a.remove();'),
    "a for loop over data": ('  const rows = tokenRows(sec.data);', '  let rows = []; for (const r of sec.data) { rows.push(r.token_id); }'),
    "a second esc declared before the real one": ('const esc = s => String(s ?? "").replace(', 'const esc = s => s;\nconst esc2 = s => String(s ?? "").replace('),
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
    "array filled with escaped text": "const rows = [];\nfor (const r of list) { rows.push(`<i>${esc(r.name)}</i>`); }\nx.innerHTML = rows.join('');",
    "for-of over a safe list": "const rows = ['<r/>', '<q/>'];\nlet h = '';\nfor (const r of rows) { h += r; }\nx.innerHTML = h;",
    "for-of over escaped parts": "let h = '';\nfor (const r of list.map(a => esc(a))) { h += r; }\nx.innerHTML = h;",
    "data attribute with esc and a constant handler": "x.innerHTML = '<button data-id=\"' + esc(a) + '\" onclick=\"del(this.dataset.id)\">x</button>';",
    "template data attribute then a constant handler": "x.innerHTML = `<button data-id=\"${esc(a)}\" onclick=\"del(this.dataset.id)\">x</button>`;",
    "blob url": "const u = URL.createObjectURL(b);\nlink.href = u;\nx.innerHTML = '<i/>';",
    "relative url with a fragment": "link.href = '#setup/' + s;\nx.innerHTML = '<i/>';",
    "aria attribute": "n.setAttribute('aria-current', 'page');\nx.innerHTML = '<i/>';",
    "plain object merge": "const o = Object.assign({}, a, {until: 1});\nx.innerHTML = '<i/>';",
    "timer with a function": "setTimeout(() => 1, 5);\nsetInterval(tick, 5);\nx.innerHTML = '<i/>';",
    "replace with plain text": "x.innerHTML = esc(a).replace('T', ' ');",
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
    "array filled with push": "const rows = [];\nfor (const r of list) { rows.push(r.name); }\nx.innerHTML = rows.join('');",
    "array filled by index": "const rows = [];\nrows[0] = a.name;\nx.innerHTML = rows.join('');",
    "array filled with a spread": "const rows = [];\nrows.push(...list);\nx.innerHTML = rows.join('');",
    "optional chaining on data": "x.innerHTML = a?.name;",
    "href built from data by +": "link.href = a.scheme + ':' + a.rest;",
    "for-of over data": "let h = '';\nfor (const r of rows) { h += r; }\nx.innerHTML = h;",
    "for-in key": "let h = '';\nfor (const k in data) { h += k; }\nx.innerHTML = h;",
    "a caught error": "try { f(); } catch (e) { x.innerHTML = e; }",
    "destructured declaration": "const { name } = a;\nx.innerHTML = name;",
    "computed innerHTML": "x['innerHTML'] = a.name;",
    "srcdoc": "f.srcdoc = a.name;",
    "Object.assign innerHTML": "Object.assign(x, { innerHTML: a.name });",
    "Object.assign of a spread onto an element": "Object.assign(x, data);",
    "Object.assign of an object spread onto an element": "Object.assign(x, { ...data });",
    "destructuring into innerHTML": "({ v: x.innerHTML } = a);",
    "writeln": "document.writeln(a.name);",
    "write on an alias": "const d = document;\nd.write(a.name);",
    "createContextualFragment": "r.createContextualFragment(a.name);",
    "parseFromString": "new DOMParser().parseFromString(a.name, 'text/html');",
    "setAttribute onclick": "n.setAttribute('onclick', a.name);",
    "setAttribute srcdoc": "n.setAttribute('srcdoc', a.name);",
    "setAttribute with a computed name": "n.setAttribute(k, 'x');",
    "setAttribute href with data": "n.setAttribute('href', a.url);",
    "href from data": "link.href = a.url;",
    "javascript url literal": "link.href = 'javascript:alert(1)';",
    "src from data": "img.src = a.url;",
    "eval": "eval(a.name);",
    "Function constructor": "new Function(a.name);",
    "Function call": "Function(a.name)();",
    "setTimeout with a string": "setTimeout('boom()', 5);",
    "setInterval with a template": "setInterval(`boom(${1})`, 5);",
    "window.setTimeout with a string": "window.setTimeout('boom()', 5);",
    "templated onclick": "x.innerHTML = `<button onclick=\"del('${esc(a.id)}')\">x</button>`;",
    "templated onclick, single quotes": "x.innerHTML = `<button onclick='del(\"${esc(a.id)}\")'>x</button>`;",
    "templated onclick, unquoted": "x.innerHTML = `<b onclick=${esc(a)}>x</b>`;",
    "onclick built with +": "x.innerHTML = '<b onclick=\"del(\\'' + esc(a) + '\\')\">x</b>';",
    "templated onerror": "x.innerHTML = `<img src=\"x\" onerror=\"${esc(a)}\">`;",
    "javascript url in a template": "x.innerHTML = `<a href=\"javascript:${esc(a)}\">x</a>`;",
    "expression at the start of an href": "x.innerHTML = `<a href=\"${esc(a)}\">x</a>`;",
    "expression at the start of a src": "x.innerHTML = `<img src=${esc(a)}>`;",
    "replace that re-introduces markup": "x.innerHTML = esc(a).replace(/&lt;/g, '<');",
    "replace with a quote": "x.innerHTML = esc(a).replace(/q/g, '\"');",
    "unsafe replace callback": "x.innerHTML = esc(a).replace(/q/g, m => a.name);",
}


@pytest.mark.parametrize("name", sorted(SAFE))
def test_a_safe_shape_is_accepted(acorn_dir, tmp_path, name):
    r = audit(acorn_dir, page(tmp_path, ESC + SAFE[name]))
    assert sum(1 for _ in r["sinks"]) >= 1
    assert findings(r) == []


@pytest.mark.parametrize("name", sorted(UNSAFE))
def test_an_unsafe_shape_is_reported(acorn_dir, tmp_path, name):
    r = audit(acorn_dir, page(tmp_path, ESC + UNSAFE[name]))
    assert len(r["sinks"]) + len(r["structure"]) >= 1
    assert findings(r) != []


def test_a_broken_esc_is_reported(acorn_dir, tmp_path):
    weak = 'const esc = s => String(s).replace(/</g, "&lt;");\nx.innerHTML = esc(a);'
    r = audit(acorn_dir, page(tmp_path, weak))
    assert any("esc leaves a special unescaped" in f for f in findings(r))


# ---- script selection (F-C508-1) -------------------------------------------------------------------------------------

JS_SCRIPT_OPENERS = [
    "<script>", "<script type=module>", '<script type="module">', "<script type='module'>", '<script type="text/javascript">',
    '<script type="application/javascript">', '<script type="text/JavaScript">', '<script type=" module ">',
    "<script defer>", '<script nonce="abc">', '<script language="javascript">', '<script type="text/ecmascript">',
    '<script id="x" type="module" defer>',
]
NON_JS_SCRIPTS = {
    '<script type="application/json">': "application/json",
    "<script type=application/json>": "application/json",
    '<script type="text/plain">': "text/plain",
    '<script type="text/jsx">': "text/jsx",
    "<script type='application/ld+json'>": "application/ld+json",
}


@pytest.mark.parametrize("opener", JS_SCRIPT_OPENERS)
def test_an_executable_script_is_audited_however_its_type_is_spelled(acorn_dir, tmp_path, opener):
    r = audit(acorn_dir, raw_page(tmp_path, f"{opener}\n{ESC}x.innerHTML = a.name;\n</script>"))
    assert r["scripts"] == 1 and r["skipped"] == []
    assert findings(r) != []


@pytest.mark.parametrize("opener", sorted(NON_JS_SCRIPTS))
def test_a_data_script_is_skipped_and_listed(acorn_dir, tmp_path, opener):
    r = audit(acorn_dir, raw_page(tmp_path, f'{opener}\n{{"a": <not js>}}\n</script><script>{ESC}x.innerHTML = "<i/>";</script>'))
    assert r["scripts"] == 1
    assert [k["type"] for k in r["skipped"]] == [NON_JS_SCRIPTS[opener]]
    assert findings(r) == []


def test_an_external_script_is_listed_as_not_audited(acorn_dir, tmp_path):
    r = audit(acorn_dir, raw_page(tmp_path, '<script src="https://example.invalid/x.js"></script><script src=/y.js></script>'))
    assert r["scripts"] == 0 and len(r["skipped"]) == 2


# ---- script extraction follows the HTML tokenizer (C-620 F-C620-1) --------------------------------------------------

CLOSERS = ["</script >", "</script\n>", "</script\t>", "</script foo>", "</script/>", "</SCRIPT >"]
OPENERS_TOKENIZER = ["<script\n>", "<script\ttype=module>", "<script/>x", "<script\n  type='text/javascript'\n>"]


@pytest.mark.parametrize("closer", CLOSERS)
def test_a_block_closed_the_way_a_browser_closes_it_is_audited(acorn_dir, tmp_path, closer):
    r = audit(acorn_dir, raw_page(tmp_path, f"<script>\n{ESC}x.innerHTML = a.name;\n{closer}"))
    assert r["scripts"] == 1 and r["structure"] == []
    assert findings(r) != []


@pytest.mark.parametrize("closer", CLOSERS)
def test_a_clean_block_with_an_odd_closer_is_clean_and_two_blocks_are_both_found(acorn_dir, tmp_path, closer):
    r = audit(acorn_dir, raw_page(tmp_path, f"<script>{ESC}x.innerHTML = esc(a);{closer}<script>y.innerHTML = esc(b);</script>"))
    assert r["scripts"] == 2 and len(r["sinks"]) == 2
    assert findings(r) == []


@pytest.mark.parametrize("opener", OPENERS_TOKENIZER)
def test_an_opener_with_whitespace_or_a_slash_is_audited(acorn_dir, tmp_path, opener):
    body = f"{opener}\n{ESC}x.innerHTML = a.name;\n</script>"
    r = audit(acorn_dir, raw_page(tmp_path, body))
    assert r["scripts"] == 1
    assert findings(r) != []


def test_a_tag_that_only_starts_with_script_is_not_a_block(acorn_dir, tmp_path):
    r = audit(acorn_dir, raw_page(tmp_path, f"<scripting>x</scripting><script-x>y</script-x><script>{ESC}x.innerHTML = esc(a);</script>"))
    assert r["scripts"] == 1 and r["structure"] == []
    assert findings(r) == []


def test_an_opener_inside_another_block_fails_the_audit(acorn_dir, tmp_path):
    r = audit(acorn_dir, raw_page(tmp_path, f'<script>{ESC}const t = "<script>"; x.innerHTML = esc(t);</script>'))
    assert any("openers" in p["why"] for p in r["structure"])
    assert findings(r) != []


def test_an_opener_that_never_closes_fails_the_audit(acorn_dir, tmp_path):
    r = audit(acorn_dir, raw_page(tmp_path, f"<script>{ESC}x.innerHTML = esc(a);</script><script>y.innerHTML = a.name;"))
    assert any("openers" in p["why"] for p in r["structure"])


def _shipped() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def test_a_new_unescaped_sink_in_a_block_closed_with_a_space_is_caught(acorn_dir, tmp_path):
    src = _shipped()
    head, _, tail = src.rpartition("</script>")
    mutant = tmp_path / "mutant.html"
    mutant.write_text(head + "\nAGENTS[0].owner && ($('events').innerHTML = AGENTS[0].owner);\n</script >" + tail, encoding="utf-8")
    assert findings(audit(acorn_dir, mutant)) != [], "the new sink in the last block was not audited"


def test_closing_the_shipped_blocks_with_a_space_changes_nothing(acorn_dir, tmp_path):
    base = audit(acorn_dir, HTML_PATH)
    mutant = tmp_path / "mutant.html"
    mutant.write_text(_shipped().replace("</script>", "</script >"), encoding="utf-8")
    r = audit(acorn_dir, mutant)
    assert (r["scripts"], len(r["sinks"]), len(r["skipped"])) == (base["scripts"], len(base["sinks"]), len(base["skipped"]))
    assert findings(r) == []


# ---- esc, scope and names (F-C508-2, Lane 10 objection 2) ------------------------------------------------------------

ESC_SHADOWS = {
    "a parameter named esc": ESC + "function g(esc) { x.innerHTML = esc(a.name); }",
    "an arrow parameter named esc": ESC + "const g = esc => { x.innerHTML = esc(a.name); };",
    "a nested declaration": ESC + "const g = () => { const esc = s => s; x.innerHTML = esc(a.name); };",
    "a nested function named esc": ESC + "function g() { function esc(s) { return s; } x.innerHTML = esc(a.name); }",
    "a loop variable": ESC + "for (const esc of list) { x.innerHTML = esc(a); }",
    "a catch variable": ESC + "try { f(); } catch (esc) { x.innerHTML = esc(a.name); }",
    "a destructured parameter": ESC + "function g({ esc }) { x.innerHTML = esc(a.name); }",
    "a shadow declared before the real one": "var esc = s => s;\n" + ESC_VAR + "x.innerHTML = esc(a.name);",
    "a second top-level declaration": ESC_VAR + "var esc = s => s;\nx.innerHTML = esc(a.name);",
    "a redeclaration without a value": ESC_VAR + "var esc;\nx.innerHTML = '<i/>';",
    "a second top-level function": ESC_VAR + "function esc(s) { return s; }\nx.innerHTML = esc(a.name);",
    "a reassignment": ESC + "esc = s => s;\nx.innerHTML = esc(a.name);",
    "a destructuring reassignment": ESC + "({ esc } = o);\nx.innerHTML = esc(a.name);",
    "an update of esc": ESC + "esc++;\nx.innerHTML = '<i/>';",
    "two functions with one name": ESC + "function row(a) { return '<b>' + esc(a) + '</b>'; }\nfunction row(a) { return a.name; }\nx.innerHTML = row(q);",
    "a function name reused by a var": ESC + "function row(a) { return '<b>' + esc(a) + '</b>'; }\nvar row = a => a.name;\nx.innerHTML = row(q);",
}


@pytest.mark.parametrize("name", sorted(ESC_SHADOWS))
def test_a_shadowed_or_repeated_name_is_reported(acorn_dir, tmp_path, name):
    r = audit(acorn_dir, page(tmp_path, ESC_SHADOWS[name]))
    assert r["structure"] != [], "nothing about the shadow or the repeated name was reported"
    assert findings(r) != []


def test_esc_declared_in_two_scripts_is_reported(acorn_dir, tmp_path):
    r = audit(acorn_dir, raw_page(tmp_path, f"<script>{ESC}x.innerHTML = esc(a);</script><script>{ESC}y.innerHTML = esc(b);</script>"))
    assert any("more than one script" in p["why"] for p in r["structure"])


def test_esc_used_in_a_second_script_without_its_own_binding_is_accepted(acorn_dir, tmp_path):
    r = audit(acorn_dir, raw_page(tmp_path, f"<script>{ESC}x.innerHTML = esc(a);</script><script>y.innerHTML = esc(b);</script>"))
    assert findings(r) == []


def test_two_distinct_function_names_are_not_a_finding(acorn_dir, tmp_path):
    r = audit(acorn_dir, page(tmp_path, ESC + "function a1(s) { return esc(s); }\nfunction a2(s) { return esc(s); }\nx.innerHTML = a1(q) + a2(q);"))
    assert findings(r) == []
