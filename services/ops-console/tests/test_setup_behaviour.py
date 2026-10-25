"""Behavioural tests for the Setup area: the real console.html runs in jsdom against a stub estate
(setup_harness.mjs). Each scenario has a ``check`` that returns a list of problems; the same check is
run against the shipped page (must be clean) and against a mutant of the page (must report a problem),
so a test that cannot fail is caught here.

Needs node + npm (jsdom is installed once into a cache dir). Skipped when unavailable, but a failure
when CI=true so the gate cannot silently vanish.
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

HTML_PATH = Path(os.environ.get("FIELD_TEST_HTML") or Path(ops_console.__file__).parent / "static" / "console.html")
HARNESS = Path(__file__).parent / "setup_harness.mjs"
JSDOM_VERSION = "24.1.3"


@pytest.fixture(scope="session")
def jsdom_dir() -> Path:
    def unavailable(why: str):
        if os.environ.get("CI", "").lower() in {"1", "true"}:
            pytest.fail(why)
        pytest.skip(why)

    node, npm = shutil.which("node"), shutil.which("npm")
    if not node:
        unavailable("node is not installed")
    d = Path(os.environ.get("FIELD_TEST_JSDOM_DIR") or Path(tempfile.gettempdir()) / f"field-jsdom-{JSDOM_VERSION}")
    if not (d / "node_modules" / "jsdom").is_dir():
        if not npm:
            unavailable("npm is not installed")
        d.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--prefix", str(d), f"jsdom@{JSDOM_VERSION}"],
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            unavailable("could not install jsdom: " + p.stderr[-300:])
    return d


def run(jsdom_dir: Path, scenario: str, html: Path = HTML_PATH) -> dict:
    p = subprocess.run(["node", str(HARNESS), str(jsdom_dir), str(html), scenario],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads(p.stdout.strip().splitlines()[-1])


# ---- checks: return a list of problems (empty = the behaviour holds) ----------------------------

def c_double(key, want):
    return lambda r: [] if r[key] == want else [f"{key}={r[key]} want {want}"]


def c_double_mint(r):
    p = []
    if r["mints"] != 1:
        p.append(f"{r['mints']} mint requests for rapid clicks")
    if not r["disabledInFlight"]:
        p.append("button not disabled in flight")
    if r["disabledAfter"]:
        p.append("button stays disabled")
    if "Token minted" not in r["result"]:
        p.append("first response not shown")
    return p


def c_double_register(r):
    return ([] if r["posts"] == 1 else ["more than one POST"]) + ([] if r["cls"] == "sres ok" and "Registered" in r["result"] else ["first response not shown"])


def c_shadow(r):
    p = []
    if "ok" in r["cls"].split():
        p.append("shadowed verdict shown green")
    if "warn" not in r["cls"].split() or "WOULD have been BLOCK" not in r["text"] or "D.scope" not in r["text"]:
        p.append("no amber would-be message")
    return p


def c_findings_witness(r):
    p = []
    if "ok" in r["cls"].split():
        p.append("green with non-null findings")
    if "witness: stale" not in r["text"] or "retention_policy: violation" not in r["text"]:
        p.append("findings not listed")
    return p


def c_read_headers(r):
    p = []
    if r["readWithOp"]:
        p.append("operator headers on reads: " + ",".join(r["readWithOp"]))
    if r["sentinelPostWithOp"]:
        p.append("operator headers on the unguarded sentinel POST")
    if not (r["guardedWithOp"] and r["revokeWithOp"]):
        p.append("guarded writes lost their operator headers")
    return p


def c_proto(r):
    p = [f"error: {e}" for e in r["errors"]]
    for h in r["out"]:
        if not (h["setupShown"] and h["overviewShown"] and h["blank"] == 1):
            p.append(f"{h['hash']} -> {h}")
    if len(r["out"]) != 5:
        p.append("not all hashes tried")
    return p


def c_xss(r):
    p = []
    if r["nodes"]:
        p.append(f"{r['nodes']} element(s) created from API strings")
    if r["pwn"] is not None:
        p.append("payload executed")
    if not r["shownText"]:
        p.append("payload not shown as plain text")
    return p


def c_no_autosubmit(r):
    return [f"POSTs without a click: {r['posts']}"] if r["posts"] else []


def c_key_leak(r):
    p = [k for k in ("inDom", "inValues", "inText", "inUrls", "inBodies") if r[k]]
    if not r["stored"]:
        p.append("key not in sessionStorage (harness sanity)")
    return p


def c_scrub(r):
    t = r["text"]
    p = [x for x in ("ledger.internal", "flycast", "svc.internal", "http://") if x in t]
    if "withheld" not in t:
        p.append("nothing scrubbed")
    return p


def c_register_failures(r):
    p = []
    for st, v in r.items():
        if "ok" in v["cls"].split() or "Registered" in v["text"]:
            p.append(f"{st} shown as success")
    return p


def c_revoke(r):
    return ([] if r["declined"] == 0 else ["revoke sent although confirm was declined"]) + ([] if r["accepted"] == 1 and r["btnEnabled"] else ["accepted revoke not sent once"])


def c_period(r):
    return [] if r["lower"] == 0 and "bad" in r["cls"].split() else ["lower-case period accepted"]


def c_404(r):
    p = []
    if "expected" in r["absent"].lower():
        p.append("absent route called expected")
    if "expected before the first sweep" not in r["sweepless"]:
        p.append("real no-sweep 404 lost its message")
    return p


def c_scope(r):
    return [] if r["preview"].startswith("Will send 4 scopes") and '"a b"' in r["preview"] else [f"preview: {r['preview']}"]


def c_focus(r):
    return [] if r["tag"] == "H2" and r["inMint"] else [f"focus on {r['tag']}"]


# scenario -> (check, mutation (old, new) or None for scenarios guarded by another mutant)
CASES = {
    "double_mint": (c_double_mint, ("if (LOCK[form.id]) return;", "if (false) return;")),
    "double_register": (c_double_register, ("if (LOCK[form.id]) return;", "if (false) return;")),
    "double_revoke": (c_double("revokes", 1), ("if (LOCK[form.id]) return;", "if (false) return;")),
    "double_check": (c_double("checks", 1), ("if (LOCK[form.id]) return;", "if (false) return;")),
    "shadow_allow": (c_shadow, ("if (cx.shadowed === true || wb) {", "if (false) {")),
    "findings_witness": (c_findings_witness, (" + n(f.reattestation_due) + extra.length;", " + n(f.reattestation_due);")),
    "read_headers": (c_read_headers, ("if (!withOp) for", "if (false) for")),
    "proto_routes": (c_proto, ("const BY_SLUG = Object.create(null);", "const BY_SLUG = {};")),
    "xss": (c_xss, ("e.textContent = String(text);", 'e["inner" + "HTML"] = String(text);')),
    "no_autosubmit": (c_no_autosubmit, ('"register-agent": () => { loadAgentChoices(); },', '"register-agent": () => { loadAgentChoices(); g("su-register").requestSubmit(); },')),
    "key_leak": (c_key_leak, ('"Signed in as operator " + OPID + ". "', '"Signed in as operator " + OPID + " key " + OPKEY + ". "')),
    "scrub": (c_scrub, ('.replace(/https?:\\/\\/\\S+/gi, "[address withheld]")', '.replace(/https?:\\/\\/\\S+/gi, "$&")')),
    "register_failures": (c_register_failures, ("    } else failure(out, r);\n  }\n\n  // ---- step 2: mint / revoke ----", '    } else result(out, "ok", "Registered " + body.agent_id, null);\n  }\n\n  // ---- step 2: mint / revoke ----')),
    "revoke_confirm": (c_revoke, ('if (!confirm("Revoke token "', 'if (false && !confirm("Revoke token "')),
    "period_case": (c_period, ("Q[1-4] \\d{4})$/.test(period)", "Q[1-4] \\d{4})$/i.test(period)")),
    "findings_404": (c_404, ('if (d && typeof d === "object" && typeof d.message === "string" && /no sweep recorded/i.test(d.message)) {', "if (true) {")),
    "scope_preview": (c_scope, ('g("su-mint-scope").addEventListener("input", previewScopes);', "")),
    "focus_heading": (c_focus, ("hd.tabIndex = -1; hd.focus();", "hd.tabIndex = -1;")),
}


@pytest.mark.parametrize("scenario", sorted(CASES))
def test_behaviour_holds_on_the_shipped_page(jsdom_dir, scenario):
    check, _ = CASES[scenario]
    assert check(run(jsdom_dir, scenario)) == []


@pytest.mark.parametrize("scenario", sorted(CASES))
def test_each_check_fails_against_its_own_mutant(jsdom_dir, scenario, tmp_path):
    check, (old, new) = CASES[scenario]
    src = HTML_PATH.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"mutation anchor not found exactly once: {old!r}"
    mutant = tmp_path / "mutant.html"
    mutant.write_text(src.replace(old, new), encoding="utf-8")
    assert check(run(jsdom_dir, scenario, mutant)) != [], "the mutant survived: the test cannot fail"


def test_plain_allow_is_green_and_clean_findings_are_green(jsdom_dir):
    # guards against the shadow / findings fixes turning everything amber
    assert run(jsdom_dir, "plain_allow")["cls"] == "sres ok"
    assert run(jsdom_dir, "findings_clean")["cls"] == "sres ok"
