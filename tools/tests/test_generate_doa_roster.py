"""tools/generate_doa_roster.py - the DOA roster the A3 arming step deploys.

A wrong roster is not cosmetic: a missing grantor refuses a real renewal
(403 D.grantor) the day it is armed, and an extra one authorises a string
nobody reviewed. Every rule the tool applies is pinned here with synthetic
inputs, each written to fail if its guard is removed:

* rows = distinct `granted_by` + distinct `identity.principal` over the
  manifests of registered, NON-RETIRED agents only (a manifest on disk with no
  registry record contributes nothing), plus (plan J9 row source 1, --tokens)
  the grantor of every LIVE token such an agent holds, scoped to its manifest;
* `allowed_scope` = ordered union over the manifests naming that string;
* `max_ttl_days` default 30, `--max-ttl-days` honoured, `active: true`;
* refusals (exit 2, nothing written): empty roster (with or without
  --skip-unresolved), unresolvable manifests without --skip-unresolved, bad
  registry or token inputs, a roster the service model rejects;
* the output loads with delegation_authority.doa AND drives the real mint gate.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import generate_doa_roster as gen  # noqa: E402
from delegation_authority.doa import DoaRoster, load_roster  # noqa: E402
from field_core.templates_api import template_data  # noqa: E402


def manifest(directory: Path, agent: str, granted_by: str, principal: str, scope: list[str],
             valid: bool = True) -> Path:
    path = directory / f"{agent}.yaml"
    if not valid:
        path.write_text("delegation: [this is: not a manifest\n", encoding="utf-8")
        return path
    data = template_data("default")
    data["agent"]["name"] = agent
    data["identity"]["principal"] = principal
    data["delegation"]["granted_by"] = granted_by
    data["delegation"]["scope"] = list(scope)
    data["delegation"]["expiry"] = "2027-06-30"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def record(agent: str, status: str = "active", ref: str | None = "default") -> dict:
    rec = {"agent_id": agent, "name": agent, "owner": "Someone", "domain": "finance", "status": status}
    if ref == "default":
        rec["manifest_ref"] = f"/data/manifests/{agent}.yaml"  # an ESTATE path, resolved by file name
    elif ref is not None:
        rec["manifest_ref"] = ref
    return rec


def run(tmp_path: Path, records: list[dict], *extra: str) -> tuple[int, str, str, Path]:
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps(records), encoding="utf-8")
    out = tmp_path / "out" / "doa-roster.yaml"
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        code = gen.main(["--registry", str(registry), "--manifests", str(tmp_path / "manifests"),
                         "--out", str(out), *extra])
    return code, so.getvalue(), se.getvalue(), out


def rows(out: Path) -> dict[str, dict]:
    return {r["grantor"]: r for r in yaml.safe_load(out.read_text(encoding="utf-8"))["grantors"]}


@pytest.fixture()
def estate(tmp_path):
    """Four manifests on disk, three registry records:
    - inv   (active)  granted_by Don Co, principal Don Co,    scope a, b
    - time  (killed)  granted_by Don Co, principal Jane Doe,  scope b, c
    - old   (retired) granted_by Old Boss, principal Old Boss, scope z
    - stray (manifest on disk, NOT registered) granted_by Stray Grantor, scope s
    """
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    manifest(mdir, "inv", "Don Co", "Don Co", ["a", "b"])
    manifest(mdir, "time", "Don Co", "Jane Doe", ["b", "c"])
    manifest(mdir, "old", "Old Boss", "Old Boss", ["z"])
    manifest(mdir, "stray", "Stray Grantor", "Stray Grantor", ["s"])
    return [record("inv"), record("time", status="killed"), record("old", status="retired")]


# --- the rows -------------------------------------------------------------------


def test_rows_are_grantors_and_principals_of_registered_non_retired_agents(tmp_path, estate):
    code, stdout, stderr, out = run(tmp_path, estate)
    assert code == 0, stderr
    got = rows(out)
    assert sorted(got) == ["Don Co", "Jane Doe"]
    assert got["Don Co"]["allowed_scope"] == ["a", "b", "c"]  # union over inv + time, first-seen order
    assert got["Jane Doe"]["allowed_scope"] == ["b", "c"]     # principal of time only
    for row in got.values():
        assert row["max_ttl_days"] == 30
        assert row["active"] is True
        assert "max_spend_usd" not in row
    assert "2 grantor row(s)" in stdout


def test_a_retired_agent_contributes_no_grantor(tmp_path, estate):
    code, _, _, out = run(tmp_path, estate)
    assert code == 0
    assert "Old Boss" not in rows(out)
    # positive control: the same agent un-retired IS rostered
    estate[2]["status"] = "active"
    code, _, _, out = run(tmp_path, estate)
    assert code == 0 and rows(out)["Old Boss"]["allowed_scope"] == ["z"]


def test_a_manifest_with_no_registry_record_contributes_nothing(tmp_path, estate):
    code, _, _, out = run(tmp_path, estate)
    assert code == 0
    assert "Stray Grantor" not in rows(out)


def test_a_principal_that_is_also_a_grantor_is_one_row(tmp_path, estate):
    code, _, _, out = run(tmp_path, estate)
    text = out.read_text(encoding="utf-8")
    assert text.count("grantor: Don Co") == 1


def test_max_ttl_days_flag_is_honoured(tmp_path, estate):
    code, _, _, out = run(tmp_path, estate, "--max-ttl-days", "45")
    assert code == 0
    assert {r["max_ttl_days"] for r in rows(out).values()} == {45}


# --- refusals: exit 2, nothing written --------------------------------------------


def test_no_grantors_is_refused_and_nothing_is_written(tmp_path, estate):
    for rec in estate:
        rec["status"] = "retired"
    code, _, stderr, out = run(tmp_path, estate)
    assert code == 2
    assert "no grantors" in stderr
    assert not out.exists()
    assert not out.parent.exists() or list(out.parent.iterdir()) == []


def test_an_empty_registry_is_refused(tmp_path, estate):
    code, _, stderr, out = run(tmp_path, [])
    assert code == 2 and not out.exists()


@pytest.mark.parametrize("bad", ["missing-file", "no-ref", "invalid"])
def test_an_unresolvable_manifest_is_refused_by_default(tmp_path, estate, bad):
    if bad == "missing-file":
        estate.append(record("ghost"))
    elif bad == "no-ref":
        estate.append(record("smoke-live", ref=None))
    else:
        manifest(tmp_path / "manifests", "broken", "X", "X", ["x"], valid=False)
        estate.append(record("broken"))
    code, _, stderr, out = run(tmp_path, estate)
    assert code == 2
    assert {"missing-file": "ghost (missing)", "no-ref": "smoke-live (no_ref)",
            "invalid": "broken (invalid)"}[bad] in stderr
    assert not out.exists()


def test_skip_unresolved_writes_the_rest_and_names_what_it_skipped(tmp_path, estate):
    estate.append(record("smoke-live", ref=None))
    code, stdout, stderr, out = run(tmp_path, estate, "--skip-unresolved")
    assert code == 0
    assert "skipped smoke-live" in stderr
    assert "1 unresolved skipped" in stdout
    assert sorted(rows(out)) == ["Don Co", "Jane Doe"]


def test_a_roster_the_service_model_rejects_is_never_written(tmp_path, estate):
    """max_ttl_days must be > 0 in delegation_authority.doa. Validation runs
    BEFORE writing, so an existing roster is left untouched."""
    out = tmp_path / "out" / "doa-roster.yaml"
    out.parent.mkdir()
    out.write_text("previous roster\n", encoding="utf-8")
    code, _, stderr, _ = run(tmp_path, estate, "--max-ttl-days", "0")
    assert code == 2
    assert "does not validate" in stderr
    assert out.read_text(encoding="utf-8") == "previous roster\n"
    assert not (out.parent / "doa-roster.yaml.tmp").exists()


def test_a_written_file_that_does_not_reload_is_refused(tmp_path, estate, monkeypatch):
    """The reload check: if what lands on disk is not what was validated, the
    old file stays and the temp file is removed."""
    real_dump = gen.yaml.safe_dump
    monkeypatch.setattr(gen.yaml, "safe_dump",
                        lambda data, **kw: real_dump(data, **kw).replace("max_ttl_days: 30", "max_ttl_days: 31"))
    code, _, stderr, out = run(tmp_path, estate)
    assert code == 2
    assert "does not reload" in stderr
    assert not out.exists()
    assert not (out.parent / "doa-roster.yaml.tmp").exists()


@pytest.mark.parametrize("content", ["not json", '{"agents": []}', '[{"name": "no id"}]'])
def test_malformed_registry_input_is_refused(tmp_path, estate, content):
    (tmp_path / "agents.json").write_text(content, encoding="utf-8")
    out = tmp_path / "out.yaml"
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = gen.main(["--registry", str(tmp_path / "agents.json"),
                         "--manifests", str(tmp_path / "manifests"), "--out", str(out)])
    assert code == 2 and not out.exists()
    assert "REFUSED" in err.getvalue()


# --- the output is a real roster ----------------------------------------------------


def test_output_loads_with_the_service_loader_and_drives_the_real_mint_gate(tmp_path, estate, monkeypatch):
    code, _, _, out = run(tmp_path, estate)
    assert code == 0
    assert isinstance(load_roster(out), DoaRoster)

    from typer.testing import CliRunner
    from delegation_authority.cli import app

    def check(grantor: str, agent: str, *scopes: str) -> int:
        argv = ["doa", "check", "--roster", str(out), "--grantor", grantor, "--ttl-days", "30",
                "--manifest", str(tmp_path / "manifests" / f"{agent}.yaml")]
        for s in scopes:
            argv += ["--scope", s]
        return CliRunner().invoke(app, argv).exit_code

    assert check("Don Co", "inv", "a", "b") == 0
    assert check("Don Co", "time", "b", "c") == 0
    assert check("Jane Doe", "time", "b", "c") == 0
    assert check("Old Boss", "old", "z") == 1        # retired agent's grantor: off roster
    assert check("Stray Grantor", "stray", "s") == 1  # unregistered manifest: off roster


def test_the_repo_manifests_give_don_the_union_of_every_scope(tmp_path):
    """The repo manifests alone, with no token file and without
    volatility-trader (so NOT the full GB10 shape: see
    test_the_gb10_shape_with_live_tokens_rosters_both_of_dons_strings): both
    ssl agents and the canary are registered; Don's row must carry every scope
    any of them declares, and the canary principal gets the canary's own scopes."""
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    names = ["ssl-invoicing-agent", "ssl-timekeeping-agent", "canary-gb10"]
    union: list[str] = []
    for name in names:
        src = REPO / "manifests" / f"{name}.yaml"
        (mdir / src.name).write_bytes(src.read_bytes())
        for s in yaml.safe_load(src.read_text(encoding="utf-8"))["delegation"]["scope"]:
            if s not in union:
                union.append(s)
    records = [record(n) for n in names] + [record("canary-gb10-retired", status="retired", ref=None)]
    code, _, stderr, out = run(tmp_path, records)
    assert code == 0, stderr
    got = rows(out)
    assert set(got) == {"Don Hagell, Spin State Labs", "FIELD canary (gate verification)"}
    assert sorted(got["Don Hagell, Spin State Labs"]["allowed_scope"]) == sorted(union)


def test_the_script_runs_as_a_script(tmp_path, estate):
    registry = tmp_path / "agents.json"
    registry.write_text(json.dumps(estate), encoding="utf-8")
    out = tmp_path / "roster.yaml"
    proc = subprocess.run([sys.executable, str(TOOLS / "generate_doa_roster.py"),
                           "--registry", str(registry), "--manifests", str(tmp_path / "manifests"),
                           "--out", str(out)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert rows(out)["Don Co"]["allowed_scope"] == ["a", "b", "c"]


# --- plan J9 row source 1: grantors of live tokens (--tokens) ---------------------


def token(agent: str, grantor: str, days: float = 10, revoked: bool = False,
          token_id: str | None = None) -> dict:
    """A GET /delegation/tokens record. days < 0 = already expired."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return {
        "token_id": token_id or f"tok-{agent}-{abs(hash((grantor, days, revoked))) % 10**8}",
        "agent_id": agent, "granted_by": grantor, "scope": ["anything"],
        "issued_at": (now - timedelta(days=1)).isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "revoked": revoked,
        "revocation_id": "rev-1" if revoked else None,
        "revoked_at": now.isoformat() if revoked else None,
    }


def write_tokens(tmp_path: Path, tokens: list[dict]) -> Path:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps(tokens), encoding="utf-8")
    return path


def test_live_token_grantors_are_rostered_with_their_holders_manifest_scope(tmp_path, estate):
    """A grantor string that no manifest names but a live token carries gets a
    row, scoped to the manifest of the agent holding the token. Revoked and
    expired tokens, and tokens held by retired or unregistered agents, add
    nothing."""
    tokens = write_tokens(tmp_path, [
        token("inv", "Token Only Grantor"),                    # live, held by active inv
        token("time", "Don Co"),                               # live; string already a manifest row
        token("inv", "Revoked Grantor", revoked=True),
        token("inv", "Expired Grantor", days=-1),
        token("old", "Retired Holder Grantor"),                # holder retired
        token("stray", "Unregistered Holder Grantor"),         # holder not in the registry
    ])
    code, stdout, stderr, out = run(tmp_path, estate, "--tokens", str(tokens))
    assert code == 0, stderr
    got = rows(out)
    assert sorted(got) == ["Don Co", "Jane Doe", "Token Only Grantor"]
    assert got["Token Only Grantor"]["allowed_scope"] == ["a", "b"]   # inv's manifest scope
    assert got["Don Co"]["allowed_scope"] == ["a", "b", "c"]          # unchanged union
    assert "Token Only Grantor: 2 scope(s), max_ttl_days=30 [token-only: live token(s) held by inv]" in stdout
    assert "ignored 4 token(s)" in stdout
    assert "no --tokens given" not in stderr
    # tokens that cannot be renewed are ignored, not reported as "no manifest"
    for grantor in ("Revoked Grantor", "Expired Grantor", "Retired Holder Grantor",
                    "Unregistered Holder Grantor"):
        assert grantor not in stdout and grantor not in stderr

    from typer.testing import CliRunner
    from delegation_authority.cli import app

    argv = ["doa", "check", "--roster", str(out), "--grantor", "Token Only Grantor", "--ttl-days", "30",
            "--manifest-ref", str(tmp_path / "manifests" / "inv.yaml"), "--scope", "a", "--scope", "b"]
    assert CliRunner().invoke(app, argv).exit_code == 0


def test_without_tokens_a_token_only_grantor_is_not_rostered_and_the_tool_says_so(tmp_path, estate):
    code, _, stderr, out = run(tmp_path, estate)
    assert code == 0
    assert "Token Only Grantor" not in rows(out)
    assert "no --tokens given" in stderr and "NOT rostered" in stderr
    assert "NO token file" in out.read_text(encoding="utf-8")


def test_a_live_token_grantor_whose_holder_has_no_manifest_is_named_not_rostered(tmp_path, estate):
    estate.append(record("ghost"))  # registered, active, manifest missing
    tokens = write_tokens(tmp_path, [token("ghost", "Ghost Grantor")])
    code, _, stderr, out = run(tmp_path, estate, "--tokens", str(tokens), "--skip-unresolved")
    assert code == 0, stderr
    assert "Ghost Grantor" not in rows(out)
    assert "live-token grantor 'Ghost Grantor' NOT rostered: its holder(s) ghost" in stderr

    # a grantor that IS rostered (here via inv's manifest) is never reported as
    # "NOT rostered" just because one of its holders has no manifest
    tokens = write_tokens(tmp_path, [token("ghost", "Don Co")])
    code, _, stderr, out = run(tmp_path, estate, "--tokens", str(tokens), "--skip-unresolved")
    assert code == 0 and "Don Co" in rows(out)
    assert "NOT rostered: its holder(s)" not in stderr


@pytest.mark.parametrize("content", [
    "not json", '{"tokens": []}',
    json.dumps([{"agent_id": "inv", "granted_by": "X"}]),              # not a delegation token
    json.dumps([{**token("inv", "X"), "note": "extra key"}]),           # extra='forbid'
    json.dumps([{**token("inv", "X"), "issued_at": "2026-09-01T00:00:00",
                 "expires_at": "2099-01-01T00:00:00"}]),                # naive: was a TypeError crash
], ids=["not-json", "not-a-list", "missing-fields", "extra-key", "naive-timestamps"])
def test_malformed_tokens_input_is_refused(tmp_path, estate, content):
    tokens = tmp_path / "tokens.json"
    tokens.write_text(content, encoding="utf-8")
    code, _, stderr, out = run(tmp_path, estate, "--tokens", str(tokens))
    assert code == 2 and not out.exists()
    assert "REFUSED (nothing written): --tokens" in stderr


def test_skip_unresolved_with_every_agent_unresolved_is_still_refused(tmp_path):
    """The likely operator slip: --manifests points at the wrong (empty)
    directory AND --skip-unresolved is passed. `grantors: []` must never be
    written, on this path either."""
    (tmp_path / "manifests").mkdir()
    records = [record("ssl-invoicing-agent"), record("ssl-timekeeping-agent")]
    tokens = write_tokens(tmp_path, [token("ssl-invoicing-agent", "Don Hagell, Spin State Labs")])
    for extra in ((), ("--tokens", str(tokens))):
        code, stdout, stderr, out = run(tmp_path, records, "--skip-unresolved", *extra)
        assert code == 2, (stdout, stderr)
        assert "no grantors" in stderr
        assert not out.exists()
        assert not out.parent.exists() or list(out.parent.iterdir()) == []


def test_the_gb10_shape_with_live_tokens_rosters_both_of_dons_strings(tmp_path):
    """Plan J9's GB10 example: rows `Don Hagell` AND `Don Hagell, Spin State
    Labs`. volatility-trader is registered and active and holds a live token
    granted by `Don Hagell`; its real manifest is not in the repo, so a
    SYNTHETIC one stands in, deliberately naming neither of Don's strings, so
    the `Don Hagell` row can only come from the token. smoke-agent is retired."""
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    for name in ("ssl-invoicing-agent", "ssl-timekeeping-agent", "canary-gb10"):
        src = REPO / "manifests" / f"{name}.yaml"
        (mdir / src.name).write_bytes(src.read_bytes())
    manifest(mdir, "volatility-trader", "vt synthetic grantor", "vt synthetic principal",
             ["read market data", "place shadow order"])
    records = [record("ssl-invoicing-agent"), record("ssl-timekeeping-agent"), record("canary-gb10"),
               record("volatility-trader"), record("smoke-agent", status="retired", ref=None)]
    tokens = write_tokens(tmp_path, [
        token("volatility-trader", "Don Hagell", days=7),
        token("ssl-invoicing-agent", "Don Hagell, Spin State Labs", days=26),
        token("ssl-timekeeping-agent", "Don Hagell, Spin State Labs", days=26),
    ])
    code, stdout, stderr, out = run(tmp_path, records, "--tokens", str(tokens))
    assert code == 0, stderr
    got = rows(out)
    assert {"Don Hagell", "Don Hagell, Spin State Labs", "FIELD canary (gate verification)"} <= set(got)
    assert got["Don Hagell"]["allowed_scope"] == ["read market data", "place shadow order"]
    assert "[token-only: live token(s) held by volatility-trader]" in stdout

    from typer.testing import CliRunner
    from delegation_authority.cli import app

    argv = ["doa", "check", "--roster", str(out), "--grantor", "Don Hagell", "--ttl-days", "30",
            "--manifest-ref", str(mdir / "volatility-trader.yaml"),
            "--scope", "read market data", "--scope", "place shadow order"]
    result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
