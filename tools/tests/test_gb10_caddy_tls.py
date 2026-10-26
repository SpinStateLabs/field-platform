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
exported root for 10.0.0.62 with no SNI / gx10 / localhost, the root survives a
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

LAN_IP = "10.0.0.62"
TLS_NAMES = ("https://10.0.0.62:8443", "https://gx10:8443", "https://localhost:8443")
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
    assert ("import " + ROUTES_TARGET, "") in blocks, "the GB10 file must import the unchanged base route map"
    sites = [(h, b) for h, b in blocks if h.startswith("https://")]
    assert len(sites) == 1, f"exactly one TLS site expected: {[h for h, _ in sites]}"
    header, body = sites[0]
    names = tuple(n.strip() for n in header.split(","))
    assert names == TLS_NAMES, f"TLS site names: {names}"
    lines = body.splitlines()
    assert "tls internal" in lines, "the TLS site must use Caddy's internal CA"
    assert "reverse_proxy 127.0.0.1:8080" in lines, "the TLS site must hand off to the :8080 route map"
    assert not any(h.startswith("http://") or h.startswith(":18080") for h, _ in blocks)


# --- the real files ------------------------------------------------------------------------------


def test_base_compose_and_base_caddyfile_are_unchanged_plain_http_8080():
    check_base_unchanged(_read(BASE), _read(CADDY_BASE))


def test_gb10_publishes_loopback_18080_and_18443_only():
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


def test_runbook_section_8_documents_the_tls_hop_and_section_7_points_to_it():
    # Its own section: section 7 must not carry `--force-recreate` (test_operator_mounts_b6.py,
    # the withdrawn single-file habit), and the proxy recreate below needs it.
    text = _read(RUNBOOK)
    s7 = _section(text, "## 7. Phase G")
    assert "https://10.0.0.62:18443" in s7 and "§8" in s7, "section 7 must point the operator-key transport at section 8"
    sub = _section(text, "## 8. GB10 console hop over TLS")
    assert text.index("## 8. GB10 console hop over TLS") > text.index("## 7. Phase G")
    for needle in (
        "https://10.0.0.62:18443",
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
    ):
        assert needle in sub, f"runbook section 8 (TLS hop) lacks {needle!r}"
    assert "OWNER" in sub or "owner" in sub
    assert "UNVERIFIED" in sub


def test_ci_proves_the_listener_the_root_persistence_and_that_18080_still_answers():
    ci = _read(CI)
    job = ci[ci.index("  compose-upgrade-smoke:"):]
    step = job[job.index("GB10 TLS listener"):]
    step = step[:step.index("      - name:", 10)]
    for needle in (ROOT_PATH, "--cacert", "--connect-to 10.0.0.62:18443:127.0.0.1:18443",
                   "--resolve gx10:18443:127.0.0.1", "https://localhost:18443",
                   "--force-recreate -V proxy", 'curl -sf --max-time 5 -o /dev/null "http://$LAN:18080/health"',
                   '--connect-to "10.0.0.62:18443:$LAN:18443"'):
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
    "drop default_sni": (CADDY_GB10, lambda t: t.replace("\tdefault_sni 10.0.0.62\n", ""), check_gb10_caddyfile),
    "drop the route import": (CADDY_GB10, lambda t: t.replace("import /etc/caddy/Caddyfile.routes", ""),
                              check_gb10_caddyfile),
    "drop the gx10 name": (CADDY_GB10, lambda t: t.replace(" https://gx10:8443,", ""), check_gb10_caddyfile),
    "TLS in the base Caddyfile": (CADDY_BASE, lambda t: t.replace(":8080 {", ":8080 {\n\ttls internal", 1),
                                  None),
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
