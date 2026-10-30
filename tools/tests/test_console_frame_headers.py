"""C-96 (reviewer C-91, #27 finding 3, proven by grep): the ops-console carries destructive
controls (kill, drill, FLEET HALT) and keeps the perimeter secret in sessionStorage, yet no
Content-Security-Policy, X-Frame-Options or nosniff was set anywhere, so another origin could
frame the console and clickjack it. The console catch-all ``handle`` of the base route map
(which Caddyfile.gb10 imports for BOTH listeners) and of the Fly edge now sets the headers.

Static: reads the Caddyfiles; no docker, no network."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CADDY_BASE = REPO / "integration" / "demo" / "Caddyfile"
CADDY_GB10 = REPO / "integration" / "demo" / "Caddyfile.gb10"
CADDY_FLY = REPO / "integration" / "fly" / "Caddyfile"

#: C-456 widened the policy from frame-ancestors alone to no other origin for any load, and added the referrer and
#: cache headers (design note: operator key on the console, channels 13 and 15).
CSP = "default-src 'none'; connect-src 'self'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'"
WANT = ("X-Frame-Options DENY",
        f"Content-Security-Policy \"{CSP}\"",
        "X-Content-Type-Options nosniff",
        "Referrer-Policy no-referrer",
        "Cache-Control no-store")


def _code(p: Path) -> list[str]:
    text = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    return [ln.split("#", 1)[0].strip() for ln in text.splitlines()
            if ln.split("#", 1)[0].strip()]


def _console_block(lines: list[str]) -> list[str]:
    """The bare ``handle {`` whose body proxies to the console (port 8011)."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i] == "handle {":
            depth, body = 1, []
            i += 1
            while i < len(lines) and depth:
                depth += lines[i].count("{") - lines[i].count("}")
                if depth:
                    body.append(lines[i])
                i += 1
            if any(ln.startswith("reverse_proxy") and ln.endswith(":8011") for ln in body):
                out = body
        else:
            i += 1
    assert out, "no console catch-all handle found"
    return out


def _problems(lines: list[str]) -> list[str]:
    body = _console_block(lines)
    bad = [f"missing {want}" for want in WANT if want not in body]
    if "header {" not in body:
        bad.append("no header block")
    if not body[-1].startswith("reverse_proxy"):
        bad.append("the proxy is not last")
    return bad


@pytest.mark.parametrize("caddy", [CADDY_BASE, CADDY_FLY], ids=["base", "fly"])
def test_the_console_catch_all_sets_the_frame_and_sniffing_headers(caddy):
    assert _problems(_code(caddy)) == []


@pytest.mark.parametrize("caddy", [CADDY_BASE, CADDY_FLY], ids=["base", "fly"])
@pytest.mark.parametrize("drop", range(len(WANT)))
def test_dropping_any_one_header_turns_the_check_red(caddy, drop):
    lines = [ln for ln in _code(caddy) if ln != WANT[drop]]
    assert _problems(lines) == [f"missing {WANT[drop]}"]


@pytest.mark.parametrize("caddy", [CADDY_BASE, CADDY_FLY], ids=["base", "fly"])
def test_moving_the_headers_out_of_the_console_handle_turns_the_check_red(caddy):
    lines = [ln for ln in _code(caddy) if ln not in WANT]
    assert any(p.startswith("missing") for p in _problems(lines))


def test_the_gb10_listeners_import_the_base_route_map_so_they_inherit_the_headers():
    text = "\n".join(_code(CADDY_GB10))
    assert "import" in text and "Caddyfile" in text
