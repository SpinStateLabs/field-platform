import json, subprocess, pathlib
AUD="/tmp/pr339/services/ops-console/tests/innerhtml_audit.mjs"; AC="/tmp/l10/acorn-8.14.0"
ESC = "function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}"
def page(body): 
    p=pathlib.Path("/tmp/l10/ih/q.html"); p.write_text(body); r=subprocess.run(["node",AUD,AC,str(p)],capture_output=True,text=True)
    if r.returncode: return "ERR "+r.stderr[-120:]
    return json.loads(r.stdout.strip().splitlines()[-1])
def flagged(o): return isinstance(o,dict) and (any(s["problems"] for s in o["sinks"]) or bool(o.get("structure")))
BAD = window = "document.body.innerHTML = window.x;"
C = {
 "type=module": f'<script type="module">{ESC}\n{BAD}</script>',
 "type=text/javascript": f'<script type="text/javascript">{ESC}\n{BAD}</script>',
 "type uppercase": f'<script TYPE="MODULE">{ESC}\n{BAD}</script>',
 "type=text/babel (JSX)": f'<script type="text/babel">{ESC}\n{BAD}</script>',
 "type=application/javascript": f'<script type="application/javascript">{ESC}\n{BAD}</script>',
 "nomodule + async attrs": f'<script async nomodule>{ESC}\n{BAD}</script>',
 "script with src (external) ": '<script src="https://x.invalid/a.js"></script>',
 "type=importmap (data, control)": '<script type="importmap">{"imports":{}}</script>',
 "type=application/json (control)": '<script type="application/json">{"a":1}</script>',
 "static inline handler attr": f'<body><button onclick="doIt()">x</button><script>{ESC}</script></body>',
 "static inline handler with data": f'<body><img src=x onerror="alert(1)"><script>{ESC}</script></body>',
 "templated handler (innerHTML)": f'<script>{ESC}\nconst v = window.x; document.body.innerHTML = `<a onclick="go(${{esc(v)}})">x</a>`;</script>',
 "templated javascript: href": f'<script>{ESC}\nconst v = window.x; document.body.innerHTML = `<a href="javascript:${{esc(v)}}">x</a>`;</script>',
 "templated style attr": f'<script>{ESC}\nconst v = window.x; document.body.innerHTML = `<b style="background:url(${{esc(v)}})">x</b>`;</script>',
 "templated href with esc (control: href=escaped value)": f'<script>{ESC}\nconst v = window.x; document.body.innerHTML = `<a href="${{esc(v)}}">x</a>`;</script>',
 "esc in single-quoted attr context": f'<script>{ESC}\nconst v = window.x; document.body.innerHTML = `<a title=${{esc(v)}}>x</a>`;</script>',
 "script in a template literal string (not a script)": f'<script>{ESC}\nconst t = "<script>" + "x"; document.body.innerHTML = esc(t);</script>',
 "closing-tag in JS string splits regex": f'<script>{ESC}\nconst s = "</scr" + "ipt>"; document.body.innerHTML = esc(s);</script><script>{BAD}</script>',
 "HTML comment hides script": f'<!-- <script>{BAD}</script> --><script>{ESC}</script>',
 "script inside <template>": f'<template><script>{BAD}</script></template><script>{ESC}</script>',
 "script inside svg": f'<svg><script>{BAD}</script></svg><script>{ESC}</script>',
 "CDATA / odd close tag spacing": f'<script>{ESC}\n{BAD}</script >',
 "uppercase SCRIPT tag": f'<SCRIPT>{ESC}\n{BAD}</SCRIPT>',
}
CTRL = {"type=importmap (data, control)", "type=application/json (control)", "templated href with esc (control: href=escaped value)", "script in a template literal string (not a script)"}
bad=0
for k,h in C.items():
    o=page(h)
    if isinstance(o,str): print("ERR ",k,o); continue
    f=flagged(o); want = not (k in CTRL)
    # 'static inline handler' pages may be flagged via structure; scripts count shown
    ok = (f==want); bad += (not ok)
    print(f"{'ok  ' if ok else 'MISS'} scripts={o['scripts']} sinks={len(o['sinks'])} structure={len(o.get('structure',[]))} flagged={f!s:5} {k}")
print("misses", bad)
