"""GB10 console hop over TLS (Phase G Stage 0, design section 4.2 Option A).

The GB10 proxy (Caddy) gets an HTTPS listener with Caddy's internal CA on host
port 18443, and Caddy's data dir (the internal root CA) lives on the named
volume caddy_data so the root the owner pins on rog-command survives every
recreate. PHASE 1 of 2: plain-HTTP 18080 stays published exactly as on main (all
interfaces) so no caller breaks; PHASE 2 (a separate change, after the callers
are migrated) rebinds it to 127.0.0.1. The base compose file (CI compose-smoke,
the demo) is unchanged: 8080, plain HTTP, ./Caddyfile.

Static: reads the YAML, the Caddyfiles, the runbook and ci.yml (no docker). The
compose-level proof (the listener answers, the certificate verifies against the
exported root for 192.0.2.10 with no SNI / gx10 / localhost, the root survives a
recreate with anonymous volumes renewed, 18080 still answers) is the CI
compose-upgrade-smoke step "GB10 TLS listener". Each mutant at the bottom must
turn a check RED.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "integration" / "demo"
BASE = DEMO / "docker-compose.yml"
GB10 = DEMO / "docker-compose.gb10.yml"
CADDY_BASE = DEMO / "Caddyfile"
CADDY_GB10 = DEMO / "Caddyfile.gb10"
CADDY_FLY = REPO / "integration" / "fly" / "Caddyfile"
RUNBOOK = REPO / "docs" / "runbooks" / "v1.2-deploy-rollback.md"
CI = REPO / ".github" / "workflows" / "ci.yml"

LAN_IP = "{$FIELD_GB10_LAN_IP}"  # the Caddyfile reads the address from the estate .env
TLS_NAMES = ("https://"+LAN_IP+":8443", "https://gx10:8443", "https://localhost:8443")
ROUTES_TARGET = "/etc/caddy/Caddyfile.routes"
ROOT_PATH = "/data/caddy/pki/authorities/local/root.crt"


class _Override(list):
    """A sequence tagged `!override` (Compose replaces instead of merging)."""


class _Loader(yaml.SafeLoader):
    pass


def _override(loader, node):
    if isinstance(node, yaml.SequenceNode):
        return _Override(loader.construct_sequence(node))
    return loader.construct_scalar(node)


_Loader.add_constructor("!override", _override)


def _load(text: str) -> dict:
    return yaml.load(text, Loader=_Loader)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def _effective(base_svc: dict, over_svc: dict, key: str) -> list:
    """Compose's result for a list key: `!override` replaces; otherwise ports
    append and short-syntax volumes merge by container target."""
    b, o = list(base_svc.get(key) or []), over_svc.get(key)
    if o is None:
        return b
    if isinstance(o, _Override):
        return list(o)
    if key == "volumes":
        merged = {_vol_target(v): v for v in b}
        merged.update({_vol_target(v): v for v in o})
        return list(merged.values())
    return b + list(o)


def _vol_target(v: str) -> str:
    return _split_vol(v)[1]


def _split_vol(v: str) -> tuple[str, str, str]:
    assert isinstance(v, str), f"only short-syntax volumes are expected on the proxy: {v!r}"
    m = re.fullmatch(r"(\$\{[^}]*\}[^:]*|[^:]+):([^:]+)(?::([^:]+))?", v)
    assert m, v
    return m.group(1), m.group(2), m.group(3) or "rw"


def _split_port(p) -> tuple[str, str, str]:
    """(host_ip, host_port, container_port). A missing host_ip means ALL
    interfaces (0.0.0.0 and ::), which is what Docker does."""
    assert isinstance(p, str), f"only short-syntax ports are expected on the proxy: {p!r}"
    parts = p.split(":")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return "", parts[0], parts[1]
    return "", parts[0], parts[0]


def _strip_comments(caddy: str) -> str:
    return "\n".join(ln.split("#", 1)[0].rstrip() for ln in caddy.splitlines())


def _blocks(caddy: str) -> list[tuple[str, str]]:
    """Top-level Caddyfile blocks as (header, body); a global options block has header ''."""
    text = _strip_comments(caddy)
    out, depth, header, body = [], 0, "", []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if depth == 0:
            if s.endswith("{"):
                header, body = s[:-1].strip(), []
                depth = 1
            else:
                out.append((s, ""))  # a bare top-level directive (import)
            continue
        depth += s.count("{") - s.count("}")
        if depth == 0:
            out.append((header, "\n".join(body)))
        else:
            body.append(s)
    assert depth == 0, "unbalanced braces"
    return out


# --- checks (each raises AssertionError on a violation; the mutants reuse them) -----------------


def check_base_unchanged(base_text: str, caddy_base: str) -> None:
    base = _load(base_text)
    proxy = base["services"]["proxy"]
    assert proxy["image"].startswith("caddy:"), proxy["image"]
    assert list(proxy["ports"]) == ["8080:8080"], f"base proxy ports changed: {proxy['ports']}"
    assert list(proxy["volumes"]) == ["./Caddyfile:/etc/caddy/Caddyfile:ro"], \
        f"base proxy volumes changed: {proxy['volumes']}"
    assert "caddy_data" not in (base.get("volumes") or {}), "caddy_data belongs to the GB10 override only"
    code = _strip_comments(caddy_base)
    assert re.search(r"(?m)^:8080 \{$", code), "base Caddyfile must keep the plain-HTTP :8080 site"
    assert "tls" not in code and "8443" not in code and "https://" not in code, \
        "the base Caddyfile (CI, demo) must stay plain HTTP"
    # The route map is shared by both GB10 listeners (imported, not copied): pin its prefix -> upstream
    # table so a dropped or re-pointed route is a finding. Only that table is pinned: header rules or
    # other directives would be refused below as unexpected, but their content is not modelled.
    assert _route_table(caddy_base) == BASE_ROUTES, f"base route map changed: {_route_table(caddy_base)}"


#: integration/demo/Caddyfile's :8080 site: handle_path prefix -> upstream ("" = the bare catch-all handle).
BASE_ROUTES = {
    "/registry/*": "registry:8001", "/ledger/*": "ledger:8002", "/delegation/*": "delegation:8003",
    "/sentinel/*": "sentinel:8004", "/killswitch/*": "killswitch:8005", "/governor/*": "governor:8006",
    "/replay/*": "replay:8007", "/gateway/*": "forcegw:8009", "/federation/*": "fedbroker:8010",
    "/lifecycle/*": "lifecycle:8012", "/attest/*": "attest:8013", "/crosswalk/*": "crosswalk:8008",
    "": "console:8011",
}


#: Key rotation slice R2 (tools/tests/test_kr_edge_block_r2.py): the edge block that refuses
#: /operator/verify-hash and /operator/rotation-state except from the proxy's own loopback. Exactly
#: these lines, first in the :8080 site; any other directive is still refused below.
R2_EDGE_BLOCK = [
    "@kr_internal_remote {",
    "path */operator/verify-hash* */operator/rotation-state*",
    "not remote_ip 127.0.0.0/8 ::1",
    "}",
    "@kr_internal_forwarded {",
    "path */operator/verify-hash* */operator/rotation-state*",
    "header X-Forwarded-For *",
    "}",
    "rewrite @kr_internal_remote /__field_internal_route_refused",
    "rewrite @kr_internal_forwarded /__field_internal_route_refused",
    "handle /__field_internal_route_refused {",
    'respond "internal route: loopback only" 403',
    "}",
]


#: C-96 (tools/tests/test_console_frame_headers.py): the response headers of the console catch-all,
#: exactly these lines in one `header` block inside the bare `handle`; nowhere else, nothing more.
CONSOLE_FRAME_HEADERS = [
    "X-Frame-Options DENY",
    "Content-Security-Policy \"default-src 'none'; connect-src 'self'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'\"",
    "X-Content-Type-Options nosniff",
    "Referrer-Policy no-referrer",
    "Cache-Control no-store",
]


def _route_table(caddy: str) -> dict:
    sites = [b for h, b in _blocks(caddy) if h == ":8080"]
    assert len(sites) == 1, "exactly one :8080 site expected in the base Caddyfile"
    lines = sites[0].splitlines()
    assert lines[:len(R2_EDGE_BLOCK)] == R2_EDGE_BLOCK, \
        f"the R2 edge block must open the base :8080 site unchanged: {lines[:len(R2_EDGE_BLOCK)]}"
    table, current, in_headers, seen_headers = {}, None, None, []
    for line in lines[len(R2_EDGE_BLOCK):]:
        if in_headers is not None:
            if line == "}":
                assert in_headers == CONSOLE_FRAME_HEADERS,                     f"the console header block must be exactly the three frame headers: {in_headers}"
                seen_headers.append(current)
                in_headers = None
            else:
                in_headers.append(line)
            continue
        if line == "header {":
            assert current == "", "a header block is allowed only in the console catch-all handle"
            in_headers = []
            continue
        m = re.fullmatch(r"handle_path (\S+) \{|handle \{", line)
        if m:
            current = m.group(1) or ""
            continue
        m = re.fullmatch(r"reverse_proxy (\S+)", line)
        if m:
            assert current is not None and current not in table, f"reverse_proxy outside a single handle: {line}"
            table[current] = m.group(1)
            continue
        if line == "}":
            current = None
            continue
        raise AssertionError(f"unexpected directive in the base :8080 site: {line!r}")
    assert in_headers is None, "unterminated header block"
    assert seen_headers in ([], [""]), f"header blocks outside the console catch-all: {seen_headers}"
    return table


def check_gb10_ports(base_text: str, gb10_text: str) -> None:
    base, over = _load(base_text), _load(gb10_text)
    over_proxy = over["services"]["proxy"]
    assert isinstance(over_proxy.get("ports"), _Override), \
        "GB10 proxy ports must be `!override` (a merge would also publish the base 8080 on all interfaces)"
    ports = [_split_port(p) for p in _effective(base["services"]["proxy"], over_proxy, "ports")]
    by_host = {hp: (ip, cp) for ip, hp, cp in ports}
    assert len(by_host) == len(ports), f"duplicate host port: {ports}"
    assert "18080" in by_host, f"PHASE 1: plain HTTP 18080 must stay published (callers not yet migrated): {ports}"
    assert "18443" in by_host, f"the TLS listener must be published on 18443: {ports}"
    assert set(by_host) == {"18080", "18443"}, f"GB10 proxy must publish 18080 and 18443 only: {ports}"
    # PHASE 1 of 2: 18080 exactly as on main (`18080:8080`, all interfaces) so no LAN caller breaks at
    # deploy. The loopback rebind is PHASE 2, a separate change made after every caller is on 18443.
    assert by_host["18080"] == ("", "8080"), \
        f"PHASE 1: 18080 must stay published as on main (all interfaces -> :8080), got {by_host['18080']}"
    assert by_host["18443"] == ("", "8443"), \
        f"18443 must be published on all interfaces (the LAN) to the TLS site on :8443: {by_host['18443']}"


def check_gb10_volumes(base_text: str, gb10_text: str) -> None:
    base, over = _load(base_text), _load(gb10_text)
    over_proxy = over["services"]["proxy"]
    vols = {_vol_target(v): _split_vol(v) for v in _effective(base["services"]["proxy"], over_proxy, "volumes")}
    assert "/data" in vols, "Caddy's data dir (/data) must be on a named volume on the GB10"
    src, _, mode = vols["/data"]
    assert src == "caddy_data", f"/data must be the named volume caddy_data, got {src!r}"
    assert mode == "rw", "Caddy writes its CA and certificates to /data: it must be read-write"
    assert "caddy_data" in (over.get("volumes") or {}), "caddy_data must be declared in the GB10 override's volumes"
    assert vols.get("/etc/caddy/Caddyfile") == ("./Caddyfile.gb10", "/etc/caddy/Caddyfile", "ro"), vols
    assert vols.get(ROUTES_TARGET) == ("./Caddyfile", ROUTES_TARGET, "ro"), vols
    assert set(vols) == {"/etc/caddy/Caddyfile", ROUTES_TARGET, "/data"}, f"unexpected proxy mounts: {sorted(vols)}"
    # nothing else in the GB10 topology gets the Caddy data dir
    for name, svc in over["services"].items():
        if name != "proxy":
            assert not any(isinstance(v, str) and v.startswith("caddy_data:") for v in (svc.get("volumes") or [])), name


def check_gb10_caddyfile(caddy_gb10: str) -> None:
    blocks = _blocks(caddy_gb10)
    assert blocks and blocks[0][0] == "", "the global options block must come first"
    glob = blocks[0][1].splitlines()
    assert f"default_sni {LAN_IP}" in glob, "an IP-literal client sends no SNI: default_sni must name the LAN IP"
    assert "skip_install_trust" in glob
    assert "auto_https disable_redirects" in glob, "no HTTP->HTTPS redirect server may be added"
    assert sorted(glob) == sorted([f"default_sni {LAN_IP}", "skip_install_trust", "auto_https disable_redirects"]), \
        f"unexpected global options: {glob}"
    assert ("import " + ROUTES_TARGET, "") in blocks, "the GB10 file must import the unchanged base route map"
    sites = [(h, b) for h, b in blocks if h.startswith("https://")]
    assert len(sites) == 1, f"exactly one TLS site expected: {[h for h, _ in sites]}"
    header, body = sites[0]
    names = tuple(n.strip() for n in header.split(","))
    assert names == TLS_NAMES, f"TLS site names: {names}"
    lines = body.splitlines()
    assert "tls internal" in lines, "the TLS site must use Caddy's internal CA"
    assert "reverse_proxy 127.0.0.1:8080" in lines, "the TLS site must hand off to the :8080 route map"
    # ONLY those two directives: a direct route inside the TLS site would bypass the shared route map
    # (and any future header strip there), so 18443 and 18080 could diverge.
    assert sorted(lines) == sorted(["tls internal", "reverse_proxy 127.0.0.1:8080"]), \
        f"the TLS site must contain only `tls internal` and `reverse_proxy 127.0.0.1:8080`: {lines}"
    assert len(blocks) == 3, f"expected exactly: global options, the route import, one TLS site: {[h for h, _ in blocks]}"
    assert not any(h.startswith("http://") or h.startswith(":18080") for h, _ in blocks)


# --- the real files ------------------------------------------------------------------------------


def test_base_compose_and_base_caddyfile_are_unchanged_plain_http_8080():
    check_base_unchanged(_read(BASE), _read(CADDY_BASE))


def test_gb10_phase1_keeps_18080_as_on_main_and_adds_18443():
    check_gb10_ports(_read(BASE), _read(GB10))


def test_gb10_persists_caddy_data_on_a_named_volume_at_data():
    check_gb10_volumes(_read(BASE), _read(GB10))


def test_gb10_caddyfile_has_the_tls_internal_site_and_imports_the_base_routes():
    check_gb10_caddyfile(_read(CADDY_GB10))


def test_fly_caddyfile_is_not_touched():
    code = _strip_comments(_read(CADDY_FLY))
    assert re.search(r"(?m)^:8080 \{$", code) and "tls" not in code and "8443" not in code


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


IMPORT_2B = (r"if ($checkPassed -eq $true) { Import-Certificate -FilePath $pem -CertStoreLocation Cert:\CurrentUser\Root }"
             r" else { throw 'check 2a did not pass: import nothing' }")


def _ps_block(text: str) -> list:
    """The lines of the first ```powershell block in text."""
    m = re.search(r"```powershell\n(.*?)```", text, re.S)
    assert m, "no powershell block"
    return m.group(1).splitlines()


def check_trust_pin(sub: str) -> None:
    """Section 8 steps 2a/2b: the guard is ONE if/elseif/else statement that sets $checkPassed only in its else
    arm (safe when pasted line by line), and the only Import-Certificate is the single 2b statement gated on it."""
    a, b = sub.index("**2a. Fetch and CHECK"), sub.index("**2b. Pin it")
    step2a, step2b = sub[a:b], sub[b:sub.index("**3. Verify", b)]
    g = _ps_block(step2a)
    assert g[0] == "$checkPassed = $false", "2a must reset $checkPassed first (a stale pass in the same window)"
    starts = [i for i, ln in enumerate(g) if ln.startswith("if (")]
    assert len(starts) == 1, f"2a must hold exactly one top-level if statement: {[g[i] for i in starts]}"
    stmt = g[starts[0]:]
    assert all(ln.startswith((" ", "}")) for ln in stmt[1:]), "nothing may follow the if/elseif/else statement in 2a"
    assert stmt[-1] == "}", "the if/elseif/else statement must end the 2a block"
    arms = [i for i, ln in enumerate(stmt) if ln.startswith("}")][:-1]
    assert [stmt[i].split("(")[0].strip() for i in arms][:-1] == ["} elseif"] * (len(arms) - 1) and \
        stmt[arms[-1]] == "} else {", "arms must be `} elseif (...) {` ... `} else {` on the closing-brace line"
    assert 1 + (len(arms) - 1) >= 4, "placeholders, missing file, SHA256 and SHA1 each need their own if/elseif arm"
    sets = [i for i, ln in enumerate(g) if "$checkPassed = $true" in ln]
    assert len(sets) == 1 and sets[0] > starts[0] + arms[-1], "$checkPassed may be set to $true only in the else arm"
    assert sum("CHECK PASSED" in ln for ln in g) == 1 and \
        [i for i, ln in enumerate(g) if "CHECK PASSED" in ln][0] > starts[0] + arms[-1], "CHECK PASSED only in the else arm"
    for word in ("placeholder-or-length", "Test-Path", "$fp256 -ne $want256", "$fileThumb -ne $wantThumb"):
        if word == "placeholder-or-length":
            assert "$want256.Length -ne 64 -or $wantThumb.Length -ne 40" in g[starts[0]], "first arm: unpasted values"
        else:
            assert any(word in stmt[i] for i in arms[:-1]) or word in stmt[0], f"no guard arm for {word}"
    assert not any("Import-Certificate" in ln for ln in g), "Import-Certificate must not be in the 2a guard block"
    # 2b: one statement, gated, CurrentUser only, never forced
    assert _ps_block(step2b) == [IMPORT_2B], f"2b must be exactly the single gated statement: {_ps_block(step2b)}"
    imports = [ln for ln in sub.splitlines() if "Import-Certificate" in ln and not ln.lstrip().startswith(("#", "**"))]
    code_imports = [ln for ln in imports if "-CertStoreLocation" in ln or ln.startswith("Import-Certificate")]
    assert code_imports == [IMPORT_2B], f"Import-Certificate must appear once, inside the gated 2b statement: {code_imports}"
    for ln in sub.splitlines():
        if "Import-Certificate" in ln:
            assert "LocalMachine" not in ln and "-Force" not in ln, ln
    # the dialog is compared with what the owner PASTED from the GB10, not with the downloaded file
    assert "SHA1 value YOU PASTED in 2a (`$wantThumb`" in step2b
    assert "the 2a one" not in sub
    assert "Remove-Item" in step2b


def check_runbook(text: str) -> None:
    # Its own section: section 7 must not carry `--force-recreate` (test_operator_mounts_b6.py,
    # the withdrawn single-file habit), and the proxy recreate below needs it.
    s7 = _section(text, "## 7. Phase G")
    assert "https://<gb10-lan-address>:18443" in s7 and "§8" in s7, "section 7 must point the operator-key transport at section 8"
    sub = _section(text, "## 8. GB10 console hop over TLS")
    assert text.index("## 8. GB10 console hop over TLS") > text.index("## 7. Phase G")
    for needle in (
        "https://<gb10-lan-address>:18443",
        ROOT_PATH,
        "Import-Certificate",
        r"Cert:\CurrentUser\Root",
        "Thumbprint",
        "up -d --no-deps --no-build --force-recreate proxy",
        "127.0.0.1:18080",
        "PHASE 1",
        "### Phase 2",
        "NOT IN THIS PR",
        "14:50",
        "15:05",
        "UNCONSTRAINED",
        "CHECK PASSED",
        "Remove-Item",
        "--cacert",
        "verify=",
        "REQUESTS_CA_BUNDLE",
        "ADDS the file",
        "name-constrained",
        "does NOT close design RT3-1",
    ):
        assert needle in sub, f"runbook section 8 (TLS hop) lacks {needle!r}"
    # R2-02: the two corrected tool notes must not regress
    assert "ignores `--cacert`" not in sub and "use only that file" not in sub
    check_trust_pin(sub)
    assert "RT3-1" in s7 and "D-I" in s7
    assert "OWNER" in sub or "owner" in sub
    assert "UNVERIFIED" in sub


def test_runbook_section_8_documents_the_tls_hop_and_section_7_points_to_it():
    check_runbook(_read(RUNBOOK))


def test_ci_proves_the_listener_the_root_persistence_and_that_18080_still_answers():
    ci = _read(CI)
    job = ci[ci.index("  compose-upgrade-smoke:"):]
    step = job[job.index("GB10 TLS listener"):]
    step = step[:step.index("      - name:", 10)]
    for needle in (ROOT_PATH, "--cacert", "--connect-to 192.0.2.10:18443:127.0.0.1:18443",
                   "--resolve gx10:18443:127.0.0.1", "https://localhost:18443",
                   "--force-recreate -V proxy", 'curl -sf --max-time 5 -o /dev/null "http://$LAN:18080/health"',
                   '--connect-to "192.0.2.10:18443:$LAN:18443"', 'test "$rc" -eq 60',
                   '"http://127.0.0.1:18080/ledger/events"', '"https://192.0.2.10:18443/ledger/events"',
                   'test "$code_http" = 401 && test "$code_tls" = "$code_http"'):
        assert needle in step, f"CI TLS step lacks {needle!r}"
    # PHASE 1: nothing in CI may assert (or depend on) a loopback-only 18080 yet
    assert "BASE: http://localhost:18080" in job, "compose-upgrade-smoke BASE must stay as on main in phase 1"
    assert "loopback-only" not in step and '"127.0.0.1:18080"' not in step


# --- mutants: each must turn a check RED ----------------------------------------------------------

_PORTS = 'ports: !override ["18080:8080", "18443:8443"]'

MUTANTS = {
    "18080 removed": (GB10, lambda t: t.replace(_PORTS, 'ports: !override ["18443:8443"]'), check_gb10_ports),
    "18443 not published": (GB10, lambda t: t.replace(_PORTS, 'ports: !override ["18080:8080"]'), check_gb10_ports),
    "phase-2 loopback rebind of 18080 in phase 1": (
        GB10, lambda t: t.replace(_PORTS, 'ports: !override ["127.0.0.1:18080:8080", "18443:8443"]'),
        check_gb10_ports),
    "18443 bound to loopback": (GB10, lambda t: t.replace(_PORTS, 'ports: !override ["18080:8080", "127.0.0.1:18443:8443"]'),
                                check_gb10_ports),
    "merge ports instead of override": (GB10, lambda t: t.replace(_PORTS, 'ports: ["18080:8080", "18443:8443"]'),
                                        check_gb10_ports),
    "drop the caddy_data mount": (GB10, lambda t: t.replace("      - caddy_data:/data\n", ""), check_gb10_volumes),
    "drop the caddy_data declaration": (GB10, lambda t: t.replace("\n  caddy_data:\n", "\n"), check_gb10_volumes),
    "mount caddy_data read-only": (GB10, lambda t: t.replace("- caddy_data:/data", "- caddy_data:/data:ro"),
                                   check_gb10_volumes),
    "keep the base Caddyfile only": (GB10, lambda t: t.replace("./Caddyfile.gb10:/etc/caddy/Caddyfile:ro",
                                                               "./Caddyfile:/etc/caddy/Caddyfile:ro"),
                                     check_gb10_volumes),
    "drop tls internal": (CADDY_GB10, lambda t: t.replace("\ttls internal\n", ""), check_gb10_caddyfile),
    "drop default_sni": (CADDY_GB10, lambda t: t.replace("\tdefault_sni " + LAN_IP + "\n", ""), check_gb10_caddyfile),
    "drop the route import": (CADDY_GB10, lambda t: t.replace("import /etc/caddy/Caddyfile.routes", ""),
                              check_gb10_caddyfile),
    "drop the gx10 name": (CADDY_GB10, lambda t: t.replace(" https://gx10:8443,", ""), check_gb10_caddyfile),
    "direct killswitch route inside the TLS site (reviewer R7)": (
        CADDY_GB10, lambda t: t.replace("\ttls internal\n",
                                        "\ttls internal\n\thandle_path /killswitch/* {\n\t\treverse_proxy killswitch:8005\n\t}\n"),
        check_gb10_caddyfile),
    "header rule added inside the TLS site": (
        CADDY_GB10, lambda t: t.replace("\ttls internal\n", "\ttls internal\n\theader -Strict-Transport-Security\n"),
        check_gb10_caddyfile),
    "drop disable_redirects": (CADDY_GB10, lambda t: t.replace("\tauto_https disable_redirects\n", ""),
                               check_gb10_caddyfile),
    "second site block in Caddyfile.gb10": (CADDY_GB10, lambda t: t + "\n:9090 {\n\trespond ok\n}\n",
                                            check_gb10_caddyfile),
    "base route /attest dropped (reviewer R6)": (
        CADDY_BASE, lambda t: t.replace("\thandle_path /attest/* {\n\t\treverse_proxy attest:8013\n\t}\n", ""), None),
    "Import-Certificate moved into 2a (reviewer)": (
        RUNBOOK, lambda t: t.replace("} else {\n    $checkPassed = $true\n",
                                     "} else {\n    $checkPassed = $true\n    Import-Certificate -FilePath $pem -CertStoreLocation Cert:\\CurrentUser\\Root\n", 1),
        check_runbook),
    "import into LocalMachine (reviewer)": (
        RUNBOOK, lambda t: t.replace(r"Import-Certificate -FilePath $pem -CertStoreLocation Cert:\CurrentUser\Root",
                                     r"Import-Certificate -FilePath $pem -CertStoreLocation Cert:\LocalMachine\Root"),
        check_runbook),
    "2b imports unconditionally": (
        RUNBOOK, lambda t: t.replace(IMPORT_2B, r"Import-Certificate -FilePath $pem -CertStoreLocation Cert:\CurrentUser\Root"),
        check_runbook),
    "guard split into separate throw lines (R2-01 shape)": (
        RUNBOOK, lambda t: t.replace("} elseif ($fp256 -ne $want256) {", "}\nif ($fp256 -ne $want256) {"), check_runbook),
    "$checkPassed set outside the else arm": (
        RUNBOOK, lambda t: t.replace("} catch { $crt = $null }\n", "} catch { $crt = $null }\n$checkPassed = $true\n", 1),
        check_runbook),
    "CHECK PASSED printed after the statement": (
        RUNBOOK, lambda t: t.replace("+ $wantThumb\n}\n", "+ $wantThumb\n}\n'CHECK PASSED'\n", 1), check_runbook),
    "no reset of a stale $checkPassed": (
        RUNBOOK, lambda t: t.replace("```powershell\n$checkPassed = $false\n", "```powershell\n", 1), check_runbook),
    "dialog compared with the file's own thumbprint": (
        RUNBOOK, lambda t: t.replace("SHA1 value YOU PASTED in 2a (`$wantThumb`", "SHA1 shown by the 2a one (`$fileThumb`"),
        check_runbook),
    "SHA1 arm dropped": (
        RUNBOOK, lambda t: t.replace("} elseif ($fileThumb -ne $wantThumb) {\n    throw 'FAIL: the SHA1 thumbprint differs from the GB10 value: do NOT import'\n", ""),
        check_runbook),
    "curl note regressed (R2-02)": (
        RUNBOOK, lambda t: t.replace("Windows `curl.exe` (Schannel) honours `--cacert`", "Windows `curl.exe` (Schannel) ignores `--cacert`"),
        check_runbook),
    "base route re-pointed": (CADDY_BASE, lambda t: t.replace("reverse_proxy killswitch:8005", "reverse_proxy ledger:8002"),
                              None),
    "TLS in the base Caddyfile": (CADDY_BASE, lambda t: t.replace(":8080 {", ":8080 {\n\ttls internal", 1),
                                  None),
    "console frame header weakened (C-96)": (
        CADDY_BASE, lambda t: t.replace("X-Frame-Options DENY", "X-Frame-Options SAMEORIGIN"), None),
    "console header block gains a fourth header (C-96)": (
        CADDY_BASE, lambda t: t.replace("\t\t\tX-Content-Type-Options nosniff\n",
                                        "\t\t\tX-Content-Type-Options nosniff\n\t\t\tX-Extra 1\n"), None),
    "header block on a service handle (C-96)": (
        CADDY_BASE, lambda t: t.replace("\thandle_path /ledger/* {\n",
                                        "\thandle_path /ledger/* {\n\t\theader {\n\t\t\tX-Frame-Options DENY\n"
                                        "\t\t\tContent-Security-Policy \"frame-ancestors 'none'\"\n"
                                        "\t\t\tX-Content-Type-Options nosniff\n\t\t}\n"), None),
    "publish TLS from the base compose": (BASE, lambda t: t.replace('ports: ["8080:8080"]',
                                                                    'ports: ["8080:8080", "8443:8443"]'), None),
}


def _run(path: Path, text: str, check) -> None:
    if path == CADDY_GB10:
        check(text)
    elif path == GB10:
        check(_read(BASE), text)
    elif path == BASE:
        check_base_unchanged(text, _read(CADDY_BASE))
    elif path == RUNBOOK:
        check(text)
    elif path == CADDY_BASE:
        check_base_unchanged(_read(BASE), text)


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_mutant_turns_a_check_red(name):
    path, mutate, check = MUTANTS[name]
    original = _read(path)
    mutated = mutate(original)
    assert mutated != original, f"mutant {name!r} did not apply (the file changed shape): update the mutant"
    with pytest.raises(AssertionError):
        _run(path, mutated, check)


# --- C-267: the LAN address is the estate's variable, never a literal in the repository ------------

_LAN_VAR_REQUIRED = "FIELD_GB10_LAN_IP: ${FIELD_GB10_LAN_IP:?"


def check_lan_address_is_required_and_not_literal(gb10_compose: str, caddyfile: str) -> None:
    assert _LAN_VAR_REQUIRED in gb10_compose, "the GB10 proxy must require FIELD_GB10_LAN_IP (`${VAR:?message}`)"
    assert "{$FIELD_GB10_LAN_IP}" in caddyfile, "the Caddyfile must read the LAN address from FIELD_GB10_LAN_IP"
    import re as _re
    literal = _re.search(r"(?<![\w.])(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(?![\w.])", caddyfile)
    assert not literal, "no private address literal in the Caddyfile"


def test_the_lan_address_is_required_and_the_caddyfile_holds_no_literal():
    check_lan_address_is_required_and_not_literal(_read(GB10), _read(CADDY_GB10))


@pytest.mark.parametrize("mutant", ["optional", "dropped", "literal"])
def test_lan_address_mutants_turn_the_check_red(mutant):
    compose, caddy = _read(GB10), _read(CADDY_GB10)
    if mutant == "optional":
        compose = compose.replace("${FIELD_GB10_LAN_IP:?", "${FIELD_GB10_LAN_IP:-")
    elif mutant == "dropped":
        compose = compose.replace("FIELD_GB10_LAN_IP: ${", "FIELD_GB10_UNUSED: ${")
    else:
        caddy = caddy.replace("{$FIELD_GB10_LAN_IP}", "10.1.2.3", 1)
    with pytest.raises(AssertionError):
        check_lan_address_is_required_and_not_literal(compose, caddy)
