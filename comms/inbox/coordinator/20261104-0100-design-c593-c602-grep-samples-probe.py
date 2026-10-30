import subprocess
pat = open("/tmp/l10/g/pattern2.txt").read()
def hit(text):  # same flatten as the step: newlines become spaces, then grep -o -E -i
    flat = text.replace("\n", " ")
    r = subprocess.run(["grep", "-o", "-E", "-i", pat], input=flat, capture_output=True, text=True); return r.returncode == 0
MUST = {
 "double quoted src": '<script src="https://x.invalid/a.js"></script>', "single quoted href": "<link href='//x.invalid/a.css'>", "unquoted src": "<img src=//x.invalid/a.png>",
 "spaces around =": '<img src = "https://x.invalid/a.png">', "poster": '<video poster="https://x.invalid/p.png">', "ping": '<a ping="https://x.invalid/p">',
 "object data (no spaces)": '<object data="//x.invalid/o">', "data-src prefix": '<img data-src=//x.invalid/a.png>', "x-src prefix": '<i x-src="https://x.invalid/a">',
 "formaction": '<button formaction="https://x.invalid/p">', "srcset first entry": '<img srcset="https://x.invalid/a.png 2x">', "srcset second entry (comma + space)": '<img srcset="a.png 1x, https://x.invalid/b.png 2x">',
 "srcset third entry": '<img srcset="a.png 1x, b.png 2x, //x.invalid/c.png 3x">', "srcset newline separated": '<img srcset="a.png 1x,\n   https://x.invalid/b.png 2x">', "imagesrcset": '<link imagesrcset="//x.invalid/a.png">',
 "meta refresh": '<meta http-equiv="refresh" content="0;url=https://x.invalid">', "css url spaced": "a{background:url( https://x.invalid/i.png )}", "@import": '@import "https://x.invalid/a.css";',
 "fetch absolute": 'fetch("https://x.invalid/api")', "google fonts": "https://fonts.googleapis.com/css", "attribute split across lines": '<img src=\n"https://x.invalid/a.png">', "uppercase": '<IMG SRC="HTTPS://X.INVALID/a">',
 "CRLF page": '<img src="https://x.invalid/a.png">\r\n',
}
NOT = {"shipping = //": "const shipping = //x", "mapping=//": "mapping=//x", "bigsrc=//": "bigsrc=//x", "plain URL in prose": "see https://example.invalid", "data uri": '<link href="data:image/svg+xml,x">', "relative src": '<script src="/static/a.js"></script>', "comment //": "// src comment", "srcset relative only": '<img srcset="a.png 1x, b.png 2x">', "url(data:)": "a{background:url(data:image/png;base64,AAA)}", "xmlns attr (svg namespace)": "<svg xmlns='http://www.w3.org/2000/svg'>"}
GAPS = {  # spellings still not covered
 "data with spaces around =": '<object data = "https://x.invalid/o">', "srcset comma without space": '<img srcset="a.png 1x,https://x.invalid/b.png 2x">', "leading space inside quotes": '<img src=" https://x.invalid/a.png">',
 "background attr": '<td background="https://x.invalid/a.png">', "meta refresh content only": '<meta content="0;url=https://x.invalid" >', "dynamic import": 'import("https://x.invalid/m.js")', "WebSocket": 'new WebSocket("wss://x.invalid/s")',
 "sendBeacon": 'navigator.sendBeacon("https://x.invalid/b")', "XHR open": 'x.open("GET","https://x.invalid/a")', "EventSource": 'new EventSource("https://x.invalid/e")', "URL held in a variable": 'const u="https://x.invalid/"; fetch(u)',
 "html entity scheme": '<img src="&#104;ttps://x.invalid/a.png">', "backslash scheme": '<img src="\\\\x.invalid/a.png">', "image-set": "a{background:image-set(\"https://x.invalid/i.png\" 1x)}", "base href": '<base href="https://x.invalid/">',
 "xlink:href": '<use xlink:href="https://x.invalid/s.svg#a"/>', "link rel=stylesheet via protocol-less host": '<link rel="stylesheet" href="x.invalid/a.css">', "style attr url()": '<b style="background:url(//x.invalid/a)">',
 "window.open absolute": 'window.open("https://x.invalid/")', "location assign": 'location.href = "https://x.invalid/"', "iframe src": '<iframe src="https://x.invalid"></iframe>',
 "iframe srcdoc": '<iframe srcdoc="<img src=//x.invalid/a>"></iframe>', "src after tab": '<img\tsrc\t=\t"//x.invalid/a">',
}
bad = 0
for k,v in MUST.items():
    ok = hit(v); bad += not ok; print("ok  " if ok else "MISS", "caught" if ok else "NOT caught", k)
print("--- must NOT match"); fp = 0
for k,v in NOT.items():
    h = hit(v); fp += h; print("FALSE HIT" if h else "clean", k)
print("--- spellings still not covered (not a PR regression unless noted)")
for k,v in GAPS.items(): print("caught" if hit(v) else "NOT caught", k)
print("must-catch misses", bad, "| false hits", fp)
