import subprocess, sys
pat = open("/tmp/l10/g/pattern.txt").read()
def hit(text, flags=("-n","-E","-i")):
    r = subprocess.run(["grep", *flags, pat], input=text, capture_output=True, text=True); return r.returncode == 0
MUST = {   # external references that must be caught
 "double quoted src": '<script src="https://x.invalid/a.js"></script>', "single quoted href": "<link href='//x.invalid/a.css'>",
 "unquoted src": "<img src=//x.invalid/a.png>", "spaces around =": '<img src = "https://x.invalid/a.png">',
 "poster": '<video poster="https://x.invalid/p.png">', "object data": '<object data="//x.invalid/o">',
 "meta refresh": '<meta http-equiv="refresh" content="0;url=https://x.invalid">', "meta refresh uppercase": '<META HTTP-EQUIV=REFRESH CONTENT="0;URL=//x">',
 "css url double": "a{background:url(\"https://x.invalid/i.png\")}", "css url spaced": "a{background:url( https://x.invalid/i.png )}", "css url single": "a{background:url('//x.invalid/i.png')}",
 "@import": '@import "https://x.invalid/a.css";', "fetch absolute": 'fetch("https://x.invalid/api")', "fetch template": "fetch(`//x.invalid/api`)",
 "google fonts": "https://fonts.googleapis.com/css?family=X", "uppercase attr": '<IMG SRC="HTTPS://X.INVALID/a">', "action form": '<form action="https://x.invalid/p">',
}
MISS_SHAPES = {   # shapes the grep may not catch (each is an external reference or load)
 "srcset": '<img srcset="https://x.invalid/a.png 2x">', "attribute split across lines": '<img src=\n"https://x.invalid/a.png">',
 "formaction": '<button formaction="https://x.invalid/p">', "xlink:href": '<use xlink:href="https://x.invalid/s.svg#a"/>',
 "link preload via imagesrcset": '<link rel=preload imagesrcset="//x.invalid/a.png">', "ping": '<a ping="https://x.invalid/p">',
 "dynamic import": 'import("https://x.invalid/m.js")', "WebSocket": 'new WebSocket("wss://x.invalid/s")', "EventSource": 'new EventSource("https://x.invalid/e")',
 "XHR open": 'x.open("GET", "https://x.invalid/a")', "sendBeacon": 'navigator.sendBeacon("https://x.invalid/b")', "importScripts": 'importScripts("https://x.invalid/w.js")',
 "window.open absolute": 'window.open("https://x.invalid/")', "location assign": 'location.href = "https://x.invalid/"', "fetch via variable": 'const u = "https://x.invalid/"; fetch(u)',
 "html entity encoded": '<img src="&#104;ttps://x.invalid/a.png">', "backslash scheme": '<img src="\\\\x.invalid/a.png">',
 "image-set": "a{background:image-set(\"https://x.invalid/i.png\" 1x)}", "base href": '<base href="https://x.invalid/">',
}
SAFE = {"plain text mention": "see https://example.invalid for docs", "data uri icon": '<link rel="icon" href="data:image/svg+xml,%3Csvg%3E">', "relative src": '<script src="/static/app.js"></script>', "double slash comment": "// comment with src = value", "url data": "a{background:url(data:image/png;base64,AAA)}"}
bad = 0
for k, v in MUST.items():
    ok = hit(v); bad += not ok; print("ok  " if ok else "MISS", "caught" if ok else "NOT caught", k)
print("--- shapes beyond the stated list")
for k, v in MISS_SHAPES.items(): print("caught" if hit(v) else "not caught", k)
print("--- false positives on safe text")
for k, v in SAFE.items(): print("FALSE HIT" if hit(v) else "clean", k)
print("must-catch misses:", bad)
