"""P35: the machine verifier identity svc-verifier-<estate> replaces Don's key in every verification step.

Owner rule (2026-10-27): verification must not need a human in the loop and must
run in CI. Stage 1's positive controls (b)/(c), the window's estate_probe
catalogue and drill, and the Setup-page click-through all used Don's personal
key. This module proves, on the REAL services over real HTTP (estate_harness.py
via test_estate_probe.Estate) with the GB10's ledger configuration
(caller_signed=True: caller signatures required, fake keys) and the DOA roster
armed (generated from the shipped manifests by tools/generate_doa_roster.py, as
the estates' roster is), that the verifier row

    {"operator_id": "svc-verifier-gb10",
     "scopes": ["kill", "revive", "drill", "attest", "mint", "revoke"],
     "names": ["FIELD canary (gate verification)"]}

(no bypass_operator_list, no mint_for_others, no registry_edit, no
ledger_attribute) can, under ENFORCE:

* kill / revive / drill / attest canary-gb10, attributed to itself (C-12 pairing);
* mint a canary token with granted_by its alias and revoke it;
* pass phase_g_check (log-only and enforce) and estate_probe catalogue;

and is REFUSED (403, the one identical body) on any other agent (kill, revive, drill, attest, mint and,
review F1, revoke of another agent's token): an SSL agent
whose manifest lists only Don, and a self-agent whose list is EMPTY (the
list-bound rule, field_core.operator_auth.list_bound); refused minting for a
non-canary agent or under any granted_by other than its alias (or its own id,
which no roster row names); and cannot edit or register a registry record.

The mutants at the end show the tests can fail: the verifier row given
bypass_operator_list, the canary manifest without the alias, and the same row
under an id without the svc-verifier- prefix each turn a test RED.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).parent))

import estate_probe  # noqa: E402
import generate_doa_roster  # noqa: E402
import phase_g_check  # noqa: E402
from test_estate_probe import CANARY, SECRET, Estate, _http  # noqa: E402
from test_phase_g_check import _arm, _row, events  # noqa: E402
from test_phase_g_check_caller_signed import assert_caller_signed  # noqa: E402

@pytest.fixture(autouse=True, scope="module")
def _settle_window():
    """This module's settle window, set for its tests only. A bare module-level assignment is shared by every
    module of the run and the last one imported wins, so the saving (or the margin) held only when the file ran
    alone (C-340, reviewer C-335 F-C335-1)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(phase_g_check, "SETTLE_S", 3.0)
        yield

ALIAS = "FIELD canary (gate verification)"
VERIFIER = "svc-verifier-gb10"
VERIFIER_SCOPES = ["kill", "revive", "drill", "attest", "mint", "revoke"]
DON = "Don Hagell, Spin State Labs"
DON_SCOPES = ["*", "mint_for_others"]               # C-805: the human row holds "*" (an explicit verifier-sized scope set under a non-verifier id is refused at load)
SSL_AGENT = "ssl-invoicing-agent"         # authorized_operators: [Don]
EMPTY_AGENT = "conformance-sentinel"      # authorized_operators: []
KEY_VER = "fok_verifier-e2e-key-NEVER-PRINT_0123456789abcdef"
KEY_DON = "fok_don-e2e-key-NEVER-PRINT_fedcba9876543210ffff"
KEY_SVC = "fok_svc-e2e-key-NEVER-PRINT_aaaaaaaaaaaaaaaaaaaa"
FP_VER = hashlib.sha256(KEY_VER.encode()).hexdigest()[:8]
FORBIDDEN = {"detail": "operator not authorised"}
BODY = {"operator": "P35 machine verifier (test)", "reason": "machine verifier test - canary only"}
CANARY_SCOPE = yaml.safe_load((REPO / "manifests" / "canary-gb10.yaml").read_text(encoding="utf-8"))[
    "delegation"]["scope"]
SSL_SCOPE = yaml.safe_load((REPO / "manifests" / f"{SSL_AGENT}.yaml").read_text(encoding="utf-8"))[
    "delegation"]["scope"]


def verifier_row(oid: str = VERIFIER, extra_scopes: tuple[str, ...] = ()) -> dict:
    return _row(oid, KEY_VER, VERIFIER_SCOPES + list(extra_scopes), [ALIAS])


def _ops(verifier: dict) -> list[dict]:
    return [
        _row("don", KEY_DON, DON_SCOPES, ["Don Hagell", DON]),
        _row("svc", KEY_SVC, ["*", "bypass_operator_list", "ledger_attribute"],
             event_prefixes=["kill.", "registry.", "debug."]),
        verifier,
    ]


def _roster(tmp: Path) -> Path:
    """The estates' roster is generated from the registry and the manifests (plan B1 / J9):
    the canary's identity.principal is a grantor row with exactly the canary's scopes."""
    records = [{"agent_id": a, "status": "active", "manifest_ref": f"/data/manifests/{a}.yaml"}
               for a in (CANARY, SSL_AGENT, EMPTY_AGENT)]
    roster, _ = generate_doa_roster.build_roster(records, REPO / "manifests", 30, False)
    out = tmp / "doa-roster.yaml"
    generate_doa_roster.write_roster(roster, out, "# generated for test_machine_verifier_identity.py\n")
    rows = {g["grantor"]: g for g in yaml.safe_load(out.read_text(encoding="utf-8"))["grantors"]}
    assert rows[ALIAS]["allowed_scope"] == CANARY_SCOPE, rows[ALIAS]
    assert VERIFIER not in rows
    return out


@pytest.fixture(scope="module")
def vest(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("p35_verifier")
    roster = _roster(tmp)
    names = ("FIELD_OPERATOR", "FIELD_OPERATOR_KEY", "FIELD_DOA_ROSTER")
    saved = {k: os.environ.get(k) for k in names}
    os.environ.update(FIELD_OPERATOR="svc", FIELD_OPERATOR_KEY=KEY_SVC, FIELD_DOA_ROSTER=str(roster))
    try:
        e = Estate(tmp, secret=True, caller_signed=True)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    try:
        mdir = e.manifest.parent
        e.refs = {CANARY: str(e.manifest)}
        for agent, domain in ((SSL_AGENT, "finance"), (EMPTY_AGENT, "platform")):
            shutil.copy(REPO / "manifests" / f"{agent}.yaml", mdir / f"{agent}.yaml")
            e.refs[agent] = str(mdir / f"{agent}.yaml")
            status, _ = _http("POST", f"{e.base}/registry/agents",
                              {"agent_id": agent, "name": agent, "owner": DON, "domain": domain,
                               "manifest_ref": e.refs[agent]}, SECRET)
            assert status == 201, (agent, status)
        e.ops_file = tmp / "operators.json"
        e.write_ops = lambda verifier=None: _write_ops(e, verifier or verifier_row())
        e.write_ops()
        e.secret_file = tmp / "perimeter.secret"
        e.secret_file.write_text(SECRET + "\n")
        e.ver_key_file = tmp / "svc-verifier-gb10.key"
        e.ver_key_file.write_text(KEY_VER + "\n")
        yield e
    finally:
        _arm(e, "off")
        e.close()


def _write_ops(e: Estate, verifier: dict) -> None:
    e.ops_file.write_text(json.dumps(_ops(verifier)), encoding="utf-8")


def _revive_if_killed(e: Estate, agent: str) -> None:
    status, hb = _http("GET", f"{e.base}/killswitch/heartbeat/{agent}", None, SECRET)
    if isinstance(hb, dict) and hb.get("killed"):
        status, _ = _http("POST", f"{e.base}/killswitch/revive/{agent}",
                          {"operator": "test reset", "reason": "reset"}, SECRET)
        assert status == 200


@pytest.fixture
def ve(vest):
    _arm(vest, "off")
    vest.write_ops()
    vest.reset()
    for agent in (SSL_AGENT, EMPTY_AGENT):
        _revive_if_killed(vest, agent)
    yield vest
    _arm(vest, "off")
    vest.write_ops()
    for agent in (SSL_AGENT, EMPTY_AGENT):
        _revive_if_killed(vest, agent)


# --- plumbing -----------------------------------------------------------------------------------


def call(e: Estate, method: str, path: str, body=None, op: str | None = VERIFIER, key: str = KEY_VER):
    headers = {"Content-Type": "application/json", "x-field-auth": SECRET}
    if op is not None:
        headers.update({"x-field-operator": op, "x-field-operator-key": key})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{e.base}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    return status, (json.loads(raw) if raw else None)


def record(e: Estate, agent: str) -> dict:
    status, rec = _http("GET", f"{e.base}/registry/agents/{agent}", None, SECRET)
    assert status == 200
    return rec


def tokens_of(e: Estate, agent: str) -> list[dict]:
    status, toks = _http("GET", f"{e.base}/delegation/tokens?agent_id={agent}", None, SECRET)
    assert status == 200
    return toks


def bump(path: Path) -> None:
    """Force a fresh mtime (the manifest resolver caches by mtime)."""
    t = time.time() + 5 + (time.time_ns() % 1000) / 10
    os.utime(path, (t, t))


def assert_secret_free(out: str) -> None:
    for s in (KEY_VER, KEY_DON, KEY_SVC, SECRET, hashlib.sha256(KEY_VER.encode()).hexdigest(), FP_VER):
        assert s not in out, "a secret reached the tool output"


def run_tool(main, argv: list[str]) -> tuple[int, str]:
    estate_probe.RESULTS.clear()
    out = io.StringIO()
    saved = sys.stdout, sys.stderr
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    sys.stdout, sys.stderr = saved   # the tools wrap them in a redactor
    return code, out.getvalue()


# --- the checks (each one is also run against a mutant below) -----------------------------------


def verifier_acts_on_canary(e: Estate) -> None:
    """kill, revive, drill and attest of the canary as the verifier: 200 each, attributed to it."""
    k0 = len(events(e, event_type="kill.agent", agent_id=CANARY))
    c0 = len(events(e, event_type="registry.status_changed", agent_id=CANARY))
    s, rep = call(e, "POST", f"/killswitch/kill/{CANARY}", BODY)
    assert s == 200 and rep.get("status") == "killed" and rep.get("operator") == VERIFIER, (s, rep)
    [kill] = events(e, event_type="kill.agent", agent_id=CANARY)[k0:]
    assert kill["payload"]["operator_id_authenticated"] == VERIFIER
    assert kill["payload"]["operator_key_fp"] == FP_VER
    assert_caller_signed(e, kill)
    s, hb = call(e, "POST", f"/killswitch/revive/{CANARY}", BODY)
    assert s == 200 and hb.get("killed") is False, (s, hb)
    s, drill = call(e, "POST", f"/killswitch/drill/{CANARY}", BODY)
    assert s == 200 and drill.get("restored") is True and drill.get("restored_status") == "active", (s, drill)
    s, rec = call(e, "POST", f"/registry/agents/{CANARY}/attest", {"attested_by": "FIELD gate verification"})
    assert s == 200 and rec.get("attested_at"), (s, rec)
    # C-12: every status change of the canary is the kill-switch acting on behalf of the verifier
    changes = events(e, event_type="registry.status_changed", agent_id=CANARY)[c0:]
    assert len(changes) == 4, [c["payload"].get("to") for c in changes]
    for c in changes:
        assert c["payload"].get("operator_id_authenticated") == "svc"
        assert c["payload"].get("operator_on_behalf_of") == VERIFIER


GUARDED = (("POST", "/killswitch/kill/{a}", BODY), ("POST", "/killswitch/revive/{a}", BODY),
           ("POST", "/killswitch/drill/{a}", BODY),
           ("POST", "/registry/agents/{a}/attest", {"attested_by": "FIELD gate verification"}))


def verifier_refused_on(e: Estate, agent: str) -> None:
    """kill, revive, drill and attest of a non-canary agent: 403 with the one body, nothing changed."""
    before = record(e, agent)
    n0 = len(events(e, agent_id=agent))
    for method, path, body in GUARDED:
        s, b = call(e, method, path.format(a=agent), body)
        assert s == 403 and b == FORBIDDEN, (path.format(a=agent), s, b)
    after = record(e, agent)
    assert after["status"] == before["status"] == "active"
    assert after.get("attested_at") == before.get("attested_at")
    new = [ev["event_type"] for ev in events(e, agent_id=agent)[n0:]]
    assert not [t for t in new if t.startswith("kill.") or t.startswith("registry.")], new


# --- the row and the manifests ----------------------------------------------------------------


def test_only_the_canary_manifests_name_the_verifier_alias_and_both_keep_don():
    for name in ("canary-gb10", "canary-fly"):
        m = yaml.safe_load((REPO / "manifests" / f"{name}.yaml").read_text(encoding="utf-8"))
        assert m["enforcement"]["kill_switch"]["authorized_operators"] == [DON, ALIAS], name
        assert m["identity"]["principal"] == ALIAS, name
    for path in sorted((REPO / "manifests").glob("*.yaml")):
        if path.stem in ("canary-gb10", "canary-fly"):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        listed = (((doc or {}).get("enforcement") or {}).get("kill_switch") or {}).get("authorized_operators")
        assert ALIAS not in (listed or []), path.name
        assert VERIFIER not in (listed or []), path.name


def test_phase_g_check_probes_every_canary_manifest_name_as_a_login_id_by_default():
    """The verifier's alias is a display name like Don's: phase_g_check's default alias probes cover it."""
    for name in ("canary-gb10", "canary-fly"):
        m = yaml.safe_load((REPO / "manifests" / f"{name}.yaml").read_text(encoding="utf-8"))
        assert set(m["enforcement"]["kill_switch"]["authorized_operators"]) <= set(phase_g_check.DEFAULT_ALIASES)


def test_the_verifier_row_is_valid_and_narrow(vest):
    from field_core.operator_auth import EXPLICIT_ONLY, parse_registry

    rows = parse_registry(json.loads(vest.ops_file.read_text(encoding="utf-8")), require_active=True)
    [row] = [r for r in rows if r["operator_id"] == VERIFIER]
    assert sorted(row["scopes"]) == sorted(VERIFIER_SCOPES) and list(row["names"]) == [ALIAS]
    assert not set(row["scopes"]) & (EXPLICIT_ONLY | {"registry_edit", "*"})


# --- ENFORCE: the canary, yes -----------------------------------------------------------------


def test_enforce_the_verifier_kills_revives_drills_and_attests_the_canary(ve):
    _arm(ve, "enforce")
    verifier_acts_on_canary(ve)


def test_enforce_the_verifier_mints_a_canary_token_as_its_alias_and_revokes_it(ve):
    _arm(ve, "enforce")
    m0 = len(events(ve, event_type="delegation.mint", agent_id=CANARY))
    s, tok = call(ve, "POST", "/delegation/tokens",
                  {"agent_id": CANARY, "granted_by": ALIAS, "scope": CANARY_SCOPE, "ttl_seconds": 86400})
    assert s == 201 and tok["granted_by"] == ALIAS and tok["scope"] == CANARY_SCOPE, (s, tok)
    [mint] = events(ve, event_type="delegation.mint", agent_id=CANARY)[m0:]
    assert mint["payload"]["token_id"] == tok["token_id"]
    assert mint["payload"]["doa_checked"] is True and mint["payload"]["doa_row"]["grantor"] == ALIAS
    s, rev = call(ve, "POST", f"/delegation/tokens/{tok['token_id']}/revoke")
    assert s == 200 and rev["revoked"] is True, (s, rev)
    s, intro = _http("POST", f"{ve.base}/delegation/introspect", {"token_id": tok["token_id"]}, SECRET)
    assert s == 200 and intro["active"] is False


# --- ENFORCE: everything else, no ---------------------------------------------------------------


@pytest.mark.parametrize("agent", [SSL_AGENT, EMPTY_AGENT])
def test_enforce_the_verifier_is_refused_on_every_non_canary_agent(ve, agent):
    _arm(ve, "enforce")
    verifier_refused_on(ve, agent)
    # control: Don (listed by alias) is let through on the SSL agent's list check
    if agent == SSL_AGENT:
        s, rec = call(ve, "POST", f"/registry/agents/{agent}/attest", {"attested_by": "Don Hagell"},
                      op="don", key=KEY_DON)
        assert s == 200, (s, rec)


def test_enforce_the_verifier_domain_kill_reaches_no_other_agent(ve):
    """A domain halt is per-agent through the same list check: every attempt on the platform domain errors."""
    _arm(ve, "enforce")
    s, body = call(ve, "POST", "/killswitch/kill/domain/platform", BODY)
    assert s == 502, (s, body)
    assert record(ve, EMPTY_AGENT)["status"] == "active"


@pytest.mark.parametrize("agent,granted_by,scope,want", [
    (SSL_AGENT, ALIAS, SSL_SCOPE, "forbidden"),               # its alias, but the agent does not list it
    (EMPTY_AGENT, ALIAS, ["read agent manifests"], "forbidden"),
    (CANARY, DON, CANARY_SCOPE, "forbidden"),                 # not its alias, no mint_for_others
    (CANARY, "FIELD canary", CANARY_SCOPE, "forbidden"),      # a near miss of its alias
    (CANARY, VERIFIER, CANARY_SCOPE, "D.grantor"),            # its own id: no roster row names it
    (SSL_AGENT, VERIFIER, SSL_SCOPE, "D.grantor"),
])
def test_enforce_the_verifier_is_refused_minting_outside_the_canary_alias_grant(ve, agent, granted_by, scope, want):
    _arm(ve, "enforce")
    t0 = len(tokens_of(ve, agent))
    m0 = len(events(ve, event_type="delegation.mint"))
    s, body = call(ve, "POST", "/delegation/tokens",
                   {"agent_id": agent, "granted_by": granted_by, "scope": scope, "ttl_seconds": 86400})
    assert s == 403, (s, body)
    if want == "forbidden":
        assert body == FORBIDDEN, body
    else:
        assert body["detail"]["clause_id"] == want, body
    assert len(tokens_of(ve, agent)) == t0
    assert len(events(ve, event_type="delegation.mint")) == m0


def test_enforce_the_verifier_cannot_revoke_a_non_canary_token(ve):
    """Review F1: the verifier lists every token behind the perimeter secret; under ENFORCE it revokes only
    the tokens of an agent whose manifest names it. A Don-minted SSL token: 403, still active; Don revokes it."""
    _arm(ve, "enforce")
    s, tok = call(ve, "POST", "/delegation/tokens",
                  {"agent_id": SSL_AGENT, "granted_by": DON, "scope": SSL_SCOPE, "ttl_seconds": 86400},
                  op="don", key=KEY_DON)
    assert s == 201, (s, tok)
    r0 = len(events(ve, event_type="delegation.revoke", agent_id=SSL_AGENT))
    s, body = call(ve, "POST", f"/delegation/tokens/{tok['token_id']}/revoke")
    assert s == 403 and body == FORBIDDEN, (s, body)
    s, intro = _http("POST", f"{ve.base}/delegation/introspect", {"token_id": tok["token_id"]}, SECRET)
    assert s == 200 and intro["active"] is True
    assert len(events(ve, event_type="delegation.revoke", agent_id=SSL_AGENT)) == r0
    s, rev = call(ve, "POST", f"/delegation/tokens/{tok['token_id']}/revoke", op="don", key=KEY_DON)
    assert s == 200 and rev["revoked"] is True, (s, rev)


def test_enforce_the_verifier_cannot_edit_or_register_registry_records(ve):
    _arm(ve, "enforce")
    before = record(ve, CANARY)
    for patch in ({"owner": "someone else"}, {"manifest_ref": ve.refs[SSL_AGENT]}, {"domain": "finance"}):
        s, b = call(ve, "PATCH", f"/registry/agents/{CANARY}", patch)
        assert s == 403 and b == FORBIDDEN, (patch, s, b)
    s, b = call(ve, "PATCH", f"/registry/agents/{SSL_AGENT}", {"status": "killed"})
    assert s == 403 and b == FORBIDDEN, (s, b)
    s, b = call(ve, "POST", "/registry/agents",
                {"agent_id": "verifier-made-this", "name": "x", "owner": ALIAS, "domain": "canary"})
    assert s == 403 and b == FORBIDDEN, (s, b)
    after = record(ve, CANARY)
    for k in ("owner", "manifest_ref", "domain", "status"):
        assert after[k] == before[k], k
    assert record(ve, SSL_AGENT)["status"] == "active"


# --- the tools, as the controller and CI run them ---------------------------------------------------


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_phase_g_check_passes_as_the_verifier_on_the_caller_signed_estate(ve, mode):
    _arm(ve, mode)
    k0 = len(events(ve, event_type="kill.agent", agent_id=CANARY))
    c0 = len(events(ve, event_type="registry.status_changed", agent_id=CANARY))
    code, out = run_tool(phase_g_check.main, [
        "--base", ve.base, "--secret-file", str(ve.secret_file), "--expect-mode", mode, "--agent", CANARY,
        "--operator-id", VERIFIER, "--key-file", str(ve.ver_key_file)])
    assert code == 0, out
    assert f"inferred mode: {mode}" in out
    [kill] = events(ve, event_type="kill.agent", agent_id=CANARY)[k0:]
    assert kill["payload"]["operator_id_authenticated"] == VERIFIER == kill["payload"]["operator_claimed"]
    assert kill["payload"]["operator_key_fp"] == FP_VER
    assert_caller_signed(ve, kill)
    ours = [c for c in events(ve, event_type="registry.status_changed", agent_id=CANARY)[c0:]
            if c["payload"].get("operator_on_behalf_of") == VERIFIER]
    assert len(ours) == 2, "C-12: the positive path's kill and revive pair with the verifier"
    assert_secret_free(out)


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_estate_probe_catalogue_and_revoke_as_the_verifier_with_its_own_canary_token(ve, mode):
    """The s1-ctl-verifier.sh sequence: the verifier mints (alias grant), runs the catalogue with its
    key (RT1-3 pairs every status change with its kill.* events) and revokes."""
    _arm(ve, mode)
    s, tok = call(ve, "POST", "/delegation/tokens",
                  {"agent_id": CANARY, "granted_by": ALIAS, "scope": ["canary.probe"], "ttl_seconds": 86400})
    assert s == 201, (s, tok)
    op = ["--base", ve.base, "--secret-file", str(ve.secret_file), "--operator-id", VERIFIER,
          "--operator-key-file", str(ve.ver_key_file)]
    try:
        code, out = run_tool(estate_probe.main, op + ["catalogue", "--agent", CANARY, "--token", tok["token_id"],
                                                      "--expect-endpoint", "skipped"])
        assert code == 0, out
        assert "RT1-3" in out and "[FAIL]" not in out
        assert_secret_free(out)
    finally:
        code, out = run_tool(estate_probe.main, op + ["revoke", "--agent", CANARY, "--token", tok["token_id"]])
    assert code == 0, out
    attested = events(ve, event_type="registry.attested", agent_id=CANARY)
    assert attested[-1]["payload"].get("operator_id_authenticated") == VERIFIER, attested[-1]["payload"]


# --- mutants: each turns a test above RED ---------------------------------------------------------


def test_mutant_verifier_with_bypass_operator_list_reaches_non_canary_agents(ve):
    ve.write_ops(verifier_row(extra_scopes=("bypass_operator_list",)))
    _arm(ve, "enforce")
    with pytest.raises(AssertionError):
        verifier_refused_on(ve, SSL_AGENT)


def test_mutant_verifier_id_without_the_prefix_reaches_an_empty_list_agent(ve):
    ve.write_ops(verifier_row(oid="verifier-gb10"))
    _arm(ve, "enforce")
    with pytest.raises(AssertionError):
        _refused_as(ve, "verifier-gb10", EMPTY_AGENT)


def _refused_as(e: Estate, oid: str, agent: str) -> None:
    for method, path, body in GUARDED:
        s, b = call(e, method, path.format(a=agent), body, op=oid)
        assert s == 403 and b == FORBIDDEN, (path.format(a=agent), s, b)


def test_mutant_canary_manifest_without_the_alias_refuses_the_verifier(ve):
    original = ve.manifest.read_bytes()
    mutant = original.replace(b"      - FIELD canary (gate verification)\r\n", b"").replace(
        b"      - FIELD canary (gate verification)\n", b"")
    assert mutant != original
    try:
        ve.manifest.write_bytes(mutant)
        bump(ve.manifest)
        _arm(ve, "enforce")
        with pytest.raises(AssertionError):
            verifier_acts_on_canary(ve)
        s, body = call(ve, "POST", "/delegation/tokens",
                       {"agent_id": CANARY, "granted_by": ALIAS, "scope": CANARY_SCOPE, "ttl_seconds": 86400})
        assert s == 403 and body == FORBIDDEN, (s, body)
    finally:
        ve.manifest.write_bytes(original)
        bump(ve.manifest)
        _arm(ve, "off")
        _revive_if_killed(ve, CANARY)


# --- the runbook says what the code does -----------------------------------------------------------


def test_the_runbook_documents_the_row_and_every_test_it_cites_exists():
    import re

    text = (REPO / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
    start = text.index("**Machine verifier identity (P35")
    section = text[start:text.index("**Ledger fields**", start)]
    row = json.dumps({"operator_id": VERIFIER, "scopes": VERIFIER_SCOPES})[:-1]
    assert row in " ".join(section.split()), "the documented row drifted"
    assert f'"names": ["{ALIAS}"]' in section
    cited = set(re.findall(r"`((?:tools|packages|services)/[A-Za-z0-9_./-]+\.py)`", section))
    assert len(cited) >= 6, cited
    for path in sorted(cited):
        assert (REPO / path).is_file(), path
    # step 5 runs the positive controls under the verifier, never with Don's key file
    step5 = text[text.index("5. LOG-ONLY evidence."):text.index("6. ENFORCE, staged:")]
    assert "--operator-id svc-verifier-gb10" in " ".join(step5.split())
    assert "--operator-id don" not in step5
