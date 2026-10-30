"""C-456 (design note: operator key on the console, channels 13 and 15; reviewer C-91): the console's response policy.

The console keeps the perimeter secret and the operator key in the tab's sessionStorage, so one DOM injection could
send them to another origin. Two things keep that from happening, and both are pinned here:

* the console catch-all `handle` of the base Caddyfile and of the Fly edge sets a Content-Security-Policy that allows
  nothing from another origin (`default-src 'none'`, same-origin `connect-src`, `data:` images, inline script and
  style only), plus `Referrer-Policy: no-referrer` and `Cache-Control: no-store` (the exact lines are pinned in
  test_console_frame_headers.py; this file checks the POLICY, so a weaker value that someone also edits there is
  still caught);
* the page itself loads no external source, so the policy blocks nothing it needs (a grep over console.html).

Static: reads files; no docker, no network. A browser check (Chromium, a stub estate) was run once by hand for the PR,
because jsdom does not enforce CSP.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_console_frame_headers import CADDY_BASE, CADDY_FLY, _code, _console_block

REPO = Path(__file__).resolve().parents[2]
CONSOLE = REPO / "services" / "ops-console" / "src" / "ops_console" / "static" / "console.html"


def policy_of(caddy: Path) -> str:
    (line,) = [ln for ln in _console_block(_code(caddy)) if ln.startswith("Content-Security-Policy ")]
    return line.split(" ", 1)[1].strip().strip('"')


def directives(policy: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for part in policy.split(";"):
        words = part.split()
        if words:
            out[words[0]] = words[1:]
    return out


def policy_problems(policy: str) -> list[str]:
    d = directives(policy)
    want = {"default-src": ["'none'"], "connect-src": ["'self'"], "img-src": ["data:"],
            "style-src": ["'unsafe-inline'"], "script-src": ["'unsafe-inline'"], "frame-ancestors": ["'none'"]}
    out = [f"{k} is {d.get(k)}, want {v}" for k, v in want.items() if d.get(k) != v]
    out += [f"unexpected directive {k}" for k in d if k not in want]
    return out


#: Elements whose reference is a LOAD: under this policy only `data:` (and `#` fragments) may be loaded, so even a
#: same-origin file is blocked (img-src data:, script-src and style-src have no 'self'). Links and form actions
#: are navigations, which the policy does not restrict.
LOADERS = {"img", "script", "link", "source", "video", "audio", "track", "input", "image", "embed", "iframe", "object"}


def _data_or_fragment(v: str) -> bool:
    return not v or v.startswith(("data:", "#"))


def _same_origin_or_data(v: str) -> bool:
    return _data_or_fragment(v) or (v.startswith("/") and not v.startswith("//"))


def external_loads(html: str) -> list[str]:
    """Places the page would load or open something from another origin, or run code from a string."""
    scripts = re.findall(r"(?is)<script\b[^>]*>(.*?)</script>", html)
    styles = re.findall(r"(?is)<style\b[^>]*>(.*?)</style>", html)
    markup = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", lambda m: m.group(0).split(">", 1)[0] + "></" + m.group(1) + ">", html)
    out: list[str] = []
    css = list(styles)
    for tag in re.findall(r"(?s)<[a-zA-Z][^>]*>", markup):
        for m in re.finditer(r"""(?is)[\s/]((?:src|href|action|formaction|poster|srcset|ping|data|cite))\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""", tag):
            v = (m.group(3) or m.group(4) or m.group(5) or "").strip()
            name = re.match(r"<([A-Za-z0-9]+)", tag).group(1).lower()
            ok = _data_or_fragment(v) if name in LOADERS else _same_origin_or_data(v)
            if not ok:
                out.append(f"<{name} {m.group(1)}={v[:60]}")
        css += [a or b for a, b in re.findall(r"""(?is)\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", tag)]
    for block in css:
        for m in re.finditer(r"""(?is)url\(\s*['"]?([^'")]*)""", block):
            if not _same_origin_or_data(m.group(1).strip()):
                out.append(f"url({m.group(1).strip()[:60]})")
        out += [f"@import {m.group(0)[:40]}" for m in re.finditer(r"(?i)@import\b[^;]*", block)]
    out += [f"{m.group(1)}({m.group(2)[:50]}" for m in re.finditer(
        r"""(?i)\b(fetch|XMLHttpRequest\.open|EventSource|WebSocket|sendBeacon|importScripts|window\.open|open)\s*\(\s*['"`]\s*((?:https?:|wss?:|//)[^'"`]*)""",
        "\n".join(scripts) + "\n" + markup)]
    out += [m.group(0) for m in re.finditer(r"(?i)<(iframe|object|embed|base|frame|applet)\b", markup)]
    out += [m.group(0)[:50] for m in re.finditer(r"""(?is)<meta[^>]+http-equiv\s*=\s*["']?(refresh|set-cookie|content-security-policy)""", markup)]
    out += re.findall(r"(?<![\w.])eval\s*\(|new\s+Function\s*\(", "\n".join(scripts))
    return out


@pytest.mark.parametrize("caddy", [CADDY_BASE, CADDY_FLY], ids=["base", "fly"])
def test_the_console_policy_allows_nothing_from_another_origin(caddy):
    assert policy_problems(policy_of(caddy)) == []


def test_both_edges_carry_the_same_policy():
    assert policy_of(CADDY_BASE) == policy_of(CADDY_FLY)


@pytest.mark.parametrize("old,new", [
    ("default-src 'none'", "default-src 'self'"),
    ("connect-src 'self'", "connect-src 'self' https://example.invalid"),
    ("connect-src 'self'", "connect-src *"),
    ("img-src data:", "img-src data: https:"),
    ("script-src 'unsafe-inline'", "script-src 'unsafe-inline' 'unsafe-eval'"),
    ("script-src 'unsafe-inline'", "script-src 'unsafe-inline' https://cdn.example.invalid"),
    ("style-src 'unsafe-inline'", "style-src 'unsafe-inline' blob:"),
    ("frame-ancestors 'none'", "frame-ancestors 'self'"),
    ("; frame-ancestors 'none'", ""),
    ("connect-src 'self'; ", ""),
    ("frame-ancestors 'none'", "frame-ancestors 'none'; form-action *"),
    ("frame-ancestors 'none'", "frame-ancestors 'none'; form-action 'self'"),
])
def test_a_weaker_policy_is_caught(old, new):
    policy = policy_of(CADDY_BASE)
    assert old in policy
    assert policy_problems(policy.replace(old, new)) != []


def test_the_page_loads_nothing_from_another_origin():
    html = CONSOLE.read_text(encoding="utf-8")
    assert len(html) > 100_000, "the console page is large; a short read means the path is wrong"
    assert external_loads(html) == []


@pytest.mark.parametrize("snippet", [
    '<script src="https://cdn.example.invalid/x.js"></script>',
    '<script src=//cdn.example.invalid/x.js></script>',
    "<link rel='stylesheet' href='https://example.invalid/a.css'>",
    '<link rel="preconnect" href="https://example.invalid">',
    '<img src="//example.invalid/a.png">',
    '<img src="http://example.invalid/a.png">',
    '<form action="https://example.invalid/collect"></form>',
    '<div style="background:url(https://example.invalid/a.png)"></div>',
    "<style>@import url('https://example.invalid/a.css');</style>",
    "<script>fetch('https://example.invalid/x')</script>",
    "<script>new WebSocket('wss://example.invalid/s')</script>",
    "<script>navigator.sendBeacon('https://example.invalid/b')</script>",
    "<script>window.open('https://example.invalid/')</script>",
    "<script>eval(code)</script>",
    "<script>new Function('x')</script>",
    '<iframe src="/x"></iframe>',
    '<script src="/app.js"></script>',
    '<img src="/logo.png">',
    '<link rel="stylesheet" href="/x.css">',
    '<link rel="icon" href="/favicon.ico">',
    '<meta http-equiv="refresh" content="0;url=https://example.invalid">',
    '<base href="https://example.invalid/">',
])
def test_each_external_load_shape_is_caught(snippet):
    html = CONSOLE.read_text(encoding="utf-8")
    assert "</body>" in html
    assert external_loads(html.replace("</body>", snippet + "</body>", 1)) != []


@pytest.mark.parametrize("snippet", [
    '<img src="data:image/png;base64,AAAA">',
    '<a href="#top">x</a>',
    '<a href="/docs/x">x</a>',
    '<form action="/api/check" method="post"></form>',
    '<script>fetch("/api/overview")</script>',
    '<div style="background:url(data:image/png;base64,AAAA)"></div>',
])
def test_same_origin_and_data_references_are_allowed(snippet):
    html = CONSOLE.read_text(encoding="utf-8")
    assert external_loads(html.replace("</body>", snippet + "</body>", 1)) == []
