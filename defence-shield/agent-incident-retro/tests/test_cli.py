"""CLI behaviour — the trust decision and the exit codes must be pinned,
because a scheduled scan and a third-party verify rely on them."""

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from agent_incident_retro.cli import app
from agent_incident_retro.synth import generate

runner = CliRunner()


def _prep(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "air.key"), "--pub", str(tmp_path / "air.pub")])
    return log, tmp_path / "air.key", tmp_path / "air.pub"


def test_scan_exits_2_on_escalate_and_writes_outputs(tmp_path: Path):
    log, key, _ = _prep(tmp_path)
    r = runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "out"), "--key", str(key)])
    assert r.exit_code == 2, r.output  # ESCALATE present
    assert (tmp_path / "out" / "report.md").exists()
    assert (tmp_path / "out" / "evidence-pack.json").exists()


def test_scan_exits_0_when_no_escalate(tmp_path: Path):
    log = tmp_path / "clean.log"
    log.write_text(
        '192.0.2.1 - - [01/Sep/2026:00:00:00 +0000] "GET /about HTTP/1.1" 200 5 "-" "Mozilla/5.0"\n',
        encoding="utf-8",
    )
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    r = runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "o"), "--key", str(tmp_path / "k")])
    assert r.exit_code == 0, r.output


def test_scan_warns_on_mostly_unparsed(tmp_path: Path):
    log = tmp_path / "wrong.log"
    log.write_text("\n".join(f'{{"not":"clf","n":{i}}}' for i in range(10)) + "\n", encoding="utf-8")
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    r = runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "o"), "--key", str(tmp_path / "k")])
    assert "WARNING" in r.output and "did not parse" in r.output


def test_verify_ok_exit_0(tmp_path: Path):
    log, key, pub = _prep(tmp_path)
    runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "out"), "--key", str(key)])
    r = runner.invoke(
        app,
        ["verify", str(tmp_path / "out" / "evidence-pack.json"), "--pub", str(pub),
         "--report", str(tmp_path / "out" / "report.md"), "--sources", str(log)],
    )
    assert r.exit_code == 0 and "VERIFIED" in r.output


def test_verify_uses_supplied_pub_not_embedded(tmp_path: Path):
    """The core trust decision: a pack re-signed with another key must FAIL
    against the real signer's public key, even though the pack is internally
    consistent with its own embedded key."""
    import base64

    from field_core.signing import generate_keypair, key_fingerprint, load_ed25519_private_key
    from agent_incident_retro.evidence import canonical

    log, key, pub = _prep(tmp_path)
    runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "out"), "--key", str(key)])
    pack_path = tmp_path / "out" / "evidence-pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))

    atk_priv, atk_pub = generate_keypair()
    pack["summary"]["requests_total"] = 1  # the edit
    pack["signer"]["public_key_pem"] = atk_pub  # swap in the attacker's advertised key
    pack["signer"]["public_key_fingerprint"] = key_fingerprint(atk_pub)
    body = {k: v for k, v in pack.items() if k != "signature"}
    pack["signature"] = base64.b64encode(load_ed25519_private_key(atk_priv).sign(canonical(body))).decode()
    pack_path.write_text(json.dumps(pack))

    # the pack now advertises and is envelope-signed by the attacker key, but
    # verified against the REAL signer's public key it must FAIL (the embedded
    # PEM is never trusted). The fingerprint check is the first guard.
    r = runner.invoke(app, ["verify", str(pack_path), "--pub", str(pub)])
    assert r.exit_code == 1 and "VERIFICATION FAILED" in r.output
    assert "FAIL] signer fingerprint" in r.output


def test_verify_qualifies_when_report_or_sources_not_checked(tmp_path: Path):
    log, key, pub = _prep(tmp_path)
    runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "out"), "--key", str(key)])
    r = runner.invoke(app, ["verify", str(tmp_path / "out" / "evidence-pack.json"), "--pub", str(pub)])
    assert r.exit_code == 0
    assert "report not checked" in r.output and "source lines not checked" in r.output


#: Pack fields that legitimately differ between two scans of the same logs:
#: generated_at itself; every event's event_id/ts/hash/prev_hash/signature and
#: chain.head (all derived from the run timestamp); report_sha256 (the report
#: prints generated_at); and signature/signer when the key differs.
TIMESTAMP_OR_KEY_DERIVED = {"generated_at", "signature", "events", "chain", "report_sha256", "signer"}


def test_scan_is_deterministic_across_processes(tmp_path: Path):
    """Two separate processes (fresh PYTHONHASHSEED each, fresh key each) must
    produce byte-identical findings, verdicts, grades, campaigns, counts and
    inputs. Only the timestamp/key-derived fields may differ — the evidence
    chain is NOT deterministic across runs, and this test says exactly which
    fields are not."""
    log = tmp_path / "s.log"
    log.write_text(generate(seed=7), encoding="utf-8")

    def run(tag: str) -> dict:
        key = tmp_path / f"k{tag}"
        runner.invoke(app, ["keygen", "--out", str(key), "--pub", str(tmp_path / f"p{tag}")])
        out = tmp_path / f"o{tag}"
        subprocess.run(
            [sys.executable, "-m", "agent_incident_retro.cli", "scan", str(log), "--out", str(out), "--key", str(key)],
            check=False,
            cwd=str(Path(__file__).resolve().parents[1] / "src"),
        )
        return json.loads((out / "evidence-pack.json").read_text(encoding="utf-8"))

    a, b = run("a"), run("b")
    differing = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert differing <= TIMESTAMP_OR_KEY_DERIVED, differing
    for key in ("findings", "campaigns", "summary", "inputs", "config", "tool", "pack_version"):
        assert json.dumps(a[key], sort_keys=True) == json.dumps(b[key], sort_keys=True), key
    assert [f["verdict"] for f in a["findings"]] == [f["verdict"] for f in b["findings"]]
    assert [f["grade"] for f in a["findings"]] == [f["grade"] for f in b["findings"]]
    # the flagged events carry the same finding digests, in the same order,
    # even though the events themselves (ids, ts, hashes) differ
    digests = lambda p: [e["payload"]["finding_sha256"] for e in p["events"] if e["event_type"] == "retro.session.flagged"]
    assert digests(a) == digests(b)


# second independent review (2026-10-12), MEDIUM-3: keygen overwrite guards


def test_keygen_refuses_to_overwrite_an_existing_pub_without_force(tmp_path: Path):
    pub = tmp_path / "air.pub"
    pub.write_text("precious\n", encoding="utf-8")
    r = runner.invoke(app, ["keygen", "--out", str(tmp_path / "air.key"), "--pub", str(pub)])
    assert r.exit_code == 1 and "exists" in r.output
    assert pub.read_text(encoding="utf-8") == "precious\n"
    assert not (tmp_path / "air.key").exists()  # nothing half-written either


def test_keygen_refuses_to_overwrite_an_existing_private_key_without_force(tmp_path: Path):
    key = tmp_path / "air.key"
    key.write_text("precious\n", encoding="utf-8")
    r = runner.invoke(app, ["keygen", "--out", str(key)])
    assert r.exit_code == 1 and key.read_text(encoding="utf-8") == "precious\n"


def test_keygen_force_leaves_private_key_0600_even_over_a_0644_file(tmp_path: Path):
    import os
    import stat

    if os.name != "posix":
        import pytest

        pytest.skip("POSIX modes only")
    key = tmp_path / "air.key"
    key.write_text("old\n", encoding="utf-8")
    key.chmod(0o644)
    pub = tmp_path / "air.pub"
    pub.write_text("old\n", encoding="utf-8")
    r = runner.invoke(app, ["keygen", "--out", str(key), "--pub", str(pub), "--force"])
    assert r.exit_code == 0, r.output
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert "BEGIN PRIVATE KEY" in key.read_text(encoding="utf-8")
    assert "BEGIN PUBLIC KEY" in pub.read_text(encoding="utf-8")


def test_keygen_fresh_private_key_is_0600(tmp_path: Path):
    import os
    import stat

    if os.name != "posix":
        import pytest

        pytest.skip("POSIX modes only")
    key = tmp_path / "air.key"
    assert runner.invoke(app, ["keygen", "--out", str(key)]).exit_code == 0
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_verify_reports_zero_compared_on_label_mismatch_and_fails(tmp_path: Path):
    """``verify --sources`` with a file whose name does not match any pack
    input label compares nothing; it must say so and FAIL, not print
    "N lines match" over zero comparisons."""
    import shutil

    log, key, pub = _prep(tmp_path)
    runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "out"), "--key", str(key)])
    renamed = tmp_path / "renamed.log"
    shutil.copyfile(log, renamed)
    r = runner.invoke(app, ["verify", str(tmp_path / "out" / "evidence-pack.json"), "--pub", str(pub), "--sources", str(renamed)])
    assert r.exit_code == 1 and "VERIFICATION FAILED" in r.output
    assert "FAIL] cited source lines: 0 of" in r.output and "label mismatch" in r.output
    assert "compared, all match" not in r.output
