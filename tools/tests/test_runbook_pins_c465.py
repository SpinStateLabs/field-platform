"""C-465 (reviewer C-196 F-C196-1, F-C196-2): a runbook that tells an operator "STOP if it differs" must carry the
hash the file really has, and the D-18 pre-deploy script must list active rows only.

F-C196-1: token-renewal.md pinned a sha256 of tools/renew_token.py in four places; the file moved on and an
operator following the runbook would have stopped on a good copy. The test recomputes the hash from the repository
file (LF bytes, as `.gitattributes` checks it out) and compares every pin on a line that names renew_token."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "runbooks" / "token-renewal.md"
DEPLOY = ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md"
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def renew_token_sha256() -> str:
    data = (ROOT / "tools" / "renew_token.py").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def pins(text: str) -> list[tuple[int, str]]:
    """(line number, hash) for every 64-hex token on a line that names renew_token."""
    return [(n, h) for n, line in enumerate(text.splitlines(), 1) if "renew_token" in line for h in HEX64.findall(line)]


def test_every_renew_token_pin_in_the_runbook_is_the_hash_of_the_file():
    found = pins(RUNBOOK.read_text(encoding="utf-8"))
    assert len(found) >= 4, found                       # the four places the reviewer named
    wrong = [(n, h[:12]) for n, h in found if h != renew_token_sha256()]
    assert not wrong, f"stale pin(s) on line(s) {wrong}; the file's sha256 is {renew_token_sha256()}"


def test_the_pin_finder_sees_a_stale_pin_and_ignores_other_files_hashes():
    text = "Expect `" + "a" * 64 + "  /x/renew_token.py`\nExpect `" + "b" * 64 + "  /x/verify_vt_field.py`\n"
    assert pins(text) == [(1, "a" * 64)]


def test_a_stale_pin_is_reported():
    stale = RUNBOOK.read_text(encoding="utf-8").replace(renew_token_sha256(), "0" * 64)
    assert all(h == "0" * 64 for _, h in pins(stale)) and len(pins(stale)) >= 4


def _d18_script() -> str:
    text = DEPLOY.read_text(encoding="utf-8")
    m = re.search(r"python3 - operators\.json <<'PY'\n(.*?)\nPY\n", text, re.S)
    assert m, "the D-18 pre-check script block moved or changed shape"
    return m.group(1)


def _run_d18(tmp_path: Path, rows: list[dict]) -> subprocess.CompletedProcess:
    f = tmp_path / "operators.json"
    f.write_text(json.dumps(rows), encoding="utf-8")
    script = tmp_path / "d18.py"
    script.write_text(_d18_script() + "\n", encoding="utf-8")
    return subprocess.run([sys.executable, str(script), str(f)], capture_output=True, text=True)


UNBOUND = {"operator_id": "svc-other", "key_sha256": "a" * 64, "scopes": ["kill", "revive", "revoke", "mint"]}


def test_the_d18_script_lists_an_active_unbound_verifier_scope_row_and_exits_1(tmp_path):
    r = _run_d18(tmp_path, [{**UNBOUND, "status": "active"}])
    assert r.returncode == 1 and "svc-other" in r.stdout


def test_the_d18_script_does_not_list_a_revoked_row(tmp_path):
    r = _run_d18(tmp_path, [{**UNBOUND, "status": "revoked"}])
    assert r.returncode == 0 and "none" in r.stdout and "svc-other" not in r.stdout


def test_the_d18_script_still_lists_a_row_with_no_status_field(tmp_path):
    r = _run_d18(tmp_path, [UNBOUND])
    assert r.returncode == 1 and "svc-other" in r.stdout


def test_the_d18_script_leaves_a_verifier_bound_row_and_a_human_star_row_alone(tmp_path):
    rows = [{**UNBOUND, "operator_id": "svc-verifier-x", "status": "active"},
            {"operator_id": "don", "key_sha256": "b" * 64, "status": "active", "scopes": ["*"]}]
    assert _run_d18(tmp_path, rows).returncode == 0


def test_the_d18_prose_says_active_rows_only():
    assert "neither is a row whose status is not `active`" in DEPLOY.read_text(encoding="utf-8")
