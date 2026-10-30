"""Lane 10 probe (C-508): sinks the audit must REPORT (a case that comes back clean is a miss). Each page is tiny."""
import json, subprocess, sys, pathlib
AUD = "/tmp/pr314/services/ops-console/tests/innerhtml_audit.mjs"; ACORN = "/opt/node-tools"
def run(js):
    p = pathlib.Path("/tmp/l10/ih/p.html"); p.write_text(f"<html><body><script>\nfunction esc(s){{return String(s??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[c]));}}\n{js}\n</script></body></html>")
    r = subprocess.run(["node", AUD, ACORN, str(p)], capture_output=True, text=True)
    if r.returncode: return "ERR " + r.stderr[-100:]
    o = json.loads(r.stdout.strip().splitlines()[-1]); return o
CASES = {   # name: (js, expect_flagged)
 "for-of loop variable into sink": ("const rows = window.data; let out=''; for (const r of rows) { out += r; } document.body.innerHTML = out;", 1),
 "for-in loop variable": ("let out=''; for (const k in window.data) { out += k; } document.body.innerHTML = out;", 1),
 "computed property sink": ("document.body['innerHTML'] = window.x;", 1),
 "computed via variable": ("const k='innerHTML'; document.body[k] = window.x;", 1),
 "Object.assign sink": ("Object.assign(document.body, {innerHTML: window.x});", 1),
 "document.writeln": ("document.writeln(window.x);", 1),
 "aliased document.write": ("const d = document; d.write(window.x);", 1),
 "srcdoc": ("document.querySelector('iframe').srcdoc = window.x;", 1),
 "createContextualFragment": ("document.createRange().createContextualFragment(window.x);", 1),
 "setAttribute onclick": ("document.body.setAttribute('onclick', window.x);", 1),
 "href javascript:": ("document.querySelector('a').href = window.x;", 1),
 "eval": ("eval(window.x);", 1),
 "setTimeout string": ("setTimeout(window.x, 1);", 1),
 "new Function": ("new Function(window.x)();", 1),
 "DOMParser then append": ("const d = new DOMParser().parseFromString(window.x,'text/html'); document.body.append(d.body.firstChild);", 1),
 "local esc shadow": ("function f(esc){ document.body.innerHTML = esc(window.x); } f(s=>s);", 1),
 "const esc shadow inside function": ("function f(){ const esc = s => s; document.body.innerHTML = esc(window.x); } f();", 1),
 "second function same name, unsafe first": ("function row(x){ return window.y; } (function(){ function row(x){ return esc(x); } document.body.innerHTML = row(1); })(); document.body.innerHTML = row(2);", 1),
 "unsafe helper defined after the safe one": ("function row(x){ return esc(x); } function g(){ function row(x){ return window.y; } return row(1); } document.body.innerHTML = g();", 1),
 "catch param": ("try { throw 1 } catch (e) { document.body.innerHTML = e; }", 1),
 "destructured param": ("function f({a}){ document.body.innerHTML = a; } f(window.x);", 1),
 "await result": ("(async () => { document.body.innerHTML = await fetch('/x').then(r=>r.text()); })();", 1),
 "arguments object": ("function f(){ document.body.innerHTML = arguments[0]; } f(window.x);", 1),
 "this property": ("const o = {v: window.x, f(){ document.body.innerHTML = this.v; }}; o.f();", 1),
 "array join of data": ("document.body.innerHTML = [window.x].join('');", 1),
 "innerHTML read-modify": ("document.body.innerHTML = document.body.innerHTML + window.x;", 1),
 "toString on data": ("document.body.innerHTML = window.x.toString();", 1),
 "number cast ok (control)": ("document.body.innerHTML = Number(window.x);", 0),
 "esc ok (control)": ("document.body.innerHTML = esc(window.x);", 0),
 "template of esc (control)": ("document.body.innerHTML = `<b>${esc(window.x)}</b>`;", 0),
}
miss = 0
for name, (js, want) in CASES.items():
    o = run(js)
    if isinstance(o, str): print("ERR ", name, o); continue
    flagged = any(s["problems"] for s in o["sinks"]); nsinks = len(o["sinks"])
    ok = (flagged == bool(want)); miss += (not ok)
    print(f"{'ok  ' if ok else 'MISS'} sinks={nsinks} flagged={flagged!s:5} {name}")
print("misses", miss)
